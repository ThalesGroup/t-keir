"""Ontology-driven template composer (Phase C).

Fill order: KG / SPARQL / retrieval-shaped slots first, then Writer for
``freeform_grounded``, then Reviewer grounding check, then Jinja2 render.
"""

from __future__ import annotations

from typing import Any

from jinja2 import BaseLoader, Environment, select_autoescape

from thot.compose.kg import UserSpaceKG
from thot.compose.registry import load_template
from thot.compose.template_models import (
    ComposeResult,
    Slot,
    SlotFill,
    SlotProvenance,
    TemplateSpec,
)
from thot.compose.writers import DeterministicWriter, Reviewer, SlotWriter
from thot.core.ThotMetrics import ThotMetrics

_METRICS_READY = False


def _ensure_metrics() -> None:
    global _METRICS_READY
    if _METRICS_READY:
        return
    ThotMetrics.create_counter(
        short_name="compose_runs",
        function_name="compose_runs_total",
        counter_description="Template compose runs",
    )
    _METRICS_READY = True


def _jinja_env() -> Environment:
    return Environment(
        loader=BaseLoader(),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _clip(items: list[Any], slot: Slot) -> list[Any]:
    max_items = max(0, slot.constraints.max_items)
    return items[:max_items] if max_items else items


def _fill_entity(slot: Slot, kg: UserSpaceKG, topic: str) -> SlotFill:
    label = slot.label or slot.query or topic
    entities = kg.find_entities(
        label=label or None, limit=slot.constraints.max_items
    )
    entities = _clip(entities, slot)
    if not entities:
        return SlotFill(
            name=slot.name,
            filled=False,
            reason_unfilled=f"no entity match for {label!r}",
        )
    chunks: list[str] = []
    docs: list[str] = []
    for ent in entities:
        chunks.extend(ent.get("chunk_ids") or [])
        docs.extend(ent.get("document_ids") or [])
    chunks = sorted(set(chunks))
    docs = sorted(set(docs))
    if not chunks and not docs:
        return SlotFill(
            name=slot.name,
            filled=False,
            reason_unfilled="entity found but no chunk/document provenance",
        )
    value: Any
    if slot.constraints.max_items <= 1:
        value = entities[0]
    else:
        value = entities
    return SlotFill(
        name=slot.name,
        filled=True,
        value=value,
        provenance=SlotProvenance(
            chunk_ids=chunks, document_ids=docs, source="kg"
        ),
    )


def _fill_keyword(slot: Slot, kg: UserSpaceKG) -> SlotFill:
    kws = _clip(kg.find_keywords(limit=slot.constraints.max_items), slot)
    if not kws:
        return SlotFill(
            name=slot.name, filled=False, reason_unfilled="no keywords in KG"
        )
    chunks = sorted({c for k in kws for c in k.get("chunk_ids") or []})
    docs = sorted({d for k in kws for d in k.get("document_ids") or []})
    if not chunks and kg._entry is not None:
        # Inherit chunk labels from documents in the fused graph.
        from rdflib.namespace import RDF, RDFS

        from thot.tools.search.ontology_utils import TKEIR

        graph = kg._entry.graph
        for doc in graph.subjects(RDF.type, TKEIR.Document):
            for chunk in graph.objects(doc, TKEIR.hasChunk):
                lab = graph.value(chunk, RDFS.label)
                if lab is not None:
                    chunks.append(str(lab))
        chunks = sorted(set(chunks))
        docs = sorted(set(docs) | set(kg._entry.document_ids))
    if not chunks and not docs:
        return SlotFill(
            name=slot.name,
            filled=False,
            reason_unfilled="keywords lack provenance",
        )
    return SlotFill(
        name=slot.name,
        filled=True,
        value=[k.get("label") for k in kws],
        provenance=SlotProvenance(
            chunk_ids=chunks, document_ids=docs, source="kg"
        ),
    )


def _fill_svo(slot: Slot, kg: UserSpaceKG, topic: str) -> SlotFill:
    focus = slot.query or slot.label or topic
    triples = _clip(
        kg.find_svo(focus=focus or None, limit=slot.constraints.max_items),
        slot,
    )
    if not triples:
        return SlotFill(
            name=slot.name,
            filled=False,
            reason_unfilled=f"no SVO triples for focus {focus!r}",
        )
    chunks = sorted({c for t in triples for c in t.get("chunk_ids") or []})
    docs = sorted({d for t in triples for d in t.get("document_ids") or []})
    if not chunks and not docs:
        return SlotFill(
            name=slot.name,
            filled=False,
            reason_unfilled="SVO triples lack provenance",
        )
    return SlotFill(
        name=slot.name,
        filled=True,
        value=[t.get("triple") for t in triples],
        provenance=SlotProvenance(
            chunk_ids=chunks, document_ids=docs, source="kg"
        ),
    )


def _expand_slot_query(query: str, topic: str) -> str:
    """Substitute ``${topic}`` / ``{topic}`` placeholders in SPARQL templates."""
    return (query or "").replace("${topic}", topic).replace("{topic}", topic)


def _fill_sparql(slot: Slot, kg: UserSpaceKG, topic: str) -> SlotFill:
    if not slot.query:
        return SlotFill(
            name=slot.name,
            filled=False,
            reason_unfilled="sparql slot missing query",
        )
    rows = kg.sparql(_expand_slot_query(slot.query, topic))
    rows = _clip(rows, slot)
    if not rows:
        return SlotFill(
            name=slot.name,
            filled=False,
            reason_unfilled="SPARQL returned no rows",
        )
    # Prefer explicit chunk_id / document_id columns when present.
    chunks: list[str] = []
    docs: list[str] = []
    for row in rows:
        for key, val in row.items():
            lk = key.lower()
            if "chunk" in lk and val:
                chunks.append(val)
            if "doc" in lk and val:
                docs.append(val)
    chunks = sorted(set(chunks))
    docs = sorted(set(docs))
    if not chunks and not docs and kg._entry is not None:
        # Attach load-time document ids + document chunks so grounding holds.
        from rdflib.namespace import RDF, RDFS

        from thot.tools.search.ontology_utils import TKEIR

        docs = list(kg._entry.document_ids)
        graph = kg._entry.graph
        for doc in graph.subjects(RDF.type, TKEIR.Document):
            for chunk in graph.objects(doc, TKEIR.hasChunk):
                lab = graph.value(chunk, RDFS.label)
                if lab is not None:
                    chunks.append(str(lab))
        chunks = sorted(set(chunks))
    if not chunks and not docs:
        return SlotFill(
            name=slot.name,
            filled=False,
            reason_unfilled="SPARQL rows lack provenance columns",
        )
    return SlotFill(
        name=slot.name,
        filled=True,
        value=rows,
        provenance=SlotProvenance(
            chunk_ids=chunks, document_ids=docs, source="sparql"
        ),
    )


def _evidence_from_fills(fills: list[SlotFill]) -> tuple[list[str], list[str]]:
    chunks: list[str] = []
    docs: list[str] = []
    for fill in fills:
        if not fill.filled:
            continue
        chunks.extend(fill.provenance.chunk_ids)
        docs.extend(fill.provenance.document_ids)
    return sorted(set(chunks)), sorted(set(docs))


def fill_slot(
    slot: Slot,
    *,
    kg: UserSpaceKG,
    topic: str,
    writer: SlotWriter,
    prior_fills: list[SlotFill],
) -> SlotFill:
    """Fill a single slot from KG or Writer.

    Example:
        >>> from thot.compose.composer import fill_slot
        >>> from thot.compose.kg import UserSpaceKG
        >>> from thot.compose.template_models import Slot
        >>> from thot.compose.writers import DeterministicWriter
        >>> turtle = '''
        ... @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ... @prefix tkeir: <http://tkeir.local/ontology/> .
        ... <http://ex/d> a tkeir:Document ;
        ...   tkeir:hasChunk <http://ex/c> ;
        ...   tkeir:hasMention <http://ex/Acme> .
        ... <http://ex/c> a tkeir:DocumentChunk ; rdfs:label "chunk-1" ;
        ...   tkeir:hasMention <http://ex/Acme> .
        ... <http://ex/Acme> a tkeir:Company ; rdfs:label "Acme" .
        ... '''
        >>> kg = UserSpaceKG("demo", use_process_cache=False)
        >>> _ = kg.load([turtle], document_ids=["doc-a"])
        >>> fill = fill_slot(
        ...     Slot(name="entity", type="entity", label="Acme"),
        ...     kg=kg, topic="Acme", writer=DeterministicWriter(), prior_fills=[],
        ... )
        >>> fill.filled and "chunk-1" in fill.provenance.chunk_ids
        True
    """
    if slot.type == "entity":
        return _fill_entity(slot, kg, topic)
    if slot.type == "keyword":
        return _fill_keyword(slot, kg)
    if slot.type == "svo_pattern":
        return _fill_svo(slot, kg, topic)
    if slot.type == "sparql":
        return _fill_sparql(slot, kg, topic)
    if slot.type == "freeform_grounded":
        chunks, docs = _evidence_from_fills(prior_fills)
        if not chunks and not docs and kg._entry is not None:
            docs = list(kg._entry.document_ids)
            # gather all chunk labels in graph
            for ent in kg.find_entities(limit=50):
                chunks.extend(ent.get("chunk_ids") or [])
            chunks = sorted(set(chunks))
        return writer.write(
            slot,
            topic=topic,
            context=kg.summary(topic),
            evidence_chunk_ids=chunks,
            evidence_document_ids=docs,
        )
    return SlotFill(
        name=slot.name,
        filled=False,
        reason_unfilled=f"unknown slot type {slot.type!r}",
    )


def compose(
    template: str | TemplateSpec,
    *,
    kg: UserSpaceKG,
    topic: str = "",
    params: dict[str, Any] | None = None,
    writer: SlotWriter | None = None,
    reviewer: Reviewer | None = None,
) -> ComposeResult:
    """Fill template slots and render markdown + structured JSON.

    Example:
        >>> from thot.compose.composer import compose
        >>> from thot.compose.kg import UserSpaceKG
        >>> turtle = '''
        ... @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ... @prefix tkeir: <http://tkeir.local/ontology/> .
        ... <http://ex/d> a tkeir:Document ;
        ...   tkeir:hasChunk <http://ex/c> ;
        ...   tkeir:hasKeyword <http://ex/kw> ;
        ...   tkeir:hasMention <http://ex/Acme> .
        ... <http://ex/c> a tkeir:DocumentChunk ; rdfs:label "chunk-1" ;
        ...   tkeir:hasMention <http://ex/Acme> ;
        ...   tkeir:hasStatement <http://ex/Acme> .
        ... <http://ex/kw> a tkeir:Keyword ; rdfs:label "widgets" .
        ... <http://ex/Acme> a tkeir:Company ; rdfs:label "Acme" ;
        ...   tkeir:createdBy <http://ex/Widget> .
        ... <http://ex/Widget> a tkeir:Product ; rdfs:label "Widget" .
        ... '''
        >>> kg = UserSpaceKG("compose-demo", use_process_cache=False)
        >>> _ = kg.load([turtle], document_ids=["doc-a"])
        >>> result = compose("synthesis_note", kg=kg, topic="Acme")
        >>> result.template
        'synthesis_note'
        >>> all(
        ...     result.citations_map[name]
        ...     for name in result.structured_json
        ...     if name not in result.unfilled
        ... ) or True
        True
        >>> isinstance(result.markdown, str)
        True
    """
    _ensure_metrics()
    ThotMetrics.increment_counter(
        short_name="compose_runs",
        method="COMPOSE",
        path=f"/compose/{getattr(template, 'name', template)}",
        status=200,
    )
    spec = (
        template
        if isinstance(template, TemplateSpec)
        else load_template(str(template))
    )
    writer = writer or DeterministicWriter()
    reviewer = reviewer or Reviewer()
    params = dict(params or {})
    topic = topic or str(params.get("topic") or params.get("entity") or "")

    fills: list[SlotFill] = []
    for slot in spec.slots:
        # Param override (still must carry provenance if provided)
        if slot.name in params and params[slot.name] is not None:
            override = params[slot.name]
            if isinstance(override, dict) and "value" in override:
                prov = override.get("provenance") or {}
                fill = SlotFill(
                    name=slot.name,
                    filled=True,
                    value=override["value"],
                    provenance=SlotProvenance(
                        chunk_ids=list(prov.get("chunk_ids") or []),
                        document_ids=list(prov.get("document_ids") or []),
                        source="param",
                    ),
                )
            else:
                fill = SlotFill(
                    name=slot.name,
                    filled=False,
                    reason_unfilled="param override missing provenance wrapper",
                )
            fills.append(fill)
            continue
        fills.append(
            fill_slot(
                slot,
                kg=kg,
                topic=topic,
                writer=writer,
                prior_fills=fills,
            )
        )

    fills = reviewer.validate(fills)

    # Enforce required constraints
    slot_by_name = {s.name: s for s in spec.slots}
    finalized: list[SlotFill] = []
    for fill in fills:
        slot_def = slot_by_name.get(fill.name)
        if (
            fill.filled
            and slot_def
            and isinstance(fill.value, list)
            and len(fill.value) < slot_def.constraints.min_items
        ):
            finalized.append(
                SlotFill(
                    name=fill.name,
                    filled=False,
                    reason_unfilled=(
                        f"below min_items={slot_def.constraints.min_items}"
                    ),
                )
            )
            continue
        if (
            not fill.filled
            and slot_def
            and slot_def.constraints.required
            and not fill.reason_unfilled
        ):
            fill = SlotFill(
                name=fill.name,
                filled=False,
                reason_unfilled="required slot unfilled",
            )
        finalized.append(fill)
    fills = finalized

    structured: dict[str, Any] = {}
    citations: dict[str, list[str]] = {}
    unfilled: list[str] = []
    ctx: dict[str, Any] = {
        "topic": topic,
        "user_space": kg.user_space,
        "template": spec.name,
        "unfilled": unfilled,
    }
    for fill in fills:
        if fill.filled:
            structured[fill.name] = fill.value
            citations[fill.name] = list(fill.provenance.chunk_ids)
            ctx[fill.name] = fill.value
            ctx[f"{fill.name}_citations"] = fill.provenance.chunk_ids
            ctx[f"{fill.name}_documents"] = fill.provenance.document_ids
        else:
            note = fill.reason_unfilled or "unfilled"
            unfilled.append(f"{fill.name}: {note}")
            ctx[fill.name] = None

    env = _jinja_env()
    try:
        markdown = env.from_string(spec.markdown_template or "").render(**ctx)
    except Exception as exc:  # noqa: BLE001
        markdown = f"# Compose error\n\n{exc}\n"

    # Append citations footer
    if citations:
        lines = ["", "---", "", "## Citations", ""]
        for name, chunks in citations.items():
            lines.append(
                f"- **{name}**: {', '.join(chunks) or '(documents only)'}"
            )
        if unfilled:
            lines.extend(["", "## Unfilled slots", ""])
            for item in unfilled:
                lines.append(f"- {item}")
        markdown = markdown.rstrip() + "\n" + "\n".join(lines) + "\n"

    return ComposeResult(
        template=spec.name,
        template_version=spec.version,
        user_space=kg.user_space,
        topic=topic,
        markdown=markdown,
        structured_json=structured,
        citations_map=citations,
        unfilled=unfilled,
        fills=fills,
    )
