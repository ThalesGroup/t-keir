"""Title: T-KEIR RAG answer pipeline for evaluation (NLP + ontology + LLM).

Offline mirror of ``/rag/query`` generation without FastAPI/Vespa:

1. Analyze the request (full linguistic pipeline)
2. Analyze evidence passages (focus windows + passage SVO)
3. Merge query+passage SVO into one ontology (optional reasoner)
4. Detect question type / answer shape
5. Build **one** unique type-aware QA prompt with relevant ontology facts
6. Single LLM generate call

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from thot.core.LlmWrapper import UnifiedLLMWrapper, WrapperConfig
from thot.core.TkeirPaths import rag_prompts_path
from thot.tools.search.generation_prompt import (
    build_focus_query_text,
    detect_question_type,
    question_type_short_answer_spec,
)
from thot.tools.search.ontology_utils import (
    extract_focus_passages,
    filter_query_relevant_chunks,
    prioritize_chunks_by_query_match,
)
from thot.tools.search.rag_config import (
    load_rag_config,
    resolve_passage_settings,
)
from thot.tools.search.rag_report import (
    format_input_prompt,
    parse_structured_generation,
)
from thot.tools.search.vespa_client import clean_chunk_text_for_prompt

LOGGER = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

_FORGE_SYSTEM = (
    "You are a RAG prompt engineer. Build ONE sharp user prompt for a QA model. "
    "You MUST ground the prompt in the provided QUESTION TYPE, QUERY SVO, "
    "PASSAGE SVO, and KEY PASSAGES. "
    "Keep every fact needed to answer. Drop indexing noise, navigation, "
    "cookie banners, and duplicate sentences. "
    "Return ONLY the forged user prompt text — no preamble."
)


@dataclass
class PassageHit:
    """One retrieved passage from the eval corpus."""

    doc_id: str
    title: str
    text: str
    score: float = 0.0


@dataclass
class RagAnswerResult:
    """One query's generation output for RAG eval."""

    query_id: str
    query: str
    short_answer: str
    detailed_report: str
    input_prompt: str
    forged: bool = False
    system_prompt: str = ""
    user_prompt: str = ""
    question_type: str = ""
    query_analysis: dict[str, Any] = field(default_factory=dict)
    structured_facts: str = ""
    focus_passages: str = ""
    reasoner_note: str = ""
    sparql_queries: list[str] = field(default_factory=list)
    sparql_clues: str = ""
    error: str | None = None


def load_prompt_language_block(language: str = "en") -> dict[str, Any]:
    """Load one language block from ``rag-prompts.yaml``."""
    path = Path(rag_prompts_path())
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    lang = (language or "en").lower()
    block = payload.get(lang) or payload.get("en") or {}
    if not isinstance(block, dict):
        raise ValueError(f"Invalid rag-prompts.yaml block for language={lang}")
    return block


def query_analysis_to_dict(analysis: Any) -> dict[str, Any]:
    """Serialize :class:`QueryAnalysis` (or dict) for generation helpers."""
    if isinstance(analysis, dict):
        return analysis
    return {
        "raw_query": getattr(analysis, "raw_query", ""),
        "language": getattr(analysis, "language", None),
        "search_terms": list(getattr(analysis, "search_terms", []) or []),
        "lexical_query": getattr(analysis, "lexical_query", "") or "",
        "keywords": list(getattr(analysis, "keywords", []) or []),
        "lemmas": list(getattr(analysis, "lemmas", []) or []),
        "pipeline_failed": bool(getattr(analysis, "pipeline_failed", False)),
        "ner_entities": [
            {"text": entity.text, "label": entity.label}
            for entity in getattr(analysis, "ner_entities", None) or []
        ],
        "svo_triples": [
            {
                "subject": triple.subject,
                "verb": triple.verb,
                "object": triple.object,
            }
            for triple in getattr(analysis, "svo_triples", None) or []
        ],
        "morphosyntax": list(getattr(analysis, "morphosyntax", []) or []),
    }


def analyze_request(
    raw_query: str,
    *,
    runner: Any,
    language: str = "en",
) -> dict[str, Any]:
    """Run full T-KEIR NLP on the user request.

    Stores the pipeline document under ``_pipeline_doc`` for ontology build.
    """
    from thot.tools.search.query_analyzer import (
        analyze_query_document,
        run_linguistic_pipeline,
    )
    from thot.tools.search.rag_config import RagSearchConfig

    normalized = (raw_query or "").strip()
    cfg = RagSearchConfig(enabled=True, use_chunk_embedding=False)
    if not normalized:
        return {"raw_query": raw_query, "language": language}
    try:
        processed = run_linguistic_pipeline(
            runner, normalized, language=language
        )
        analysis = analyze_query_document(
            processed, normalized, language=language, config=cfg
        )
        payload = query_analysis_to_dict(analysis)
        payload["_pipeline_doc"] = ensure_pipeline_safe(processed, normalized)
        return payload
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Request NLP failed: %s", exc)
        return {
            "raw_query": normalized,
            "language": language,
            "pipeline_failed": True,
            "search_terms": normalized.split(),
        }


def ensure_pipeline_safe(
    processed: dict[str, Any], text: str
) -> dict[str, Any]:
    """Shallow-copy pipeline output with content filled when missing."""
    document = dict(processed or {})
    if text and not document.get("content"):
        document["content"] = [text]
    return document


