"""Title: Report

Audit report rendering.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from typing import Any

from thot.action.models import ActionRecord
from thot.audit.hot_store import HotStore


def build_report(
    records: list[ActionRecord],
    *,
    correlation_id: str,
) -> dict[str, Any]:
    """Build a JSON audit report for one correlation id.

    Args:
        records: Actions belonging to the correlation.
        correlation_id: 32-hex W3C trace / correlation id.

    Returns:
        Report dict with schema ``tkeir.audit.report.v1``.

    Example:
        >>> from thot.action.models import ActionRecord
        >>> from thot.audit.report import build_report
        >>> cid = "i" * 32
        >>> report = build_report(
        ...     [ActionRecord(correlation_id=cid)], correlation_id=cid
        ... )
        >>> report["action_count"] == 1 and report["correlation_id"] == cid
        True
    """
    return {
        "schema": "tkeir.audit.report.v1",
        "correlation_id": correlation_id,
        "action_count": len(records),
        "actions": [
            record.model_dump(by_alias=True, mode="json") for record in records
        ],
    }


def render_html(report: dict[str, Any]) -> str:
    """Minimal HTML report (PDF deferred to Phase 9).

    Example:
        >>> from thot.audit.report import render_html
        >>> html = render_html(
        ...     {"correlation_id": "j" * 32, "actions": []}
        ... )
        >>> "Correlation" in html and "No records" in html
        True
    """
    cid = report.get("correlation_id", "")
    rows = []
    for action in report.get("actions") or []:
        intent = (action.get("intent") or {}).get("declared", "")
        actor = (action.get("actor") or {}).get("id", "")
        status = (action.get("execution") or {}).get("status", "")
        rows.append(
            f"<tr><td>{action.get('action_id')}</td>"
            f"<td>{intent}</td><td>{actor}</td><td>{status}</td></tr>"
        )
    body = "".join(rows) or "<tr><td colspan='4'>No records</td></tr>"
    return (
        "<!DOCTYPE html><html><head>"
        f"<title>Audit report {cid}</title></head><body>"
        f"<h1>Correlation {cid}</h1>"
        "<table border='1' cellpadding='4'>"
        "<tr><th>action_id</th><th>intent</th><th>actor</th><th>status</th></tr>"
        f"{body}</table></body></html>"
    )


def load_report(
    store: HotStore,
    correlation_id: str,
) -> dict[str, Any]:
    """Load and build a report from the hot store.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.action.models import ActionRecord
        >>> from thot.audit.hot_store import SqliteHotStore
        >>> from thot.audit.report import load_report
        >>> cid = "t" * 32
        >>> with tempfile.TemporaryDirectory() as td:
        ...     hot = SqliteHotStore(Path(td) / "hot.db")
        ...     _ = hot.append(ActionRecord(correlation_id=cid))
        ...     report = load_report(hot, cid)
        ...     hot.close()
        ...     report["action_count"] == 1
        True
    """
    records = store.get_by_correlation(correlation_id)
    return build_report(records, correlation_id=correlation_id)
