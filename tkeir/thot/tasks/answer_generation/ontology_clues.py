"""Title: Ontology clues for generate-eval (merge + SPARQL + reasoner).

Builds per-passage document ontologies via ``document_ontology``, merges them,
derives SPARQL from the query ontology, runs existing reasoners, and formats
clues for the LLM QA prompt.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)

_SPARQL_SAFE = re.compile(r"[^a-zA-Z0-9_\- ]+")
_MIN_TERM_LEN = 3


@dataclass
class OntologyClueBundle:
    """Merged ontology facts + SPARQL/reasoner clues for the QA prompt.

    Example:
        >>> from thot.tasks.answer_generation.ontology_clues import OntologyClueBundle
        >>> callable(OntologyClueBundle)
        True
    """

    ontology_facts: str = ""
    sparql_clues: str = ""
    reasoner_note: str = ""
    sparql_queries: list[str] = field(default_factory=list)
    passage_graph_count: int = 0
    merged_triple_count: int = 0


def ensure_pipeline_document(
    processed: dict[str, Any],
    *,
    source_id: str,
    text: str = "",
) -> dict[str, Any]:
    """Copy a pipeline doc and set a stable ``source_doc_id`` for URI minting.

    Example:
        >>> from thot.tasks.answer_generation.ontology_clues import ensure_pipeline_document
        >>> ensure_pipeline_document({}, source_id="d1", text="hi")["source_doc_id"]
        'd1'
    """
    document = dict(processed or {})
    document["source_doc_id"] = source_id
    if text and not document.get("content"):
        document["content"] = [text]
    return document


def build_document_ontology_json_ld(document: dict[str, Any]) -> str:
    """Build JSON-LD for one analyzed T-KEIR document (passage or query).

    Example:
        >>> from thot.tasks.answer_generation.ontology_clues import build_document_ontology_json_ld
        >>> callable(build_document_ontology_json_ld)
        True
    """
    from thot.tasks.document_ontology.OntologyBuilder import (
        build_document_graph,
    )
    from thot.tools.search.ontology_utils import serialize_graph_json_ld

    graph = build_document_graph(document)
    return serialize_graph_json_ld(graph)


def merge_passage_ontology_json_lds(json_lds: list[str]) -> tuple[Any, str]:
    """Merge passage JSON-LD payloads → ``(rdflib.Graph, merged_json_ld)``.

    Example:
        >>> from thot.tasks.answer_generation.ontology_clues import merge_passage_ontology_json_lds
        >>> len(merge_passage_ontology_json_lds([])[1])
        2
    """
    from thot.tools.search.ontology_utils import (
        merge_rdf_graphs,
        serialize_graph_json_ld,
    )

    payloads = [payload for payload in json_lds if (payload or "").strip()]
    if not payloads:
        from rdflib import Graph

        empty = Graph()
        return empty, "[]"
    merged = merge_rdf_graphs(payloads)
    return merged, serialize_graph_json_ld(merged)


def _terms_from_pipeline_document(
    document: dict[str, Any] | None,
) -> list[str]:
    """Harvest subject/object labels from a query pipeline document KG.

    Example:
        >>> from thot.tasks.answer_generation.ontology_clues import _terms_from_pipeline_document
        >>> _terms_from_pipeline_document({"kg": [{"subject": {"content": ["Alice"]}}]})
        ['Alice']
    """
    if not document:
        return []
    terms: list[str] = []
    for triple in document.get("kg") or []:
        if not isinstance(triple, dict):
            continue
        for role in ("subject", "object"):
            node = triple.get(role) or {}
            if not isinstance(node, dict):
                continue
            content = node.get("lemma_content") or node.get("content") or []
            if isinstance(content, list):
                text = " ".join(str(part) for part in content if part).strip()
            else:
                text = str(content or "").strip()
            if text:
                terms.append(text)
    for entity in document.get("content_ner") or []:
        if isinstance(entity, dict):
            text = str(entity.get("text") or "").strip()
            if text:
                terms.append(text)
    return terms


def _analysis_morphosyntax(
    analysis: dict[str, Any],
    *,
    query_document: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return morphosyntax tokens from analysis or pipeline documents.

    Example:
        >>> from thot.tasks.answer_generation.ontology_clues import _analysis_morphosyntax
        >>> callable(_analysis_morphosyntax)
        True
    """
    morph = analysis.get("morphosyntax")
    if isinstance(morph, list) and morph:
        return morph
    for document in (query_document, analysis.get("_pipeline_doc")):
        if not isinstance(document, dict):
            continue
        nested = document.get("content_morphosyntax")
        if isinstance(nested, list) and nested:
            return nested
    return []