def _analyze_passages(
    passages: list[PassageHit],
    *,
    runner: Any | None,
    language: str,
    max_passages: int = 5,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Run NLP on passages → SVO lines + pipeline documents for ontology."""
    if runner is None:
        return [], []
    from thot.tasks.answer_generation.ontology_clues import (
        ensure_pipeline_document,
    )
    from thot.tools.search.query_analyzer import (
        analyze_query_document,
        run_linguistic_pipeline,
    )
    from thot.tools.search.rag_config import RagSearchConfig

    lines: list[str] = []
    documents: list[dict[str, Any]] = []
    cfg = RagSearchConfig(enabled=True, use_chunk_embedding=False)
    for hit in passages[:max_passages]:
        text = clean_chunk_text_for_prompt(hit.text)[:4000]
        if not text.strip():
            continue
        try:
            processed = run_linguistic_pipeline(
                runner, text, language=language
            )
            analysis = analyze_query_document(
                processed, text, language=language, config=cfg
            )
            document = ensure_pipeline_document(
                processed, source_id=str(hit.doc_id), text=text
            )
            documents.append(document)
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("Passage NLP failed for %s: %s", hit.doc_id, exc)
            continue
        for triple in analysis.svo_triples:
            subject = (triple.subject or "").strip()
            verb = (triple.verb or "").strip()
            obj = (triple.object or "").strip()
            if subject and verb:
                lines.append(f"- {subject} — {verb} — {obj}".rstrip(" —"))
    return list(dict.fromkeys(lines)), documents


def _passage_svo_lines(
    passages: list[PassageHit],
    *,
    runner: Any | None,
    language: str,
    max_passages: int = 5,
) -> list[str]:
    """Extract SVO lines from top passages via the linguistic pipeline."""
    lines, _docs = _analyze_passages(
        passages,
        runner=runner,
        language=language,
        max_passages=max_passages,
    )
    return lines


def structure_passages(
    query: str,
    passages: list[PassageHit],
    *,
    analysis: dict[str, Any],
    runner: Any | None = None,
    language: str = "en",
    use_reasoner: bool = True,
) -> tuple[str, str, str, list[dict[str, Any]]]:
    """Analyze passages → KEY PASSAGES + STRUCTURED FACTS + pipeline docs.

    Returns:
        ``(focus_passages, structured_facts, reasoner_note, passage_documents)``
        where ``passage_documents`` are NLP outputs ready for document_ontology.
    """
    rag_cfg = load_rag_config()
    passage_settings = resolve_passage_settings(
        defaults=rag_cfg.prompt.passages
    )
    # Lightweight chunk-like objects for prioritize helpers
    ranked = sorted(passages, key=lambda item: item.score, reverse=True)

    class _Chunk:
        def __init__(self, hit: PassageHit) -> None:
            self.chunk_id = hit.doc_id
            self.text_raw = hit.text
            self.title = hit.title
            self.parent_doc_id = hit.doc_id
            self.score = hit.score
            self.relevance = hit.score

    chunks = [_Chunk(hit) for hit in ranked]
    focus_query = build_focus_query_text(raw_query=query, analysis=analysis)
    prioritized = prioritize_chunks_by_query_match(chunks, focus_query)
    prioritized = filter_query_relevant_chunks(
        prioritized,
        focus_query,
        max_chunks=rag_cfg.prompt.max_chunks_for_prompt,
    )
    if not prioritized:
        prioritized = chunks[: rag_cfg.prompt.max_chunks_for_prompt]
    focus_passages = extract_focus_passages(
        [
            (chunk.chunk_id, clean_chunk_text_for_prompt(chunk.text_raw))
            for chunk in prioritized
        ],
        focus_query,
        max_passages=passage_settings.count,
        context_sentences=passage_settings.context_sentences,
        max_chars_per_passage=passage_settings.max_chars,
    )

    svo_lines, passage_documents = _analyze_passages(
        [
            PassageHit(c.chunk_id, c.title, c.text_raw, c.score)
            for c in prioritized
        ],
        runner=runner,
        language=language,
        max_passages=min(5, passage_settings.count),
    )
    structured_parts: list[str] = []
    if svo_lines:
        structured_parts.append("SVO facts from retrieved passages:")
        structured_parts.extend(svo_lines[: rag_cfg.prompt.max_svo_triples])
    # Always include short excerpts as fallback facts
    structured_parts.append("Source excerpts:")
    for chunk in prioritized[: rag_cfg.prompt.max_chunks_for_prompt]:
        excerpt = clean_chunk_text_for_prompt(chunk.text_raw)
        excerpt = excerpt[: rag_cfg.prompt.max_chars_per_chunk]
        title = (chunk.title or chunk.chunk_id).strip()
        structured_parts.append(f"[{title}]\n{excerpt}")
    structured_facts = "\n".join(structured_parts)

    reasoner_note = ""
    if use_reasoner and svo_lines:
        reasoner_note = _try_reason_over_svo(svo_lines[:40])

    return focus_passages, structured_facts, reasoner_note, passage_documents


def _try_reason_over_svo(svo_lines: list[str]) -> str:
    """Best-effort ontology reasoner pass over SVO-derived RDF."""
    try:
        from rdflib import Graph, Literal, Namespace, URIRef
        from rdflib.namespace import RDF, RDFS

        from thot.tools.search.ontology_reasoner import query_merged_ontology
    except Exception as exc:  # noqa: BLE001
        return f"reasoner unavailable: {exc}"

    ns = Namespace("urn:tkeir:eval:")
    graph = Graph()
    graph.bind("tkeir", ns)
    for index, line in enumerate(svo_lines):
        # "- S — V — O"
        body = line.lstrip("- ").strip()
        parts = [part.strip() for part in body.split("—")]
        if len(parts) < 2:
            continue
        subject = parts[0]
        verb = parts[1] if len(parts) > 1 else "relatedTo"
        obj = parts[2] if len(parts) > 2 else ""
        s_uri = URIRef(ns[f"s{index}"])
        graph.add((s_uri, RDF.type, ns.Entity))
        graph.add((s_uri, RDFS.label, Literal(subject)))
        if obj:
            o_uri = URIRef(ns[f"o{index}"])
            graph.add((o_uri, RDF.type, ns.Entity))
            graph.add((o_uri, RDFS.label, Literal(obj)))
            pred = URIRef(
                ns[re.sub(r"[^a-zA-Z0-9_]", "_", verb) or "relatedTo"]
            )
            graph.add((s_uri, pred, o_uri))
            graph.add((pred, RDFS.label, Literal(verb)))
    if len(graph) == 0:
        return ""
    try:
        raw = graph.serialize(format="json-ld")
        json_ld = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        result = query_merged_ontology(
            json_ld,
            operation="consistency",
        )
        consistent = result.get("consistent")
        if consistent is True:
            return "ontology reasoner: SVO graph consistent"
        if consistent is False:
            return "ontology reasoner: SVO graph inconsistent"
        return (
            f"ontology reasoner: {result.get('operation', 'consistency')} ok"
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("Reasoner skipped: %s", exc)
        return f"reasoner skipped: {exc}"


def _parse_svo_line(line: str) -> tuple[str, str, str] | None:
    """Parse ``- S — V — O`` or ``S | V | O`` into a triple."""
    body = line.lstrip("- ").strip()
    if "—" in body:
        parts = [part.strip() for part in body.split("—")]
    elif "|" in body:
        parts = [part.strip() for part in body.split("|")]
    else:
        return None
    if len(parts) < 2:
        return None
    subject = parts[0]
    verb = parts[1] if len(parts) > 1 else "relatedTo"
    obj = parts[2] if len(parts) > 2 else ""
    if not subject:
        return None
    return subject, verb, obj


def _svo_dicts_from_analysis(
    analysis: dict[str, Any],
) -> list[tuple[str, str, str]]:
    """Normalize query analysis SVO triples."""
    out: list[tuple[str, str, str]] = []
    for triple in analysis.get("svo_triples") or []:
        if isinstance(triple, dict):
            subject = str(triple.get("subject") or "").strip()
            verb = str(triple.get("verb") or "").strip()
            obj = str(triple.get("object") or "").strip()
        else:
            subject = str(getattr(triple, "subject", "") or "").strip()
            verb = str(getattr(triple, "verb", "") or "").strip()
            obj = str(getattr(triple, "object", "") or "").strip()
        if subject and verb:
            out.append((subject, verb, obj))
    return out


def _svo_dicts_from_structured_facts(
    structured_facts: str,
) -> list[tuple[str, str, str]]:
    """Extract passage SVO triples from structured facts text."""
    block = _extract_passage_svo_block(structured_facts)
    if block.startswith("(no"):
        return []
    out: list[tuple[str, str, str]] = []
    for line in block.splitlines():
        parsed = _parse_svo_line(line)
        if parsed:
            out.append(parsed)
    return out


def build_query_passage_ontology(
    analysis: dict[str, Any],
    structured_facts: str,
    *,
    use_reasoner: bool = True,
) -> tuple[str, str]:
    """Merge query+passage SVO into one ontology and optionally reason.

    Returns:
        ``(ontology_facts_text, reasoner_note)`` for the unique QA prompt.
    """
    query_triples = _svo_dicts_from_analysis(analysis)
    passage_triples = _svo_dicts_from_structured_facts(structured_facts)
    lines: list[str] = []
    if query_triples:
        lines.append("Query relations:")
        for subject, verb, obj in query_triples:
            lines.append(f"- {subject} — {verb} — {obj}".rstrip(" —"))
    if passage_triples:
        lines.append("Passage relations:")
        for subject, verb, obj in passage_triples:
            lines.append(f"- {subject} — {verb} — {obj}".rstrip(" —"))

    # Cross-link shared entities (lightweight multihop bridge).
    bridges: list[str] = []
    query_entities = {
        token.lower()
        for subject, _verb, obj in query_triples
        for token in (subject, obj)
        if token
    }
    for subject, verb, obj in passage_triples:
        if subject.lower() in query_entities or (
            obj and obj.lower() in query_entities
        ):
            bridges.append(
                f"- bridge: {subject} — {verb} — {obj}".rstrip(" —")
            )
    if bridges:
        lines.append(
            "Bridging relations (shared entities across query/passages):"
        )
        lines.extend(list(dict.fromkeys(bridges))[:40])

    reasoner_note = ""
    all_triples = query_triples + passage_triples
    if use_reasoner and all_triples:
        svo_lines = [
            f"- {subject} — {verb} — {obj}".rstrip(" —")
            for subject, verb, obj in all_triples
        ]
        reasoner_note = _try_reason_over_svo(svo_lines[:60])
        # Prefer inferred/bridge facts for multihop when reasoner is consistent.
        if "inconsistent" in reasoner_note.lower():
            lines.append(
                "Reasoner warning: ontology inconsistent — prefer KEY PASSAGES."
            )

    if not lines:
        return "(no ontology relations extracted)", reasoner_note
    return "\n".join(lines), reasoner_note


def _format_query_ner_block(analysis: dict[str, Any]) -> str:
    """Render query NER entities for the multi-strategy QA prompt."""
    entities = analysis.get("ner_entities") or []
    lines: list[str] = []
    for entity in entities[:16]:
        if isinstance(entity, dict):
            text = str(entity.get("text") or "").strip()
            label = str(entity.get("label") or "entity").strip()
        else:
            text = str(getattr(entity, "text", "") or "").strip()
            label = str(getattr(entity, "label", "entity") or "entity").strip()
        if text:
            lines.append(f"- {text} ({label})")
    return "\n".join(lines) if lines else "(no query NER extracted)"


def _format_query_svo_block(analysis: dict[str, Any]) -> str:
    """Render query SVO triples for the QA prompt."""
    triples = analysis.get("svo_triples") or []
    if not triples:
        return "(no query SVO extracted)"
    lines: list[str] = []
    for triple in triples:
        if isinstance(triple, dict):
            subject = str(triple.get("subject") or "").strip()
            verb = str(triple.get("verb") or "").strip()
            obj = str(triple.get("object") or "").strip()
        else:
            subject = str(getattr(triple, "subject", "") or "").strip()
            verb = str(getattr(triple, "verb", "") or "").strip()
            obj = str(getattr(triple, "object", "") or "").strip()
        if subject or verb or obj:
            lines.append(f"- {subject} — {verb} — {obj}".rstrip(" —"))
    return "\n".join(lines) if lines else "(no query SVO extracted)"


def _extract_passage_svo_block(structured_facts: str) -> str:
    """Pull the SVO section out of structured facts text."""
    text = structured_facts or ""
    if "SVO facts from retrieved passages:" not in text:
        return "(no passage SVO extracted)"
    after = text.split("SVO facts from retrieved passages:", 1)[1]
    if "Source excerpts:" in after:
        after = after.split("Source excerpts:", 1)[0]
    lines = [line for line in after.splitlines() if line.strip()]
    return "\n".join(lines) if lines else "(no passage SVO extracted)"


def _extract_source_excerpts(structured_facts: str) -> str:
    """Pull classical source excerpts from structured facts text."""
    text = structured_facts or ""
    if "Source excerpts:" in text:
        return text.split("Source excerpts:", 1)[1].strip() or "(none)"
    # If the whole block is not SVO-prefixed, treat it as excerpts.
    if "SVO facts from retrieved passages:" not in text:
        return text.strip() or "(none)"
    return "(none)"


def _has_useful_sparql_clues(sparql_clues: str) -> bool:
    """True when SPARQL produced usable hit lines (not empty / no-hit markers)."""
    text = (sparql_clues or "").strip().lower()
    if not text:
        return False
    if text.startswith("(no "):
        return False
    if "no sparql" in text:
        return False
    return bool(text)


def _compact_reasoner_note(reasoner_note: str) -> str:
    """Keep reasoner status; drop noisy zero-hit SPARQL counters."""
    text = (reasoner_note or "").strip()
    if not text:
        return ""
    parts = [part.strip() for part in text.split(";") if part.strip()]
    kept: list[str] = []
    for part in parts:
        lower = part.lower()
        if "0 hit" in lower or "no hit" in lower:
            continue
        if lower.startswith("sparql#") and "hit" in lower:
            # Keep only non-zero SPARQL hit summaries.
            kept.append(part)
            continue
        kept.append(part)
    return "; ".join(kept)


def _filter_ontology_clue_lines(
    ontology_facts: str, *, max_lines: int = 24
) -> str:
    """Prefer relational ontology lines; drop pure type/label noise when possible."""
    text = (ontology_facts or "").strip()
    if not text or text.startswith("(no ") or text == "(none)":
        return ""
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    header: list[str] = []
    body: list[str] = []
    footer: list[str] = []
    for line in lines:
        if line.startswith("Merged ") or line.startswith("("):
            if line.startswith("("):
                footer.append(line)
            else:
                header.append(line)
            continue
        body.append(line)

    def _noise(line: str) -> bool:
        lower = line.lower()
        return (
            " | type | " in lower
            or " | label | " in lower
            or " | haskeyword | " in lower
            or lower.endswith(" | type | entity")
            or lower.endswith(" | type | keyword")
        )

    preferred = [line for line in body if not _noise(line)]
    chosen = preferred if preferred else body
    chosen = chosen[:max_lines]
    chunks = header + chosen + footer
    return "\n".join(chunks).strip()


def build_unique_qa_prompt(
    *,
    query: str,
    analysis: dict[str, Any],
    focus_passages: str,
    structured_facts: str,
    ontology_facts: str,
    reasoner_note: str = "",
    sparql_clues: str = "",
    question_type: str,
    language: str = "en",
) -> tuple[str, str]:
    """Build one multi-strategy type-aware QA prompt (no forge LLM).

    Evidence priority (do not invert):
      1. Question type + answer shape
      2. KEY PASSAGES / classical excerpts (primary)
      3. Query NER + query/passage SVO (structure)
      4. Ontology / SPARQL / reasoner (optional bridging clues only)
    """
    prompt_cfg = load_prompt_language_block(language)
    unavailable = str(
        prompt_cfg.get("unavailable_answer")
        or "The information is not available."
    )
    short_spec = question_type_short_answer_spec(
        question_type, language=language
    )
    query_svo = _format_query_svo_block(analysis)
    query_ner = _format_query_ner_block(analysis)
    passage_svo = _extract_passage_svo_block(structured_facts)
    source_excerpts = _extract_source_excerpts(structured_facts)
    ontology_block = _filter_ontology_clue_lines(ontology_facts)
    useful_sparql = _has_useful_sparql_clues(sparql_clues)
    compact_reasoner = _compact_reasoner_note(reasoner_note)

    if question_type == "yes_no":
        system = (
            "You are a precise yes/no QA model. "
            "PRIMARY evidence is KEY PASSAGES and SOURCE EXCERPTS. "
            "Use QUERY NER / SVO and PASSAGE SVO to align entities and relations. "
            "Treat ONTOLOGY / SPARQL / REASONER as optional bridging clues only — "
            "never refuse an answer solely because clues are empty when passages "
            "support Yes or No. Do not invent facts. "
            f"SHORT_ANSWER must be Yes or No. "
            f"If passages are insufficient, reply exactly: {unavailable}"
        )
    elif question_type == "inference":
        system = (
            "You are a multi-hop QA model. "
            "Combine KEY PASSAGES first, then QUERY/PASSAGE SVO and NER to bridge "
            "entities across sources. Ontology / SPARQL clues are optional helpers "
            "for multi-hop links — if they are empty, still answer from passages "
            "and SVO. Do not invent bridging facts. "
            f"If evidence is insufficient, reply exactly: {unavailable}"
        )
    elif question_type == "entity_report":
        system = str(
            prompt_cfg.get("system_svo") or prompt_cfg.get("system") or ""
        ).replace("{unavailable_answer}", unavailable)
    else:
        system = (
            "You are a precise QA model. "
            "Combine strategies in this order: (1) QUESTION TYPE / ANSWER SHAPE, "
            "(2) KEY PASSAGES and SOURCE EXCERPTS, (3) QUERY NER + QUERY/PASSAGE SVO, "
            "(4) optional ONTOLOGY / SPARQL / REASONER clues for bridges. "
            "Passages are authoritative; clues must not override clear passage text. "
            "Do not invent facts. "
            f"If evidence is insufficient, reply exactly: {unavailable}"
        )

    clue_sections: list[str] = []
    if ontology_block:
        clue_sections.append(
            "ONTOLOGY CLUES (optional bridges; not required if empty):\n"
            f"{ontology_block}"
        )
    if useful_sparql:
        clue_sections.append(
            "SPARQL CLUES (optional; query → merged passage ontologies):\n"
            f"{sparql_clues.strip()}"
        )
    if compact_reasoner:
        clue_sections.append(f"ONTOLOGY REASONER:\n{compact_reasoner}")
    clues_block = (
        "\n\n".join(clue_sections)
        if clue_sections
        else "(no ontology/SPARQL clues — rely on passages + NER/SVO)"
    )

    user = (
        f"QUESTION TYPE: {question_type}\n"
        f"ANSWER SHAPE: {short_spec}\n\n"
        f"QUESTION:\n{query}\n\n"
        f"STRATEGY: passages + answer type first; NER/SVO for structure; "
        f"ontology/SPARQL only as optional clues.\n\n"
        f"QUERY NER:\n{query_ner}\n\n"
        f"QUERY SVO:\n{query_svo}\n\n"
        f"PASSAGE SVO:\n{passage_svo}\n\n"
        f"KEY PASSAGES (primary evidence):\n"
        f"{(focus_passages or '(none)').strip()}\n\n"
        f"SOURCE EXCERPTS (classical context):\n"
        f"{source_excerpts}\n\n"
        f"OPTIONAL ONTOLOGY / REASONER CLUES:\n{clues_block}\n\n"
        "Return EXACTLY this format (keep the markers):\n\n"
        "SHORT_ANSWER:\n"
        "<answer matching ANSWER SHAPE>\n\n"
        "DETAILED_REPORT:\n"
        "<brief justification citing passages first, then NER/SVO, "
        "then any useful ontology clues>\n\n"
        f"If the evidence cannot support any answer, set SHORT_ANSWER to exactly:\n"
        f"{unavailable}"
    )
    return system, user


def build_rag_prompts(
    *,
    query: str,
    analysis: dict[str, Any],
    focus_passages: str,
    structured_facts: str,
    reasoner_note: str = "",
    language: str = "en",
    ontology_facts: str = "",
    sparql_clues: str = "",
    question_type: str | None = None,
) -> tuple[str, str]:
    """Assemble the unique multi-strategy QA prompt."""
    qtype = question_type or detect_question_type(query, analysis)
    ontology = ontology_facts
    note = reasoner_note
    if not ontology:
        ontology, built_note = build_query_passage_ontology(
            analysis, structured_facts, use_reasoner=False
        )
        if not note:
            note = built_note
    return build_unique_qa_prompt(
        query=query,
        analysis=analysis,
        focus_passages=focus_passages,
        structured_facts=structured_facts,
        ontology_facts=ontology,
        reasoner_note=note,
        sparql_clues=sparql_clues,
        question_type=qtype,
        language=language,
    )


def build_forge_brief(
    *,
    query: str,
    analysis: dict[str, Any],
    focus_passages: str,
    structured_facts: str,
    question_type: str,
    language: str = "en",
) -> str:
    """Build the forge LLM user message (SVO + question type first)."""
    short_spec = question_type_short_answer_spec(
        question_type, language=language
    )
    query_svo = _format_query_svo_block(analysis)
    passage_svo = _extract_passage_svo_block(structured_facts)
    ner = analysis.get("ner_entities") or []
    ner_lines = []
    for entity in ner[:12]:
        if isinstance(entity, dict):
            text = str(entity.get("text") or "").strip()
            label = str(entity.get("label") or "entity").strip()
        else:
            text = str(getattr(entity, "text", "") or "").strip()
            label = str(getattr(entity, "label", "entity") or "entity").strip()
        if text:
            ner_lines.append(f"- {text} ({label})")
    ner_block = "\n".join(ner_lines) if ner_lines else "(none)"
    return (
        f"QUESTION TYPE: {question_type}\n"
        f"SHORT_ANSWER SHAPE: {short_spec}\n\n"
        f"QUESTION:\n{query}\n\n"
        f"QUERY SVO (structure the answer around these relations):\n"
        f"{query_svo}\n\n"
        f"QUERY NAMED ENTITIES:\n{ner_block}\n\n"
        f"PASSAGE SVO (evidence relations):\n{passage_svo}\n\n"
        f"KEY PASSAGES:\n{(focus_passages or '(none)').strip()}\n\n"
        f"STRUCTURED FACTS / EXCERPTS:\n{(structured_facts or '(none)').strip()}\n\n"
        "Forge a compact USER prompt that:\n"
        "1. States the QUESTION TYPE and required SHORT_ANSWER shape.\n"
        "2. Restates the question via QUERY SVO.\n"
        "3. Lists only the PASSAGE SVO / KEY PASSAGE facts needed to answer.\n"
        "4. Keeps SHORT_ANSWER / DETAILED_REPORT output markers.\n"
        "5. Drops noise unrelated to the question type.\n"
        "Return ONLY that forged user prompt."
    )


async def forge_prompt_with_llm(
    llm: UnifiedLLMWrapper,
    *,
    system_prompt: str,
    user_prompt: str,
    query: str,
    analysis: dict[str, Any] | None = None,
    focus_passages: str = "",
    structured_facts: str = "",
    question_type: str = "",
    language: str = "en",
) -> str:
    """One LLM call to forge a sharp QA prompt from SVO + question type."""
    analysis = analysis or {}
    qtype = question_type or detect_question_type(query, analysis)
    forge_user = build_forge_brief(
        query=query,
        analysis=analysis,
        focus_passages=focus_passages,
        structured_facts=structured_facts,
        question_type=qtype,
        language=language,
    )
    # Keep a short tail of the deterministic template as a format hint.
    forge_user = (
        f"{forge_user}\n\n"
        f"FORMAT HINT (system excerpt):\n{system_prompt[:1200]}\n\n"
        f"FORMAT HINT (template excerpt):\n{user_prompt[:1500]}"
    )
    forged = await llm.generate(
        forge_user, system=_FORGE_SYSTEM, temperature=0.1
    )
    text = (forged or "").strip()
    if not text:
        return user_prompt
    return text


_MARKUP_LINE_RE = re.compile(
    r"^\s*(?:\*\*|__|#+|\d+[.)]\s+|[-*•]\s+)+",
)
_YES_NO_RE = re.compile(
    r"^\s*(yes|no|oui|non)\b",
    re.IGNORECASE,
)
_SENT_END_RE = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÀ-ÖØ-Þ\"'])")
_SYNTAGM_LABEL = "pattern_syntagm_or_prep_group"


def strip_answer_markup(text: str) -> str:
    """Remove markdown/bold/bullet wrappers from model answers."""
    if not text:
        return ""
    lines: list[str] = []
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line or set(line) <= {"*", "_", "-", " ", "#"}:
            continue
        line = _MARKUP_LINE_RE.sub("", line).strip()
        line = line.strip("*_ `")
        if line.upper() in {
            "SHORT_ANSWER",
            "SHORT ANSWER",
            "DETAILED_REPORT",
            "DETAILED REPORT",
        }:
            continue
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def _morph_sentences(morphosyntax: list[dict[str, Any]]) -> list[str]:
    """Rebuild complete sentences from morphosyntax (no mid-phrase cuts)."""
    if not morphosyntax:
        return []
    from thot.tasks.golden_chunking.ChunkBuilder import extract_sentence_spans

    sentences: list[str] = []
    for span in extract_sentence_spans(morphosyntax):
        tokens = morphosyntax[span.start : span.end]
        parts: list[str] = []
        for token in tokens:
            text = str(token.get("text") or "")
            if not text:
                continue
            if parts and text in {".", ",", "!", "?", ";", ":", "…", "'", "’"}:
                parts[-1] = parts[-1] + text
            elif parts and text.startswith("'"):
                parts[-1] = parts[-1] + text
            else:
                parts.append(text)
        sentence = " ".join(parts).strip()
        if sentence:
            sentences.append(sentence)
    return sentences


def _fallback_sentences(text: str) -> list[str]:
    """Split on sentence boundaries when morphosyntax is unavailable."""
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return []
    parts = _SENT_END_RE.split(normalized)
    return [part.strip() for part in parts if part.strip()]


def _kg_node_text(node: Any) -> str:
    """Join a KG subject/object/value ``content`` field into one phrase."""
    if not isinstance(node, dict):
        return ""
    content = node.get("content")
    if isinstance(content, list):
        return " ".join(
            str(part).strip() for part in content if str(part).strip()
        )
    if isinstance(content, str):
        return content.strip()
    return ""


def extract_nlp_syntagms(processed: dict[str, Any] | None) -> list[str]:
    """Collect ``pattern_syntagm_or_prep_group`` phrases from NLP ``kg``.

    These spans are produced by ``syntactic-rules.json`` (same resource used
    by the syntactic tagger), not by ad-hoc POS heuristics.
    """
    if not processed:
        return []
    phrases: list[str] = []
    for triple in processed.get("kg") or []:
        if not isinstance(triple, dict):
            continue
        for role in ("subject", "object", "value", "property"):
            node = triple.get(role)
            if not isinstance(node, dict):
                continue
            if str(node.get("label") or "") != _SYNTAGM_LABEL:
                continue
            phrase = _kg_node_text(node)
            if phrase:
                phrases.append(phrase)
    return list(dict.fromkeys(phrases))


def extract_nlp_named_entities(processed: dict[str, Any] | None) -> list[str]:
    """Collect named-entity surface forms from NLP ``content_ner``."""
    if not processed:
        return []
    phrases: list[str] = []
    for span in processed.get("content_ner") or []:
        if not isinstance(span, dict):
            continue
        text = str(span.get("text") or "").strip()
        if text:
            phrases.append(text)
    return list(dict.fromkeys(phrases))


def _normalize_yes_no(text: str) -> str | None:
    """Return canonical Yes/No when the answer opens that way."""
    match = _YES_NO_RE.match(text or "")
    if not match:
        return None
    token = match.group(1).lower()
    if token in {"yes", "oui"}:
        return "Yes"
    return "No"


def _prefer_annotated_phrase(
    cleaned: str,
    sentence: str,
    *,
    named_entities: list[str],
    syntagms: list[str],
) -> str | None:
    """Pick the best NER / syntagm phrase already present in the answer."""
    hay_clean = cleaned.lower()
    hay_sent = sentence.lower()
    ranked: list[str] = []
    # Prefer named entities first (who/which/what), then syntagm groups.
    for phrase in named_entities + syntagms:
        low = phrase.lower()
        if low in hay_clean or low in hay_sent:
            ranked.append(phrase)
    if not ranked:
        return None
    # Longest annotated span that fits the answer (complete phrase, no cut).
    ranked.sort(key=lambda item: (len(item), item), reverse=True)
    return ranked[0]


def coherent_short_answer(
    text: str,
    *,
    question_type: str = "other",
    morphosyntax: list[dict[str, Any]] | None = None,
    named_entities: list[str] | None = None,
    syntagms: list[str] | None = None,
    max_sentences: int | None = None,
) -> str:
    """Keep SHORT_ANSWER on complete sentences/NLP syntagms (never cut a phrase).

    Uses pipeline annotations:
    - ``content_ner`` named entities
    - ``kg`` nodes labeled ``pattern_syntagm_or_prep_group``
    - morphosyntax sentence boundaries (``is_sent_start``)
    """
    cleaned = strip_answer_markup(text)
    if not cleaned:
        return ""

    if question_type == "yes_no":
        yes_no = _normalize_yes_no(cleaned.replace("\n", " "))
        if yes_no:
            return yes_no

    sentences = _morph_sentences(morphosyntax or [])
    if not sentences:
        sentences = _fallback_sentences(cleaned.replace("\n", " "))
    if not sentences:
        return cleaned

    if max_sentences is None:
        if question_type in {
            "who",
            "what",
            "which",
            "when",
            "where",
            "yes_no",
        }:
            max_sentences = 1
        elif question_type in {"inference", "entity_report", "comparison"}:
            max_sentences = 2
        else:
            max_sentences = 2

    kept = sentences[: max(1, max_sentences)]

    if question_type in {"who", "which", "what"}:
        preferred = _prefer_annotated_phrase(
            cleaned,
            kept[0],
            named_entities=list(named_entities or []),
            syntagms=list(syntagms or []),
        )
        if preferred and len(kept[0].split()) <= 16:
            return preferred

    return " ".join(kept).strip()


def clean_detailed_report(text: str) -> str:
    """Light cleanup for DETAILED_REPORT (markup only; keep paragraphs)."""
    cleaned = strip_answer_markup(text)
    return cleaned.strip()


def clean_generated_answers(
    short_answer: str,
    detailed_report: str,
    *,
    question_type: str = "other",
    runner: Any | None = None,
    language: str = "en",
) -> tuple[str, str]:
    """Clean SHORT_ANSWER / DETAILED_REPORT using NLP NER + syntagm annotations."""
    morph: list[dict[str, Any]] | None = None
    named_entities: list[str] = []
    syntagms: list[str] = []
    stripped = strip_answer_markup(short_answer)
    if runner is not None and stripped:
        try:
            from thot.tools.search.query_analyzer import (
                run_linguistic_pipeline,
            )

            processed = run_linguistic_pipeline(
                runner, stripped, language=language
            )
            morph = list(processed.get("content_morphosyntax") or [])
            named_entities = extract_nlp_named_entities(processed)
            syntagms = extract_nlp_syntagms(processed)
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("Answer syntax cleanup skipped: %s", exc)
    short_clean = coherent_short_answer(
        short_answer,
        question_type=question_type,
        morphosyntax=morph,
        named_entities=named_entities,
        syntagms=syntagms,
    )
    detail_clean = clean_detailed_report(detailed_report)
    return short_clean, detail_clean


async def generate_rag_answer(
    llm: UnifiedLLMWrapper,
    *,
    system_prompt: str,
    user_prompt: str,
    language: str = "en",
    question_type: str = "other",
    runner: Any | None = None,
) -> tuple[str, str]:
    """Run the unique QA prompt through the LLM and clean structured output."""
    prompt_cfg = load_prompt_language_block(language)
    unavailable = str(
        prompt_cfg.get("unavailable_answer")
        or "The information is not available."
    )
    raw = await llm.generate(
        user_prompt, system=system_prompt or None, temperature=0.1
    )
    short_answer, detailed = parse_structured_generation(
        raw, unavailable_answer=unavailable
    )
    short_answer, detailed = clean_generated_answers(
        short_answer,
        detailed,
        question_type=question_type,
        runner=runner,
        language=language,
    )
    if not short_answer:
        short_answer = unavailable
    return short_answer, detailed


async def answer_from_passages(
    query_id: str,
    query: str,
    passages: list[PassageHit],
    *,
    llm: UnifiedLLMWrapper,
    runner: Any | None,
    language: str = "en",
    forge_prompt: bool = False,
    use_reasoner: bool = True,
    use_ontology: bool = True,
) -> RagAnswerResult:
    """Oracle evidence → unique ontology-grounded QA prompt → one LLM call.

    ``forge_prompt`` is opt-in and discouraged: the unique prompt is built
    deterministically from question type + merged query/passage ontology.
    ``use_ontology`` / ``use_reasoner`` default from ``rag.yaml``
    ``answer_generation`` when callers pass the resolved flags.
    """
    try:
        if runner is not None:
            analysis = analyze_request(query, runner=runner, language=language)
        else:
            analysis = {"raw_query": query, "language": language}

        question_type = detect_question_type(query, analysis)
        focus_passages, structured_facts, _legacy_note, passage_docs = (
            structure_passages(
                query,
                passages,
                analysis=analysis,
                runner=runner,
                language=language,
                use_reasoner=False,
            )
        )
        from thot.tasks.answer_generation.ontology_clues import (
            OntologyClueBundle,
            build_ontology_clues,
            ensure_pipeline_document,
            format_clues_for_prompt,
        )

        ontology_facts = ""
        reasoner_note = ""
        sparql_clues = ""
        clue_bundle = OntologyClueBundle()

        if use_ontology:
            query_document = analysis.get("_pipeline_doc")
            if isinstance(query_document, dict):
                query_document = ensure_pipeline_document(
                    query_document, source_id="query", text=query
                )
            else:
                query_document = None

            clue_bundle = build_ontology_clues(
                query=query,
                analysis=analysis,
                query_document=query_document,
                passage_documents=passage_docs,
                use_reasoner=use_reasoner,
            )
            ontology_facts = format_clues_for_prompt(clue_bundle)
            # Keep lightweight SVO merge as fallback when document_ontology is empty.
            if (
                not clue_bundle.passage_graph_count
                or ontology_facts.startswith("(no ")
            ):
                fallback_facts, fallback_note = build_query_passage_ontology(
                    analysis,
                    structured_facts,
                    use_reasoner=use_reasoner,
                )
                ontology_facts = fallback_facts
                reasoner_note = fallback_note
                sparql_clues = ""
            else:
                reasoner_note = clue_bundle.reasoner_note
                sparql_clues = clue_bundle.sparql_clues

        system_prompt, user_prompt = build_rag_prompts(
            query=query,
            analysis=analysis,
            focus_passages=focus_passages,
            structured_facts=structured_facts,
            reasoner_note=reasoner_note,
            language=language,
            ontology_facts=ontology_facts,
            sparql_clues=sparql_clues,
            question_type=question_type,
        )
        forged = False
        if forge_prompt:
            # Optional legacy path; unique prompt is preferred.
            user_prompt = await forge_prompt_with_llm(
                llm,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                query=query,
                analysis=analysis,
                focus_passages=focus_passages,
                structured_facts=structured_facts,
                question_type=question_type,
                language=language,
            )
            forged = True
        short_answer, detailed = await generate_rag_answer(
            llm,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            language=language,
            question_type=question_type,
            runner=runner,
        )
        return RagAnswerResult(
            query_id=query_id,
            query=query,
            short_answer=short_answer,
            detailed_report=detailed,
            input_prompt=format_input_prompt(system_prompt, user_prompt),
            forged=forged,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            question_type=question_type,
            query_analysis=analysis,
            structured_facts=structured_facts,
            focus_passages=focus_passages,
            reasoner_note=reasoner_note or ontology_facts[:500],
            sparql_queries=list(clue_bundle.sparql_queries),
            sparql_clues=sparql_clues,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("RAG answer failed for %s", query_id)
        return RagAnswerResult(
            query_id=query_id,
            query=query,
            short_answer="",
            detailed_report="",
            input_prompt="",
            error=str(exc),
        )


def tokenize_answer(text: str) -> list[str]:
    """Lowercase alphanumeric tokens for F1 scoring."""
    return _TOKEN_RE.findall((text or "").lower())


def token_f1(prediction: str, gold: str) -> float:
    """Token-level F1 between prediction and gold answer."""
    pred = tokenize_answer(prediction)
    ref = tokenize_answer(gold)
    if not pred and not ref:
        return 1.0
    if not pred or not ref:
        return 0.0
    pred_counts: dict[str, int] = {}
    ref_counts: dict[str, int] = {}
    for token in pred:
        pred_counts[token] = pred_counts.get(token, 0) + 1
    for token in ref:
        ref_counts[token] = ref_counts.get(token, 0) + 1
    overlap = sum(
        min(pred_counts[token], ref_counts[token])
        for token in pred_counts
        if token in ref_counts
    )
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred)
    recall = overlap / len(ref)
    return 2 * precision * recall / (precision + recall)


def normalized_em(prediction: str, gold: str) -> float:
    """Normalized exact match (whitespace/case folded)."""
    left = " ".join(tokenize_answer(prediction))
    right = " ".join(tokenize_answer(gold))
    if not left and not right:
        return 1.0
    return 1.0 if left == right else 0.0


def answer_contains_gold(prediction: str, gold: str) -> float:
    """1.0 when gold token sequence appears in the prediction."""
    left = " ".join(tokenize_answer(prediction))
    right = " ".join(tokenize_answer(gold))
    if not right:
        return 0.0
    return 1.0 if right in left else 0.0


def build_llm_wrapper() -> UnifiedLLMWrapper:
    """Construct ``UnifiedLLMWrapper`` from env + ``rag.yaml`` models."""
    rag = load_rag_config()
    file_models = {
        "embedding_model": rag.models.embedding_model,
        "llm_model": rag.models.llm_model,
        "embedding_dim": rag.models.embedding_dim,
        "rerank_strategy": rag.search.rerank.strategy,
    }
    return UnifiedLLMWrapper(WrapperConfig.from_env(file_models=file_models))
