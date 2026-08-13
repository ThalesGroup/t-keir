"""Title: Wiki knowledge graph — SVO + facts fused with business ontology.

Display graph is intentionally small and wiki-focused:
  1. Subject–verb–object triples from the live wiki (Answer / Evidence / Timeline)
  2. Structured facts from the wiki (and light chunk fill-in)
  3. Matched business-ontology concepts that appear in wiki text (focus only)

Full BO catalog JSON-LD is kept under ``business_ontology_json_ld`` but is
never the display ``json_ld``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

LOGGER = logging.getLogger(__name__)

_PIPELINE_RUNNER: Any = None
_PIPELINE_LOCK = __import__("threading").Lock()
_MAX_PIPELINE_CHARS = 6000
_MAX_CHUNK_TEXTS = 6
_MAX_DISPLAY_ENTITIES = 36
_MAX_DISPLAY_RELATIONS = 48
_MAX_BO_SUPPORT_RELATIONS = 12
_BO_SUPPORT_PREDICATES = frozenset(
    {"rel:broader", "broader", "rel:related_to", "related_to", "related"}
)
_WIKI_SECTION_NAMES = (
    "Answer",
    "Evidence",
    "Structured facts",
    "Timeline",
)
_FACT_LINE_RE = re.compile(
    r"(?m)^\s*(?:[-*•]|\d+[.)])?\s*" r"([^:\n|]{2,80}?)\s*[:=|–—]\s*(.+?)\s*$"
)
_BULLET_FACT_RE = re.compile(r"(?m)^\s*[-*•]\s+(.{8,200})$")
_SKIP_BO_PREDICATES = frozenset(
    {
        "rel:has_concept",
        "has_concept",
        "rel:in_scheme",
        "in_scheme",
        "rel:document",
        "document",
    }
)
_HEADING_RE = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)
_TITLE_CASE_RE = re.compile(
    r"\b([A-Z][a-zA-Z0-9]+(?:[ \t]+[A-Z][a-zA-Z0-9]+){0,4})\b"
)
_SIMPLE_SVO_RE = re.compile(
    r"(?m)\b([A-Z][\w'-]{1,40}(?:\s+[A-Z][\w'-]{1,40}){0,3})\s+"
    r"(is|are|was|were|has|have|had|announced|reported|attacked|"
    r"launched|signed|blocked|seized|warned|accused|claimed|"
    r"deployed|struck|killed|injured|captured|released)\s+"
    r"([A-Za-z][\w'-]{1,40}(?:\s+[A-Za-z][\w'-]{1,40}){0,4})",
)


def _parse_graph_nodes(doc_ont: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract DefinedTerm-like nodes from document_ontology.json_ld.

        Example:
            >>> True
            True
    """
    raw = doc_ont.get("json_ld")
    if isinstance(raw, str) and raw.strip():
        try:
            import json

            parsed = json.loads(raw)
        except Exception:  # noqa: BLE001
            return []
    elif isinstance(raw, dict):
        parsed = raw
    elif isinstance(raw, list):
        return [n for n in raw if isinstance(n, dict)]
    else:
        return []
    if isinstance(parsed, list):
        return [n for n in parsed if isinstance(n, dict)]
    if isinstance(parsed, dict):
        graph = parsed.get("@graph") or parsed.get("graph") or []
        if isinstance(graph, list):
            return [n for n in graph if isinstance(n, dict)]
        return [parsed]
    return []


def normalize_business_ontology_payload(raw: Any) -> dict[str, Any] | None:
    """
    Normalize YAML text / dict / concepts list into ``{concepts: [...]}``.

        Example:
            >>> True
            True
    """
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            loaded = yaml.safe_load(text)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("business_ontology YAML parse failed: %s", exc)
            return None
        raw = loaded
    if isinstance(raw, list):
        concepts = [
            c for c in raw if isinstance(c, dict) and c.get("concept_id")
        ]
        return {"concepts": concepts} if concepts else None
    if isinstance(raw, dict):
        concepts_raw = raw.get("concepts")
        if isinstance(concepts_raw, list) and concepts_raw:
            return {
                "concepts": [
                    c
                    for c in concepts_raw
                    if isinstance(c, dict) and c.get("concept_id")
                ]
            }
    return None


