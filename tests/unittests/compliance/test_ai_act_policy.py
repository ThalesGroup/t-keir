"""Title: Ai act policy

AI Act OPA policy tests.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from opa_helpers import articles_of, eval_summary, load_fixture, requires_opa


@requires_opa
def test_minimal_risk_art5_pass_and_high_risk_not_mandatory():
    summary = eval_summary(
        "eu.ai_act", load_fixture("input_minimal_risk.json")
    )
    assert summary["category"] == "MINIMAL_RISK"
    assert summary["violations_count"] == 0
    assert summary["not_applicable_count"] > 0
    assert any(a.startswith("Art.5") for a in articles_of(summary["passed"]))
    na = articles_of(summary["not_applicable"])
    assert "Art.9(1)" in na
    assert "Art.14(1)" in na
    assert summary["compliance_score"] == 100


@requires_opa
def test_high_risk_missing_controls_violations():
    summary = eval_summary(
        "eu.ai_act", load_fixture("input_high_risk_violations.json")
    )
    assert summary["category"] == "HIGH_RISK"
    assert summary["violations_count"] > 0
    viol = articles_of(summary["violations"])
    assert any(a.startswith("Art.9") for a in viol)
    assert any(a.startswith("Art.12") for a in viol)
    assert any(a.startswith("Art.14") for a in viol)
    critical = [
        v for v in summary["violations"] if v.get("severity") == "CRITICAL"
    ]
    assert not any(
        str(v.get("article", "")).startswith("Art.5") for v in critical
    )


@requires_opa
def test_prohibited_unacceptable_art5_critical():
    summary = eval_summary("eu.ai_act", load_fixture("input_prohibited.json"))
    assert summary["category"] == "UNACCEPTABLE"
    viol = summary["violations"]
    assert len(viol) >= 1
    assert all(str(v.get("article", "")).startswith("Art.5") for v in viol)
    assert any(v.get("severity") == "CRITICAL" for v in viol)
    na = articles_of(summary["not_applicable"])
    assert "Art.9(1)" in na
    assert "Art.55(1)(a)" in na
    assert summary["not_applicable_count"] > 0


@requires_opa
def test_gpai_systemic_art55_applies_high_risk_not_mandatory():
    summary = eval_summary(
        "eu.ai_act", load_fixture("input_gpai_systemic.json")
    )
    assert summary["category"] == "GPAI_SYSTEMIC"
    na = articles_of(summary["not_applicable"])
    assert "Art.9(1)" in na
    assert "Art.16(a)" in na
    assert "Art.55(1)(a)" not in na
    active = articles_of(summary["violations"]) | articles_of(
        summary["passed"]
    )
    assert any(a.startswith("Art.55") for a in active)