def _content_token_keys(
    analysis: dict[str, Any],
    *,
    query_document: dict[str, Any] | None = None,
) -> set[str]:
    """Lowercased content-bearing surfaces from morphosyntax (UD POS).

    Example:
        >>> from thot.tasks.answer_generation.ontology_clues import _content_token_keys
        >>> callable(_content_token_keys)
        True
    """
    from thot.tools.search.query_refiner import (
        meaningful_tokens_from_morphosyntax,
    )

    morph = _analysis_morphosyntax(analysis, query_document=query_document)
    if not morph:
        return set()
    return {
        token.lower()
        for token in meaningful_tokens_from_morphosyntax(morph)
        if token
    }


def _is_content_phrase(text: str, content_keys: set[str]) -> bool:
    """True if phrase has content tokens, or no POS filter is available.

    Example:
        >>> from thot.tasks.answer_generation.ontology_clues import _is_content_phrase
        >>> _is_content_phrase("hello world", {"hello"})
        True
    """
    if not text:
        return False
    if not content_keys:
        # No morphosyntax: keep NLP-derived phrases; do not invent stop lists.
        return True
    parts = [part for part in re.split(r"\s+", text.strip()) if part]
    if not parts:
        return False
    return any(part.lower() in content_keys for part in parts)


def _append_term(terms: list[str], text: str | None) -> None:
    """Append a non-empty term string.

    Example:
        >>> from thot.tasks.answer_generation.ontology_clues import _append_term
        >>> terms = []
        >>> _append_term(terms, "  alpha  ")
        >>> terms
        ['alpha']
    """
    value = str(text or "").strip()
    if value:
        terms.append(value)


def _query_focus_terms(
    analysis: dict[str, Any],
    query: str,
    *,
    query_document: dict[str, Any] | None = None,
) -> list[str]:
    """Collect SPARQL focus terms from NLP analysis (language-agnostic).

    Prefer pipeline KG / NER / keywords / lemmas / search_terms / SVO. Filter
    SVO and morph fallbacks with Universal Dependencies POS (via existing
    helpers), never with language-specific stopword lists. ``query`` is unused
    for tokenization when NLP is present.

        Example:
            >>> from thot.tasks.answer_generation.ontology_clues import _query_focus_terms
            >>> callable(_query_focus_terms)
            True
    """
    _ = query  # raw string is not tokenized; NLP analysis is the source of truth
    terms: list[str] = []
    terms.extend(_terms_from_pipeline_document(query_document))

    for entity in analysis.get("ner_entities") or []:
        if isinstance(entity, dict):
            _append_term(terms, entity.get("text"))
        else:
            _append_term(terms, getattr(entity, "text", None))

    for keyword in analysis.get("keywords") or []:
        if isinstance(keyword, dict):
            _append_term(terms, keyword.get("text"))
        else:
            _append_term(terms, keyword)

    for lemma in analysis.get("lemmas") or []:
        _append_term(terms, lemma)

    for term in analysis.get("search_terms") or []:
        _append_term(terms, term)

    content_keys = _content_token_keys(analysis, query_document=query_document)
    for triple in analysis.get("svo_triples") or []:
        if isinstance(triple, dict):
            parts = [
                triple.get("subject"),
                triple.get("verb"),
                triple.get("object"),
            ]
        else:
            parts = [
                getattr(triple, "subject", None),
                getattr(triple, "verb", None),
                getattr(triple, "object", None),
            ]
        for part in parts:
            text = str(part or "").strip()
            if _is_content_phrase(text, content_keys):
                terms.append(text)

    # Fallback: content lemmas / surfaces from morphosyntax only
    if not terms:
        morph = _analysis_morphosyntax(analysis, query_document=query_document)
        if morph:
            from thot.tools.search.query_analyzer import extract_lemma_terms
            from thot.tools.search.query_refiner import (
                meaningful_tokens_from_morphosyntax,
            )

            for token in meaningful_tokens_from_morphosyntax(morph):
                _append_term(terms, token)
            for lemma in extract_lemma_terms(morph):
                _append_term(terms, lemma)

    # Normalize / dedupe
    cleaned: list[str] = []
    seen: set[str] = set()
    for term in terms:
        norm = _SPARQL_SAFE.sub(" ", term).strip()
        if len(norm) < _MIN_TERM_LEN:
            continue
        key = norm.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(norm)
    return cleaned[:12]