def load_business_ontology_file(path: str | Path) -> dict[str, Any] | None:
    """
    Load a business_ontology YAML/JSON file from disk.

        Example:
            >>> True
            True
    """
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return normalize_business_ontology_payload(
            p.read_text(encoding="utf-8")
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("failed to load business ontology %s: %s", p, exc)
        return None


def resolve_osiris_business_ontology(
    *,
    request_payload: Any = None,
    request_yaml: str | None = None,
    osiris_base_url: str | None = None,
) -> dict[str, Any] | None:
    """
    Resolve BO from request body, env path, or Osiris ``/api/tkeir/ontology``.

        Priority:
          1. ``request_payload`` (already parsed ``{concepts}``)
          2. ``request_yaml`` (raw YAML text)
          3. ``COLLECTOR_BUSINESS_ONTOLOGY`` / ``OSIRIS_ONTOLOGY_PATH`` file
          4. GET ``{OSIRIS_BASE_URL}/api/tkeir/ontology`` (yaml or json)

        Example:
            >>> True
            True
    """
    for candidate in (request_payload, request_yaml):
        normalized = normalize_business_ontology_payload(candidate)
        if normalized:
            return normalized

    for env_key in ("COLLECTOR_BUSINESS_ONTOLOGY", "OSIRIS_ONTOLOGY_PATH"):
        path = os.getenv(env_key, "").strip()
        if path:
            loaded = load_business_ontology_file(path)
            if loaded:
                return loaded

    base = str(osiris_base_url or os.getenv("OSIRIS_BASE_URL") or "").rstrip(
        "/"
    )
    if not base:
        return None
    try:
        import httpx

        with httpx.Client(timeout=8.0, follow_redirects=True) as client:
            res = client.get(
                f"{base}/api/tkeir/ontology",
                headers={"Accept": "application/json, text/yaml, text/plain"},
            )
            if res.status_code >= 400:
                return None
            ctype = (res.headers.get("content-type") or "").lower()
            if "json" in ctype:
                return normalize_business_ontology_payload(res.json())
            return normalize_business_ontology_payload(res.text)
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("osiris ontology fetch failed: %s", exc)
        return None


def _coverage_from_annotation(
    ontology_payload: dict[str, Any],
    annotated: dict[str, Any],
    *,
    haystack: str,
) -> dict[str, Any]:
    """
    Build HMI-like coverage (matched / missing / ratio) from annotate result.

        Example:
            >>> True
            True
    """
    from thot.tools.search.business_ontology import (
        _label_hits_haystack,
        _normalize_for_ontology_match,
        _ontology_match_labels,
    )

    concepts = [
        c
        for c in ontology_payload.get("concepts") or []
        if isinstance(c, dict) and c.get("concept_id")
    ]
    hay = _normalize_for_ontology_match(haystack or "")
    matched: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    # Prefer concept ids stamped by annotate (KG / core_concepts).
    stamped: set[str] = set()
    for cid in annotated.get("core_concepts") or []:
        if isinstance(cid, dict):
            cid = cid.get("concept_id") or cid.get("identifier")
        if cid:
            stamped.add(str(cid).strip())
    for triple in annotated.get("kg") or []:
        if not isinstance(triple, dict):
            continue
        if str(triple.get("provenance") or "").lower() != "external":
            continue
        prop = triple.get("property") or {}
        pred = str(
            prop.get("content") if isinstance(prop, dict) else prop or ""
        )
        if pred != "rel:has_concept":
            continue
        val = triple.get("value") or {}
        cid = str(
            val.get("content") if isinstance(val, dict) else val or ""
        ).strip()
        if cid:
            stamped.add(cid)
    doc_ont = annotated.get("document_ontology") or {}
    for path_row in doc_ont.get("ontology_paths") or []:
        if isinstance(path_row, dict) and path_row.get("concept_id"):
            stamped.add(str(path_row["concept_id"]).strip())
    for node in _parse_graph_nodes(doc_ont):
        if str(node.get("provenance") or "").lower() != "external":
            continue
        if (
            not node.get("matched_in_text")
            and node.get("role") != "matched_term"
        ):
            continue
        cid = str(node.get("identifier") or "").strip()
        if cid:
            stamped.add(cid)

    for raw in concepts:
        cid = str(raw.get("concept_id") or "").strip()
        preferred = str(raw.get("preferred_label") or cid).strip()
        surfaces = _ontology_match_labels(raw, cid)
        hit = cid in stamped
        if not hit and hay:
            for label in surfaces:
                if _label_hits_haystack(label, hay):
                    hit = True
                    break
        row = {
            "conceptId": cid,
            "preferredLabel": preferred,
            "surfaces": surfaces[:12],
        }
        if hit:
            matched.append(row)
        else:
            missing.append(row)

    total = len(concepts)
    m = len(matched)
    return {
        "total": total,
        "matched": m,
        "ratio": (m / total) if total else 0.0,
        "matchedConcepts": matched,
        "missingConcepts": missing,
    }


def _kg_node_text(node: Any) -> str:
    """
    Flatten a KG / SVO node to a display string.

        Example:
            >>> True
            True
    """
    if node is None:
        return ""
    if isinstance(node, str):
        return node.strip()
    if not isinstance(node, dict):
        return str(node).strip()
    for key in ("label", "text", "content", "lemma_content"):
        val = node.get(key)
        if isinstance(val, list):
            joined = " ".join(str(x).strip() for x in val if str(x).strip())
            if joined:
                return joined
        elif val:
            return str(val).strip()
    return ""


def _clean_predicate(raw: str) -> str:
    """
    Normalize predicate for graph display (strip ``rel:``).

        Example:
            >>> True
            True
    """
    pred = (raw or "").strip()
    if pred.lower().startswith("rel:"):
        pred = pred[4:]
    return pred.replace("_", " ").strip() or "related"


def _collector_pipeline_runner():
    """
    Lazy shared PipelineRunner for wiki NLP (best-effort).

        Example:
            >>> True
            True
    """
    global _PIPELINE_RUNNER
    if _PIPELINE_RUNNER is not None:
        return _PIPELINE_RUNNER
    with _PIPELINE_LOCK:
        if _PIPELINE_RUNNER is not None:
            return _PIPELINE_RUNNER
        try:
            from thot.core.TkeirPaths import configs_dir
            from thot.tasks.pipeline.PipelineConfiguration import (
                PipelineConfiguration,
            )
            from thot.tasks.pipeline.PipelineRunner import PipelineRunner

            config = PipelineConfiguration()
            with open(
                os.path.join(configs_dir(), "pipeline.yaml"),
                encoding="utf-8",
            ) as handle:
                config.load(handle)
            _PIPELINE_RUNNER = PipelineRunner(config)
            LOGGER.info("Loaded PipelineRunner for collector wiki ontology")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Wiki PipelineRunner unavailable: %s", exc)
            _PIPELINE_RUNNER = False
    return _PIPELINE_RUNNER if _PIPELINE_RUNNER is not False else None


def _analyze_text_pipeline(
    text: str, *, language: str | None = None
) -> dict[str, Any]:
    """
    Run NLP on one text blob; return ner / svo / keywords / kg.

        Example:
            >>> True
            True
    """
    blob = (text or "").strip()
    empty = {
        "ner_entities": [],
        "svo_triples": [],
        "keywords": [],
        "kg": [],
        "source": "none",
    }
    if len(blob) < 8:
        return empty
    blob = blob[:_MAX_PIPELINE_CHARS]
    runner = _collector_pipeline_runner()
    if not runner:
        return empty
    try:
        from thot.tools.search.query_analyzer import (
            analyze_query_document,
            run_linguistic_pipeline,
        )
        from thot.tools.search.rag_config import RagSearchConfig

        processed = run_linguistic_pipeline(runner, blob, language=language)
        analysis = analyze_query_document(
            processed,
            blob[:240],
            language=language,
            config=RagSearchConfig(),
        )
        return {
            "ner_entities": [
                {"text": e.text, "label": e.label}
                for e in analysis.ner_entities or []
            ],
            "svo_triples": [
                {
                    "subject": t.subject,
                    "verb": t.verb,
                    "object": t.object,
                }
                for t in analysis.svo_triples or []
            ],
            "keywords": list(analysis.keywords or []),
            "kg": list(processed.get("kg") or []),
            "source": "pipeline",
        }
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("wiki NLP analyze failed: %s", exc)
        return empty


def _fallback_extract_signals(
    wiki_markdown: str,
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Heuristic NER / SVO / keywords when PipelineRunner is unavailable.

        Example:
            >>> True
            True
    """
    titles = [
        str(c.get("title") or "").strip() for c in chunks if c.get("title")
    ]
    headings = [
        m.group(1).strip() for m in _HEADING_RE.finditer(wiki_markdown or "")
    ]
    # Prefer per-sentence / per-paragraph scans so headings don't glue into SVO.
    text_parts = [
        wiki_markdown or "",
        "\n".join(titles),
        "\n".join(
            str(c.get("text_raw") or "")[:800]
            for c in chunks[:_MAX_CHUNK_TEXTS]
        ),
    ]
    hay = "\n".join(text_parts)
    ner: list[dict[str, Any]] = []
    seen_ner: set[str] = set()
    for label in titles + headings:
        key = label.casefold()
        if len(label) < 3 or key in seen_ner:
            continue
        seen_ner.add(key)
        ner.append({"text": label, "label": "Work"})
    for match in _TITLE_CASE_RE.finditer(hay):
        label = match.group(1).strip()
        key = label.casefold()
        if len(label) < 3 or key in seen_ner:
            continue
        if label.lower() in {
            "the",
            "and",
            "for",
            "with",
            "from",
            "this",
            "that",
            "updated",
            "events",
            "source",
            "sources",
        }:
            continue
        seen_ner.add(key)
        ner.append({"text": label, "label": "Entity"})
        if len(ner) >= 80:
            break

    svo: list[dict[str, Any]] = []
    seen_svo: set[tuple[str, str, str]] = set()
    for paragraph in re.split(r"[\n.]+", hay):
        paragraph = paragraph.strip()
        if len(paragraph) < 8:
            continue
        for match in _SIMPLE_SVO_RE.finditer(paragraph):
            subj, verb, obj = (
                match.group(1).strip(),
                match.group(2).strip().lower(),
                match.group(3).strip(),
            )
            if "\n" in subj or "\n" in obj:
                continue
            key = (subj.casefold(), verb, obj.casefold())
            if key in seen_svo or len(subj) < 2 or len(obj) < 2:
                continue
            seen_svo.add(key)
            svo.append({"subject": subj, "verb": verb, "object": obj})
            if len(svo) >= 60:
                break
        if len(svo) >= 60:
            break

    keywords: list[str] = []
    seen_kw: set[str] = set()
    for label in titles + headings + [e["text"] for e in ner[:24]]:
        key = label.casefold()
        if key in seen_kw or len(label) < 3:
            continue
        seen_kw.add(key)
        keywords.append(label)

    return {
        "ner_entities": ner,
        "svo_triples": svo,
        "keywords": keywords[:48],
        "kg": [],
        "source": "heuristic",
    }


def _merge_pipeline_signals(*parts: dict[str, Any]) -> dict[str, Any]:
    """
    Union ner / svo / keywords across analysis passes.

        Example:
            >>> True
            True
    """
    ner: list[dict[str, Any]] = []
    svo: list[dict[str, Any]] = []
    keywords: list[str] = []
    kg: list[dict[str, Any]] = []
    seen_ner: set[str] = set()
    seen_svo: set[tuple[str, str, str]] = set()
    seen_kw: set[str] = set()
    sources: list[str] = []

    for part in parts:
        if not part:
            continue
        src = str(part.get("source") or "")
        if src and src not in sources:
            sources.append(src)
        for ent in part.get("ner_entities") or []:
            if not isinstance(ent, dict):
                continue
            text = str(ent.get("text") or "").strip()
            if len(text) < 2:
                continue
            ner_key = text.casefold()
            if ner_key in seen_ner:
                continue
            seen_ner.add(ner_key)
            ner.append(
                {
                    "text": text,
                    "label": str(ent.get("label") or "Entity"),
                }
            )
        for triple in part.get("svo_triples") or []:
            if not isinstance(triple, dict):
                continue
            subj = str(triple.get("subject") or "").strip()
            verb = str(triple.get("verb") or "").strip()
            obj = str(triple.get("object") or "").strip()
            if not subj or not verb:
                continue
            svo_key = (subj.casefold(), verb.casefold(), obj.casefold())
            if svo_key in seen_svo:
                continue
            seen_svo.add(svo_key)
            svo.append({"subject": subj, "verb": verb, "object": obj})
        for kw in part.get("keywords") or []:
            label = (
                str(kw).strip()
                if not isinstance(kw, dict)
                else str(kw.get("text") or kw.get("label") or "").strip()
            )
            if len(label) < 2:
                continue
            kw_key = label.casefold()
            if kw_key in seen_kw:
                continue
            seen_kw.add(kw_key)
            keywords.append(label)
        for triple in part.get("kg") or []:
            if isinstance(triple, dict):
                kg.append(triple)

    return {
        "ner_entities": ner,
        "svo_triples": svo,
        "keywords": keywords,
        "kg": kg,
        "source": "+".join(sources) if sources else "none",
    }


def _wiki_core_text(wiki_markdown: str) -> str:
    """
    Answer / Evidence / Structured facts / Timeline only (drop Sources noise).

        Example:
            >>> True
            True
    """
    md = (wiki_markdown or "").strip()
    if not md:
        return ""
    blocks: list[str] = []
    for name in _WIKI_SECTION_NAMES:
        pattern = re.compile(
            rf"(?is)^##\s*{re.escape(name)}\s*\n(.*?)(?=^##\s|\Z)",
            re.MULTILINE,
        )
        match = pattern.search(md)
        if match:
            body = (match.group(1) or "").strip()
            if body:
                blocks.append(f"## {name}\n{body}")
    return "\n\n".join(blocks) if blocks else md[:_MAX_PIPELINE_CHARS]


def _facts_from_wiki(wiki_markdown: str) -> list[dict[str, Any]]:
    """
    Parse Structured facts / Evidence bullets into simple fact triples.

        Example:
            >>> True
            True
    """
    md = _wiki_core_text(wiki_markdown)
    facts: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(subj: str, pred: str, obj: str) -> None:
        s = re.sub(r"\s+", " ", (subj or "").strip(" -*•"))
        p = re.sub(r"\s+", " ", (pred or "").strip().lower()) or "fact"
        o = re.sub(r"\s+", " ", (obj or "").strip(" -*•"))
        if len(s) < 2 or len(o) < 2:
            return
        if len(s) > 72 or len(o) > 120:
            return
        key = (s.casefold(), p.casefold(), o.casefold())
        if key in seen:
            return
        seen.add(key)
        facts.append(
            {
                "subject": s,
                "verb": p,
                "object": o,
                "kind": "fact",
            }
        )

    # Key: value / Key — value lines (Structured facts)
    for match in _FACT_LINE_RE.finditer(md):
        left, right = match.group(1).strip(), match.group(2).strip()
        # Skip markdown table separators and section noise
        if set(left) <= {"-", "=", "|"} or set(right) <= {"-", "=", "|"}:
            continue
        if left.lower() in {"source", "sources", "url", "link"}:
            continue
        # Timeline-style "2024-01-01: ..." → event on date
        if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", left):
            _add(right[:72], "on", left)
        else:
            _add(left, "is", right)
        if len(facts) >= 40:
            break

    # Evidence bullets that look like short claims (SVO-ish)
    if len(facts) < 24:
        for match in _BULLET_FACT_RE.finditer(md):
            line = match.group(1).strip()
            if ":" in line or "—" in line or "–" in line:
                continue
            svo_match = _SIMPLE_SVO_RE.search(line)
            if not svo_match:
                continue
            _add(
                svo_match.group(1),
                svo_match.group(2).lower(),
                svo_match.group(3),
            )
            if len(facts) >= 40:
                break

    return facts


def _extract_pipeline_signals(
    wiki_markdown: str,
    chunks: list[dict[str, Any]],
    *,
    language: str | None = None,
) -> dict[str, Any]:
    """
    Wiki-first NLP: core wiki sections, then a few chunk fill-ins.

        Example:
            >>> True
            True
    """
    parts: list[dict[str, Any]] = []
    wiki_blob = _wiki_core_text(wiki_markdown)
    if wiki_blob:
        parts.append(_analyze_text_pipeline(wiki_blob, language=language))
    # Light chunk fill-in only (titles + short text) so graph stays clear.
    for ch in chunks[:_MAX_CHUNK_TEXTS]:
        text = " ".join(
            [
                str(ch.get("title") or "").strip(),
                str(ch.get("text_raw") or "").strip()[:900],
            ]
        ).strip()
        if len(text) >= 12:
            parts.append(_analyze_text_pipeline(text, language=language))
    merged = _merge_pipeline_signals(*parts)
    facts = _facts_from_wiki(wiki_markdown)
    if facts:
        # Facts stay separate; only lift short labels into NER/keywords.
        merged = _merge_pipeline_signals(
            merged,
            {
                "ner_entities": (
                    [
                        {"text": f["subject"], "label": "Fact"}
                        for f in facts[:20]
                    ]
                    + [
                        {"text": f["object"], "label": "Fact"}
                        for f in facts[:20]
                        if len(str(f.get("object") or "")) < 48
                    ]
                ),
                "svo_triples": [],
                "keywords": [f["subject"] for f in facts[:16]],
                "kg": [],
                "source": "wiki_facts",
            },
        )
    # Heuristic titles/headings as last resort when NLP is thin.
    heuristic = _fallback_extract_signals(
        wiki_blob or wiki_markdown, chunks[:4]
    )
    merged = _merge_pipeline_signals(merged, heuristic)
    merged["facts"] = facts
    return merged


def _relations_from_svo(
    svo_triples: list[dict[str, Any]],
    *,
    weight: float = 8.0,
) -> list[dict[str, Any]]:
    """
    Convert SVO triples into HMI display relations (pipeline primary).

        Example:
            >>> True
            True
    """
    relations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for triple in svo_triples:
        source = str(triple.get("subject") or "").strip()
        predicate = _clean_predicate(str(triple.get("verb") or ""))
        target = str(triple.get("object") or "").strip()
        if not source or not predicate:
            continue
        key = (source.casefold(), predicate.casefold(), target.casefold())
        if key in seen:
            continue
        seen.add(key)
        relations.append(
            {
                "source": source,
                "predicate": predicate,
                "target": target,
                "weight": weight,
                "provenance": "document",
            }
        )
    return relations


def _relations_from_kg_document(
    kg: list[dict[str, Any]],
    *,
    weight: float = 7.0,
) -> list[dict[str, Any]]:
    """
    Take non-external KG triples (pipeline document provenance).

        Example:
            >>> True
            True
    """
    relations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for triple in kg:
        if not isinstance(triple, dict):
            continue
        prov = str(triple.get("provenance") or "document").lower()
        if prov == "external":
            continue
        source = _kg_node_text(triple.get("subject"))
        predicate = _clean_predicate(_kg_node_text(triple.get("property")))
        target = _kg_node_text(triple.get("value"))
        if not source or not predicate:
            continue
        pred_norm = predicate.lower().replace(" ", "_")
        if pred_norm in {p.replace("rel:", "") for p in _SKIP_BO_PREDICATES}:
            continue
        key = (source.casefold(), predicate.casefold(), target.casefold())
        if key in seen:
            continue
        seen.add(key)
        relations.append(
            {
                "source": source,
                "predicate": predicate,
                "target": target,
                "weight": weight,
                "provenance": "document",
            }
        )
    return relations


def _bo_support_relations(
    annotated_kg: list[Any],
    coverage: dict[str, Any],
    *,
    weight: float = 1.25,
) -> list[dict[str, Any]]:
    """
    Light BO edges among matched concepts only (never catalog flood).

        Example:
            >>> True
            True
    """
    by_id = {
        c["conceptId"]: c["preferredLabel"]
        for c in coverage.get("matchedConcepts") or []
        if c.get("conceptId") and c.get("preferredLabel")
    }
    matched_labels = {
        str(c.get("preferredLabel") or "").casefold()
        for c in coverage.get("matchedConcepts") or []
        if c.get("preferredLabel")
    }
    matched_ids = set(by_id)
    if not matched_ids:
        return []

    relations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for triple in annotated_kg or []:
        if not isinstance(triple, dict):
            continue
        if str(triple.get("provenance") or "").lower() != "external":
            continue
        pred_raw = _kg_node_text(triple.get("property"))
        pred_key = pred_raw.strip().lower()
        if pred_key in _SKIP_BO_PREDICATES:
            continue
        if pred_key not in _BO_SUPPORT_PREDICATES and not any(
            pred_key.endswith(p.replace("rel:", ""))
            for p in _BO_SUPPORT_PREDICATES
        ):
            continue
        source = _kg_node_text(triple.get("subject"))
        target = _kg_node_text(triple.get("value"))
        source = by_id.get(source, source)
        target = by_id.get(target, target)
        if not source or not target:
            continue
        # Keep only edges that touch matched BO labels.
        if (
            source.casefold() not in matched_labels
            and target.casefold() not in matched_labels
            and source not in matched_ids
            and target not in matched_ids
        ):
            continue
        predicate = _clean_predicate(pred_raw)
        key = (source.casefold(), predicate.casefold(), target.casefold())
        if key in seen:
            continue
        seen.add(key)
        relations.append(
            {
                "source": source,
                "predicate": predicate,
                "target": target,
                "weight": weight,
                "provenance": "external",
            }
        )
    return relations[:_MAX_BO_SUPPORT_RELATIONS]


def _entities_from_pipeline(
    signals: dict[str, Any],
    *,
    chunk_ids: list[str] | None = None,
    max_entities: int = _MAX_DISPLAY_ENTITIES,
) -> list[dict[str, Any]]:
    """
    Build a small entity set from SVO participants + facts + light NER.

        Example:
            >>> True
            True
    """
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()
    cids = [c for c in chunk_ids or [] if c][:12]

    def _add(label: str, etype: str, weight: float) -> None:
        lab = re.sub(r"\s+", " ", (label or "").strip())
        if len(lab) < 2 or len(lab) > 72:
            return
        key = lab.casefold()
        if key in seen:
            return
        seen.add(key)
        entities.append(
            {
                "label": lab,
                "type": etype,
                "weight": weight,
                "chunk_ids": list(cids),
                "provenance": "document",
            }
        )

    # Prefer fact / SVO participants so the graph reads as claims, not catalog.
    for fact in signals.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        _add(str(fact.get("subject") or ""), "Fact", 20.0)
        obj = str(fact.get("object") or "")
        if len(obj) <= 48:
            _add(obj, "Fact", 16.0)
    for triple in signals.get("svo_triples") or []:
        _add(str(triple.get("subject") or ""), "Entity", 18.0)
        obj = str(triple.get("object") or "")
        if len(obj) <= 56:
            _add(obj, "Entity", 14.0)
    for ent in signals.get("ner_entities") or []:
        if len(entities) >= max_entities:
            break
        _add(
            str(ent.get("text") or ""), str(ent.get("label") or "Entity"), 10.0
        )
    for kw in signals.get("keywords") or []:
        if len(entities) >= max_entities:
            break
        _add(str(kw), "Keyword", 6.0)

    entities.sort(key=lambda e: float(e.get("weight") or 0), reverse=True)
    return entities[:max_entities]


def _cap_relations(
    relations: list[dict[str, Any]],
    *,
    max_relations: int = _MAX_DISPLAY_RELATIONS,
    known_labels: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Keep high-weight edges; optionally require endpoints in entity set.

        Example:
            >>> True
            True
    """
    known = known_labels or set()

    def _ok(rel: dict[str, Any]) -> bool:
        if not known:
            return True
        src = str(rel.get("source") or "").casefold()
        tgt = str(rel.get("target") or "").casefold()
        # Allow missing target for unary claims, but prefer both ends known.
        if src not in known:
            return False
        if tgt and tgt not in known:
            return False
        return True

    ranked = sorted(
        (r for r in relations if _ok(r)),
        key=lambda r: float(r.get("weight") or 0),
        reverse=True,
    )
    return ranked[:max_relations]


def _keywords_from_pipeline(signals: dict[str, Any]) -> list[dict[str, Any]]:
    """
    HMI keyword rows from pipeline keywords (+ thin NER fallback).

        Example:
            >>> True
            True
    """
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for kw in signals.get("keywords") or []:
        label = str(kw).strip()
        key = label.casefold()
        if len(label) < 2 or key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "label": label,
                "weight": 6.0,
                "chunk_ids": [],
                "provenance": "document",
            }
        )
    for ent in signals.get("ner_entities") or []:
        label = str(ent.get("text") or "").strip()
        key = label.casefold()
        if len(label) < 2 or key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "label": label,
                "weight": 4.0,
                "chunk_ids": [],
                "provenance": "document",
            }
        )
    return rows[:80]


