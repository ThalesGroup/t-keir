"""CRA / GDPR / NIS2 / DORA / PLD OPA policy smoke tests."""

from __future__ import annotations

from opa_helpers import eval_summary, load_fixture, requires_opa


@requires_opa
def test_cra_summary_shape():
    summary = eval_summary("eu.cra", load_fixture("input_minimal_risk.json"))
    assert "CRA" in str(summary.get("regulation", ""))
    assert "violations_count" in summary
    assert "passed_count" in summary
    assert "not_applicable_count" in summary
    assert "compliance_score" in summary
    assert isinstance(summary.get("articles_covered"), list)
    assert len(summary["articles_covered"]) > 0


@requires_opa
def test_gdpr_summary_shape():
    summary = eval_summary("eu.gdpr", load_fixture("input_minimal_risk.json"))
    assert "violations_count" in summary
    assert summary["compliance_score"] >= 0


@requires_opa
def test_nis2_out_of_scope_all_not_mandatory():
    summary = eval_summary("eu.nis2", load_fixture("input_minimal_risk.json"))
    assert summary.get("entity_type") == "OUT_OF_SCOPE"
    assert summary["violations_count"] == 0
    assert summary["not_applicable_count"] > 0


@requires_opa
def test_dora_out_of_scope_all_not_mandatory():
    summary = eval_summary("eu.dora", load_fixture("input_minimal_risk.json"))
    assert summary["violations_count"] == 0
    assert summary["not_applicable_count"] > 0


@requires_opa
def test_pld_out_of_scope_all_not_mandatory():
    summary = eval_summary("eu.pld", load_fixture("input_minimal_risk.json"))
    assert summary["violations_count"] == 0
    assert summary["not_applicable_count"] > 0