def _sparql_string_literal(value: str) -> str:
    """Escape a value for use inside a SPARQL string literal.

    Example:
        >>> from thot.tasks.answer_generation.ontology_clues import _sparql_string_literal
        >>> _sparql_string_literal("hello")
        'hello'
    """
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", " ")
        .replace("\r", " ")
    )


def generate_sparql_from_query_ontology(
    analysis: dict[str, Any],
    query: str,
    *,
    query_document: dict[str, Any] | None = None,
    limit: int = 30,
) -> list[str]:
    """Generate up to three SPARQL SELECT queries from the query ontology.

    1. Label-oriented fact harvest for focus terms
    2. Multi-hop bridge between the two strongest entities (when available)
    3. Class / type focus for the top entity-like term

        Example:
            >>> from thot.tasks.answer_generation.ontology_clues import generate_sparql_from_query_ontology
            >>> len(generate_sparql_from_query_ontology({"search_terms": ["Alice"]}, "Who is Alice?")) >= 1
            True
    """
    terms = _query_focus_terms(analysis, query, query_document=query_document)
    if not terms:
        return []

    queries: list[str] = []
    # 1) Label-oriented fact harvest for all focus terms
    filters = " ||\n    ".join(
        f'CONTAINS(LCASE(STR(?sl)), "{_sparql_string_literal(term.lower())}") || '
        f'CONTAINS(LCASE(STR(?ol)), "{_sparql_string_literal(term.lower())}")'
        for term in terms[:8]
    )
    queries.append(f"""PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX tkeir: <http://tkeir.local/ontology/>
SELECT ?s ?p ?o ?sl ?ol WHERE {{
  ?s ?p ?o .
  OPTIONAL {{ ?s rdfs:label ?sl }}
  OPTIONAL {{ ?o rdfs:label ?ol }}
  FILTER(
    {filters}
  )
}} LIMIT {int(limit)}""")

    # 2) Multi-hop bridge between the two longest entity-like terms
    entity_like = sorted(terms, key=len, reverse=True)
    if len(entity_like) >= 2:
        left = _sparql_string_literal(entity_like[0].lower())
        right = _sparql_string_literal(entity_like[1].lower())
        queries.append(f"""PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX tkeir: <http://tkeir.local/ontology/>
SELECT ?a ?p1 ?mid ?p2 ?b ?al ?midl ?bl WHERE {{
  ?a ?p1 ?mid .
  ?mid ?p2 ?b .
  OPTIONAL {{ ?a rdfs:label ?al }}
  OPTIONAL {{ ?mid rdfs:label ?midl }}
  OPTIONAL {{ ?b rdfs:label ?bl }}
  FILTER(
    (
      CONTAINS(LCASE(STR(?al)), "{left}") &&
      CONTAINS(LCASE(STR(?bl)), "{right}")
    ) || (
      CONTAINS(LCASE(STR(?al)), "{right}") &&
      CONTAINS(LCASE(STR(?bl)), "{left}")
    )
  )
}} LIMIT {max(10, int(limit) // 2)}""")
    else:
        # Fallback second query: outgoing edges from the top term
        top = _sparql_string_literal(entity_like[0].lower())
        queries.append(f"""PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX tkeir: <http://tkeir.local/ontology/>
SELECT ?s ?p ?o ?sl ?ol WHERE {{
  ?s ?p ?o .
  OPTIONAL {{ ?s rdfs:label ?sl }}
  OPTIONAL {{ ?o rdfs:label ?ol }}
  FILTER(CONTAINS(LCASE(STR(?sl)), "{top}"))
}} LIMIT {max(10, int(limit) // 2)}""")

    # 3) Class / type inventory for the strongest focus term
    top = _sparql_string_literal(entity_like[0].lower())
    queries.append(
        f"""PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
SELECT ?x ?type ?xl ?tl WHERE {{
  ?x rdf:type ?type .
  OPTIONAL {{ ?x rdfs:label ?xl }}
  OPTIONAL {{ ?type rdfs:label ?tl }}
  FILTER(
    CONTAINS(LCASE(STR(?xl)), "{top}") ||
    CONTAINS(LCASE(STR(?tl)), "{top}") ||
    CONTAINS(LCASE(STR(?x)), "{top}") ||
    CONTAINS(LCASE(STR(?type)), "{top}")
  )
}} LIMIT {max(10, int(limit) // 2)}"""
    )
    return queries[:3]