def _json_ld_from_pipeline(
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    *,
    topic: str,
) -> str:
    """
    Compact JSON-LD graph from pipeline entities/relations (no BO catalog).

        Example:
            >>> True
            True
    """
    graph: list[dict[str, Any]] = []
    id_by_label: dict[str, str] = {}
    emitted: set[str] = set()

    def _nid(label: str) -> str:
        key = label.casefold()
        if key in id_by_label:
            return id_by_label[key]
        nid = f"urn:pipeline:{len(id_by_label) + 1}"
        id_by_label[key] = nid
        return nid

    def _ensure_node(label: str, etype: str = "Thing") -> str:
        key = label.casefold()
        nid = _nid(label)
        if key not in emitted:
            emitted.add(key)
            graph.append(
                {
                    "@id": nid,
                    "@type": etype,
                    "name": label,
                    "provenance": "document",
                }
            )
        return nid

    for ent in entities:
        label = str(ent.get("label") or "").strip()
        if not label:
            continue
        if str(ent.get("provenance") or "").lower() == "external":
            # BO support labels stay as preferred focus, not catalog nodes.
            continue
        _ensure_node(label, str(ent.get("type") or "Thing"))

    for rel in relations:
        if str(rel.get("provenance") or "").lower() == "external":
            continue
        source = str(rel.get("source") or "").strip()
        target = str(rel.get("target") or "").strip()
        predicate = str(rel.get("predicate") or "related").strip()
        if not source or not target:
            continue
        sid = _ensure_node(source)
        tid = _ensure_node(target)
        graph.append(
            {
                "@id": f"urn:pipeline:edge:{len(graph) + 1}",
                "@type": "Relationship",
                "subject": sid,
                "predicate": predicate,
                "object": tid,
                "name": f"{source} {predicate} {target}",
                "provenance": "document",
            }
        )

    payload = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": f"OSIRIS wiki knowledge graph ({topic})",
        "@graph": graph,
    }
    return json.dumps(payload, ensure_ascii=False)


