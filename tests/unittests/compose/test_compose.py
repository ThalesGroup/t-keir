"""Title: Compose

Unit tests for ontology-driven composition (Phase C).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from pathlib import Path

from thot.agent.registry import list_agent_names, load_agent_spec
from thot.compose.composer import compose, fill_slot
from thot.compose.demo_data import demo_turtles
from thot.compose.exporters import export_markdown, export_structured_json
from thot.compose.kg import UserSpaceKG
from thot.compose.registry import list_template_names, load_template
from thot.compose.template_models import Slot
from thot.compose.writers import DeterministicWriter, Reviewer


def _demo_kg(space: str = "alice") -> UserSpaceKG:
    kg = UserSpaceKG(space, use_process_cache=False)
    kg.load(demo_turtles(), document_ids=["doc_a"])
    return kg


def test_templates_and_agents_registered():
    assert "synthesis_note" in list_template_names()
    assert "entity_profile" in list_template_names()
    for name in ("analyst", "writer", "reviewer", "researcher"):
        assert name in list_agent_names()
        assert load_agent_spec(name).name == name


def test_kg_cache_invalidation():
    kg = UserSpaceKG("cache-test", use_process_cache=True)
    kg.load(demo_turtles(), document_ids=["doc_a"])
    assert not kg.is_empty()
    assert kg.find_entities(label="Acme")
    kg.invalidate(reason="supersede")
    assert kg.is_empty()
    # fresh instance should miss cache
    kg2 = UserSpaceKG("cache-test", use_process_cache=True)
    assert kg2.is_empty()


def test_sparql_and_entity_fill():
    kg = _demo_kg("sparql-test")
    rows = kg.sparql(
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
        "SELECT ?label WHERE { ?s rdfs:label ?label } LIMIT 5"
    )
    assert any("Acme" in r.get("label", "") for r in rows)
    fill = fill_slot(
        Slot(name="entity", type="entity", label="Acme"),
        kg=kg,
        topic="Acme",
        writer=DeterministicWriter(),
        prior_fills=[],
    )
    assert fill.filled
    assert "doc.pdf#chunk-1-abc" in fill.provenance.chunk_ids


def test_compose_synthesis_note_grounded(tmp_path: Path):
    kg = _demo_kg("compose-syn")
    result = compose("synthesis_note", kg=kg, topic="Acme")
    assert result.template == "synthesis_note"
    assert "executive_summary" in result.structured_json
    assert result.citations_map["executive_summary"]
    for name in result.structured_json:
        assert result.citations_map.get(name), f"{name} missing citations"
    assert any(u.startswith("open_questions:") for u in result.unfilled)
    md = export_markdown(result, tmp_path / "synthesis_note.md")
    js = export_structured_json(result, tmp_path / "synthesis_note.json")
    assert "Citations" in md.read_text(encoding="utf-8")
    assert js.is_file()


def test_compose_entity_profile():
    kg = _demo_kg("compose-ent")
    result = compose("entity_profile", kg=kg, topic="Acme")
    assert result.structured_json.get("entity")
    assert result.citations_map.get("entity")
    assert "narrative" in result.structured_json


def test_reviewer_rejects_ungrounded():
    from thot.compose.template_models import SlotFill, SlotProvenance

    fills = Reviewer().validate(
        [
            SlotFill(
                name="ok",
                filled=True,
                value="x",
                provenance=SlotProvenance(chunk_ids=["c1"]),
            ),
            SlotFill(
                name="bad",
                filled=True,
                value="y",
                provenance=SlotProvenance(chunk_ids=[]),
            ),
        ]
    )
    assert fills[0].filled and not fills[1].filled


def test_load_template_slots():
    spec = load_template("synthesis_note")
    names = {s.name for s in spec.slots}
    assert "executive_summary" in names
    assert "key_relations" in names


def test_otan_templates_registered():
    for name in (
        "otan_intsum",
        "otan_sitrep",
        "otan_spotrep",
        "otan_commander_brief",
    ):
        assert name in list_template_names()
        spec = load_template(name)
        assert spec.slots
        assert spec.markdown_template.strip()


def test_otan_intsum_has_full_body_slots():
    spec = load_template("otan_intsum")
    names = {s.name for s in spec.slots}
    assert {
        "subject",
        "period_covered",
        "highlights",
        "adversary_situation",
        "specialist_threat",
        "environmental_factors",
        "assessment_outlook",
        "sources",
    } <= names
    assert any(
        s.name == "highlights" and s.constraints.required for s in spec.slots
    )
    assert "HIGHLIGHTS / EXECUTIVE SUMMARY" in (spec.markdown_template or "")
    assert "MLCOA" in (spec.markdown_template or "") or "ASSESSMENT" in (
        spec.markdown_template or ""
    )


def test_findings_grounded_writer_slot_tags():
    from thot.compose.writers import FindingsGroundedWriter

    ctx = (
        "- [situation] Vessel loitering near Fujairah [c1]\n"
        "- [entity_tracking] EOI MT RED SEA EAGLE [c2]\n"
        "- [recommendation] Raise CCIR-1 [c3]"
    )
    assert "Vessel loitering" in (
        FindingsGroundedWriter.prose_for_slot(ctx, "situation") or ""
    )
    assert FindingsGroundedWriter.prose_for_slot(ctx, "evaluation") == ""
    assert (
        FindingsGroundedWriter.prose_for_slot("- plain [c1]", "situation")
        is None
    )

    writer = FindingsGroundedWriter(
        findings_context=ctx, chunk_ids=["c1", "c2"], document_ids=[]
    )
    sit = writer.write(
        Slot(
            name="situation", type="freeform_grounded", description="SITUATION"
        ),
        topic="MT RED SEA EAGLE",
        context="",
        evidence_chunk_ids=[],
        evidence_document_ids=[],
    )
    assert sit.filled
    assert "Vessel loitering" in str(sit.value)
    assert "EOI" not in str(sit.value)
    empty = writer.write(
        Slot(name="evaluation", type="freeform_grounded"),
        topic="MT RED SEA EAGLE",
        context="",
        evidence_chunk_ids=[],
        evidence_document_ids=[],
    )
    assert not empty.filled


def test_persona_writers_embed_otan_templates():
    expected = {
        "j2_analyst_writer": ("OTAN INTSUM TEMPLATE", "[highlights]"),
        "moc_watch_writer": ("OTAN SITREP TEMPLATE", "[units_in_sector]"),
        "j2x_humint_writer": ("OTAN SPOTREP TEMPLATE", "[coverage_analysis]"),
        "ctf_commander_writer": (
            "OTAN COMMANDER'S BRIEF TEMPLATE",
            "[decisions_required]",
        ),
        "admin_writer": ("OTAN INTSUM TEMPLATE", "[highlights]"),
    }
    for name, needles in expected.items():
        assert name in list_agent_names()
        prompt = load_agent_spec(name).system_prompt
        for needle in needles:
            assert needle in prompt, f"{name} missing {needle!r}"