def propose_queries_for_navigator(
    analysis: dict[str, Any] | None,
    query: str,
    *,
    ontology_json_ld: str = "",
    entity_types: list[str] | None = None,
    chunk_entities: list[dict[str, Any]] | None = None,
    chunk_keywords: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Build Navigator proposals from returned-chunk importance + ontology.

    The three SPARQL chips are driven by the most important entity/keyword
    terms across retrieved chunks (not by generic business-ontology popularity).

        Example:
            >>> from thot.tasks.answer_generation.ontology_clues import propose_queries_for_navigator
            >>> propose_queries_for_navigator(None, "q")[0]["kind"]
            'coherence'
    """
    analysis = analysis or {}
    from thot.tools.search.ontology_utils import merge_rdf_graphs
    from thot.tools.search.python_reasoner import propose_navigator_queries

    focus = _query_focus_terms(analysis, query)
    if not (ontology_json_ld or "").strip():
        return [
            {
                "kind": "coherence",
                "title": "Coherence check",
                "query": "consistency",
                "description": (
                    "No fused ontology yet — run a search/RAG query first"
                ),
            }
        ]
    try:
        graph = merge_rdf_graphs([ontology_json_ld])
    except Exception:  # noqa: BLE001
        LOGGER.exception("Failed to parse ontology for navigator proposals")
        return []
    return propose_navigator_queries(
        graph,
        focus_terms=focus,
        entity_types=entity_types or [],
        chunk_entities=chunk_entities or [],
        chunk_keywords=chunk_keywords or [],
    )


def _format_sparql_binding_row(row: Any) -> str:
    """Render one SPARQL result row as a compact clue line.

    Example:
        >>> from thot.tasks.answer_generation.ontology_clues import _format_sparql_binding_row
        >>> _format_sparql_binding_row({"sl": "Alice", "ol": "Bob"})
        'Alice — Bob'
    """
    if isinstance(row, dict):
        parts: list[str] = []
        for key in (
            "sl",
            "al",
            "s",
            "p",
            "p1",
            "midl",
            "mid",
            "p2",
            "ol",
            "bl",
            "o",
            "b",
        ):
            if key in row and row[key] is not None:
                value = str(row[key]).strip()
                if not value:
                    continue
                if value.startswith("http://") or value.startswith("https://"):
                    value = value.rsplit("/", 1)[-1]
                parts.append(value)
        if parts:
            return " — ".join(dict.fromkeys(parts))
        return " | ".join(f"{k}={v}" for k, v in row.items() if v is not None)
    return str(row)


def run_sparql_on_merged(
    merged_json_ld: str,
    sparql_queries: list[str],
    *,
    limit_rows: int = 20,
) -> tuple[str, list[str]]:
    """Execute SPARQL queries via ``query_merged_ontology``; return clue text.

    Example:
        >>> from thot.tasks.answer_generation.ontology_clues import run_sparql_on_merged
        >>> callable(run_sparql_on_merged)
        True
    """
    from thot.tools.search.ontology_reasoner import query_merged_ontology

    clue_lines: list[str] = []
    notes: list[str] = []
    for index, sparql in enumerate(sparql_queries, start=1):
        try:
            result = query_merged_ontology(
                merged_json_ld,
                operation="sparql",
                sparql=sparql,
                limit=limit_rows,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("SPARQL clue query %d failed: %s", index, exc)
            notes.append(f"SPARQL#{index} failed: {exc}")
            continue
        rows = result.get("results") or []
        backend = result.get("backend") or ""
        notes.append(
            f"SPARQL#{index}: {len(rows)} hit(s) via {backend or 'python'}"
        )
        for row in rows[:limit_rows]:
            line = _format_sparql_binding_row(row)
            if line:
                clue_lines.append(f"- {line}")
    # Dedupe
    clue_lines = list(dict.fromkeys(clue_lines))
    return "\n".join(clue_lines) if clue_lines else "(no SPARQL hits)", notes


def run_reasoner_on_merged(
    merged_json_ld: str,
) -> str:
    """Run consistency (+ optional infer) on the merged passage ontology.

    Example:
        >>> from thot.tasks.answer_generation.ontology_clues import run_reasoner_on_merged
        >>> callable(run_reasoner_on_merged)
        True
    """
    from thot.tools.search.ontology_reasoner import query_merged_ontology

    notes: list[str] = []
    try:
        consistency = query_merged_ontology(
            merged_json_ld,
            operation="consistency",
        )
        consistent = consistency.get("consistent")
        backend = consistency.get("backend") or ""
        if consistent is True:
            notes.append(f"consistency: ok ({backend})")
        elif consistent is False:
            notes.append(f"consistency: INCONSISTENT ({backend})")
        else:
            notes.append(
                f"consistency: {consistency.get('note') or consistency.get('operation')} ({backend})"
            )
    except Exception as exc:  # noqa: BLE001
        notes.append(f"consistency failed: {exc}")

    try:
        inferred = query_merged_ontology(
            merged_json_ld,
            operation="infer",
            limit=20,
        )
        count = int(
            inferred.get("count") or len(inferred.get("results") or [])
        )
        if count:
            notes.append(f"infer: {count} result(s)")
            for row in (inferred.get("results") or [])[:8]:
                if isinstance(row, dict):
                    label = (
                        row.get("label")
                        or row.get("iri")
                        or row.get("class")
                        or row.get("individual")
                    )
                    if label:
                        notes.append(f"  - inferred: {label}")
                else:
                    notes.append(f"  - inferred: {row}")
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("infer skipped: %s", exc)
        notes.append(f"infer skipped: {exc}")
    return "; ".join(notes) if notes else ""


def build_ontology_clues(
    *,
    query: str,
    analysis: dict[str, Any],
    query_document: dict[str, Any] | None,
    passage_documents: list[dict[str, Any]],
    use_reasoner: bool = True,
) -> OntologyClueBundle:
    """Merge passage ontologies, SPARQL from query, reason — return prompt clues.

    Steps:
      1. ``build_document_graph`` per passage (and query) via document_ontology
      2. ``merge_rdf_graphs`` on passage JSON-LD
      3. Generate SPARQL from query ontology terms; run on merged graph
      4. Optional consistency / infer reasoner
      5. Summarize graph + SPARQL hits as LLM clues

        Example:
            >>> from thot.tasks.answer_generation.ontology_clues import build_ontology_clues
            >>> callable(build_ontology_clues)
            True
    """
    from thot.tools.search.ontology_utils import summarize_graph_for_prompt

    bundle = OntologyClueBundle()
    passage_json_lds: list[str] = []
    for index, document in enumerate(passage_documents):
        if not document:
            continue
        try:
            json_ld = build_document_ontology_json_ld(document)
            if json_ld and json_ld.strip() not in {"", "[]"}:
                passage_json_lds.append(json_ld)
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("Passage ontology build failed [%s]: %s", index, exc)

    bundle.passage_graph_count = len(passage_json_lds)
    if not passage_json_lds:
        # Fall back: still try query graph alone for term extraction
        bundle.ontology_facts = "(no passage ontologies built)"
        return bundle

    merged_graph, merged_json_ld = merge_passage_ontology_json_lds(
        passage_json_lds
    )
    bundle.merged_triple_count = len(merged_graph)
    bundle.ontology_facts = summarize_graph_for_prompt(
        merged_graph, query, max_triples=50
    )

    # Query ontology drives SPARQL; merged passages are the query target.
    sparql_queries = generate_sparql_from_query_ontology(
        analysis, query, query_document=query_document
    )
    bundle.sparql_queries = sparql_queries
    sparql_notes: list[str] = []
    if sparql_queries and merged_json_ld.strip() not in {"", "[]"}:
        clues, sparql_notes = run_sparql_on_merged(
            merged_json_ld, sparql_queries
        )
        bundle.sparql_clues = clues
    else:
        bundle.sparql_clues = "(no SPARQL generated)"

    reasoner_bits: list[str] = []
    if use_reasoner and merged_json_ld.strip() not in {"", "[]"}:
        reasoner_bits.append(run_reasoner_on_merged(merged_json_ld))
    reasoner_bits.extend(sparql_notes)
    bundle.reasoner_note = "; ".join(bit for bit in reasoner_bits if bit)
    return bundle


def format_clues_for_prompt(bundle: OntologyClueBundle) -> str:
    """Format merged passage ontology summary for the QA prompt.

    SPARQL hit lines stay in ``bundle.sparql_clues`` and are injected via the
    dedicated SPARQL CLUES block (avoid duplicating them here).

        Example:
            >>> from thot.tasks.answer_generation.ontology_clues import OntologyClueBundle, format_clues_for_prompt
            >>> "fact" in format_clues_for_prompt(OntologyClueBundle(ontology_facts="fact"))
            True
    """
    sections: list[str] = []
    if bundle.ontology_facts:
        sections.append(
            "Merged passage ontology (document_ontology):\n"
            f"{bundle.ontology_facts}"
        )
    if bundle.passage_graph_count or bundle.merged_triple_count:
        sections.append(
            f"(graphs merged={bundle.passage_graph_count}, "
            f"triples={bundle.merged_triple_count})"
        )
    return "\n\n".join(sections) if sections else "(no ontology clues)"