def apply_business_ontology_to_wiki(
    *,
    wiki_markdown: str,
    chunks: list[dict[str, Any]],
    ontology_payload: dict[str, Any],
    topic: str = "osiris-live",
) -> dict[str, Any]:
    """
    Build a simple wiki knowledge graph: SVO + facts, fused with BO.

        Display priority (small & clear):
          1. Wiki Structured facts
          2. Wiki / chunk SVO triples
          3. Document KG triples (non-external)
          4. Matched BO concepts that appear in wiki text (focus markers)
          5. Sparse BO broader/related edges among those matches only

        Full BO catalog stays under ``business_ontology_json_ld`` only.

        Example:
            >>> True
            True
    """
    from thot.tools.search.business_ontology import (
        annotate_document_with_business_ontology,
        business_ontology_to_json_ld,
    )

    wiki_core = _wiki_core_text(wiki_markdown)
    chunk_blobs = []
    for ch in chunks:
        chunk_blobs.append(
            {
                "chunk_id": ch.get("chunk_id"),
                "text_raw": ch.get("text_raw") or "",
                "title": ch.get("title") or "",
                "search_vector_payload": ch.get("text_raw") or "",
            }
        )
    document: dict[str, Any] = {
        "title": f"OSIRIS live wiki ({topic})",
        "content": [wiki_core or wiki_markdown or ""],
        "golden_chunks": chunk_blobs,
        "source_doc_id": f"osiris-wiki:{topic}",
        "source": "tkeir-collector",
    }

    signals = _extract_pipeline_signals(wiki_markdown, chunks)
    annotated = annotate_document_with_business_ontology(
        document, ontology_payload
    )
    # BO match haystack = wiki core only (not the full chunk dump).
    haystack = wiki_core or (wiki_markdown or "")
    coverage = _coverage_from_annotation(
        ontology_payload, annotated, haystack=haystack
    )
    catalog_json_ld = business_ontology_to_json_ld(ontology_payload)
    doc_ont = annotated.get("document_ontology") or {}

    chunk_ids = [
        str(c.get("chunk_id") or "").strip()
        for c in chunks
        if c.get("chunk_id")
    ]
    entities = _entities_from_pipeline(
        signals, chunk_ids=chunk_ids, max_entities=_MAX_DISPLAY_ENTITIES
    )
    keywords = _keywords_from_pipeline(signals)

    # Matched BO concepts: only those that appear in wiki text.
    hay_cf = haystack.casefold()
    seen_ent = {str(e.get("label") or "").casefold() for e in entities}
    for c in coverage.get("matchedConcepts") or []:
        label = str(
            c.get("preferredLabel") or c.get("conceptId") or ""
        ).strip()
        if not label or label.casefold() in seen_ent:
            continue
        if label.casefold() not in hay_cf and not any(
            tok and tok in hay_cf
            for tok in re.findall(r"[a-z0-9]{4,}", label.casefold())
        ):
            continue
        seen_ent.add(label.casefold())
        entities.append(
            {
                "label": label,
                "type": "BusinessConcept",
                "weight": 5.0,
                "chunk_ids": [],
                "provenance": "external",
            }
        )
        if len(entities) >= _MAX_DISPLAY_ENTITIES + 8:
            break

    # Relations: facts (highest) → SVO → doc KG → sparse BO support
    fact_triples = [
        {
            "subject": f.get("subject"),
            "verb": f.get("verb"),
            "object": f.get("object"),
        }
        for f in signals.get("facts") or []
        if isinstance(f, dict)
    ]
    relations = _relations_from_svo(fact_triples, weight=10.0)
    for rel in relations:
        rel["provenance"] = "fact"
    relations.extend(
        _relations_from_svo(signals.get("svo_triples") or [], weight=8.0)
    )
    relations.extend(_relations_from_kg_document(signals.get("kg") or []))

    seen_rel = {
        (
            str(r.get("source") or "").casefold(),
            str(r.get("predicate") or "").casefold(),
            str(r.get("target") or "").casefold(),
        )
        for r in relations
    }
    bo_added = 0
    for rel in _bo_support_relations(annotated.get("kg") or [], coverage):
        if bo_added >= _MAX_BO_SUPPORT_RELATIONS:
            break
        key = (
            str(rel.get("source") or "").casefold(),
            str(rel.get("predicate") or "").casefold(),
            str(rel.get("target") or "").casefold(),
        )
        if key in seen_rel:
            continue
        # Only keep BO edges whose endpoints are already in the display set.
        if key[0] not in seen_ent or (key[2] and key[2] not in seen_ent):
            continue
        seen_rel.add(key)
        relations.append(rel)
        bo_added += 1

    known = {str(e.get("label") or "").casefold() for e in entities}
    # Keep fact/SVO edges even if object is long and not an entity node:
    # inject missing endpoints for top relations, then cap.
    for rel in list(relations)[:_MAX_DISPLAY_RELATIONS]:
        for end in ("source", "target"):
            lab = str(rel.get(end) or "").strip()
            if not lab or lab.casefold() in known:
                continue
            if len(lab) > 56:
                continue
            known.add(lab.casefold())
            entities.append(
                {
                    "label": lab,
                    "type": "Entity",
                    "weight": float(rel.get("weight") or 6.0),
                    "chunk_ids": list(chunk_ids[:8]),
                    "provenance": str(rel.get("provenance") or "document"),
                }
            )
    entities = entities[: _MAX_DISPLAY_ENTITIES + 12]
    known = {str(e.get("label") or "").casefold() for e in entities}
    relations = _cap_relations(
        relations, max_relations=_MAX_DISPLAY_RELATIONS, known_labels=known
    )

    display_json_ld = _json_ld_from_pipeline(
        entities, relations, topic=topic or "osiris-live"
    )

    merged_kg: list[dict[str, Any]] = []
    for triple in signals.get("kg") or []:
        if isinstance(triple, dict):
            row = dict(triple)
            row.setdefault("provenance", "document")
            merged_kg.append(row)
    for triple in fact_triples + list(signals.get("svo_triples") or []):
        if not isinstance(triple, dict):
            continue
        merged_kg.append(
            {
                "subject": {"content": triple.get("subject")},
                "property": {"content": triple.get("verb")},
                "value": {"content": triple.get("object")},
                "provenance": "document",
            }
        )
    for triple in annotated.get("kg") or []:
        if isinstance(triple, dict):
            merged_kg.append(triple)

    pipeline_rel_count = sum(
        1
        for r in relations
        if str(r.get("provenance") or "").lower() not in {"external"}
    )
    bo_rel_count = sum(
        1
        for r in relations
        if str(r.get("provenance") or "").lower() == "external"
    )
    fact_rel_count = sum(
        1
        for r in relations
        if str(r.get("provenance") or "").lower() == "fact"
    )

    return {
        "document_ontology": doc_ont,
        "kg": merged_kg,
        "core_concepts": annotated.get("core_concepts") or [],
        "json_ld": display_json_ld,
        "business_ontology_json_ld": catalog_json_ld,
        "relations": relations,
        "entities": entities,
        "keywords": keywords,
        "facts": signals.get("facts") or [],
        "bo_coverage": coverage,
        "concept_count": len(ontology_payload.get("concepts") or []),
        "matched_count": coverage.get("matched") or 0,
        "pipeline_entity_count": sum(
            1
            for e in entities
            if str(e.get("provenance") or "").lower() != "external"
        ),
        "pipeline_relation_count": pipeline_rel_count,
        "fact_relation_count": fact_rel_count,
        "bo_support_relation_count": bo_rel_count,
        "pipeline_source": signals.get("source"),
        "provenance": "document",
        "source": "wiki_svo_facts+bo_fuse",
    }
