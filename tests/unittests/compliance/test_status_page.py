"""Title: Compliance status page unit tests

Runs Google-style docstring Examples via doctest and behavioral checks.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import doctest
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
OPA = ROOT / "compliance" / "opa"
if str(OPA) not in sys.path:
    sys.path.insert(0, str(OPA))

import status_page  # noqa: E402
from status_page import (  # noqa: E402
    collect_rows,
    criticality_counts,
    render_status_page_md,
    render_status_table_html,
)

DOCTEST_FLAGS = (
    doctest.NORMALIZE_WHITESPACE
    | doctest.ELLIPSIS
    | doctest.IGNORE_EXCEPTION_DETAIL
)


@pytest.fixture
def sample_report() -> dict:
    return {
        "compliant": False,
        "compliance_score": 40,
        "version": "test",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "ai_act_category": "LIMITED_RISK",
        "regulations": {
            "ai_act": {
                "compliant": False,
                "compliance_score": 50,
                "category": "LIMITED_RISK",
                "violations": [
                    {
                        "article": "Art.50(1)",
                        "severity": "HIGH",
                        "message": "Persons informed",
                        "remediation": "Attest transparency",
                    },
                    {
                        "article": "Art.5",
                        "severity": "CRITICAL",
                        "message": "Prohibited",
                        "remediation": "Remove practice",
                    },
                ],
                "passed": [
                    {
                        "article": "Art.72",
                        "message": "Incident notification",
                    }
                ],
                "not_applicable": [
                    {
                        "article": "Art.10",
                        "reason": "HIGH_RISK only",
                    }
                ],
            },
            "nis2": {
                "compliant": True,
                "compliance_score": 100,
                "entity_type": "OUT_OF_SCOPE",
                "violations": [],
                "passed": [],
                "not_applicable": [
                    {"article": "Art.1", "reason": "out of scope"}
                ],
            },
        },
    }


def test_status_page_docstring_examples() -> None:
    """Execute every ``Example:`` / ``>>>`` block in status_page.py."""
    importlib.reload(status_page)
    failures, tests = doctest.testmod(
        status_page, optionflags=DOCTEST_FLAGS, verbose=False
    )
    assert tests > 0, "No doctest examples discovered in status_page"
    assert failures == 0, f"{failures} doctest failure(s) in status_page"


def test_collect_rows_orders_fail_by_criticality(sample_report: dict) -> None:
    rows = collect_rows(sample_report)
    fails = [r for r in rows if r["status"] == "FAIL"]
    assert [r["criticality"] for r in fails] == ["CRITICAL", "HIGH"]
    assert fails[0]["remediation"] == "Remove practice"
    assert criticality_counts(rows) == {
        "CRITICAL": 1,
        "HIGH": 1,
        "MEDIUM": 0,
        "LOW": 0,
    }


def test_status_table_html_includes_colors_and_remediation(
    sample_report: dict,
) -> None:
    html = render_status_table_html(sample_report)
    assert "background:#c62828" in html  # FAIL
    assert "background:#2e7d32" in html  # PASS
    assert "Criticality" in html
    assert "Remove practice" in html
    assert "Attest transparency" in html


def test_status_page_md_wrapper(sample_report: dict) -> None:
    md = render_status_page_md(sample_report)
    assert "One-page compliance status" in md
    assert "LIMITED_RISK" in md
    assert "<table" in md
