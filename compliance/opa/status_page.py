"""Title: One-page EU compliance status table

Shared HTML/Markdown renderer for the full OPA audit posture: status,
criticality (severity), and remediation for failed checks.

Public helpers use Google-style docstrings; ``Example:`` blocks are executed
by ``tests/unittests/compliance/test_status_page.py``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import html
from typing import Any

REG_ORDER = ("ai_act", "cra", "gdpr", "nis2", "dora", "pld")
REG_TITLES = {
    "ai_act": "AI Act",
    "cra": "CRA",
    "gdpr": "GDPR",
    "nis2": "NIS2",
    "dora": "DORA",
    "pld": "PLD",
}

# Display order for failed rows (highest criticality first).
_SEVERITY_RANK = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3,
    "": 4,
    "—": 4,
}

_STATUS_STYLE = {
    "FAIL": "background:#c62828;color:#fff",
    "PASS": "background:#2e7d32;color:#fff",
    "N/A": "background:#757575;color:#fff",
}

_CRIT_STYLE = {
    "CRITICAL": "background:#b71c1c;color:#fff",
    "HIGH": "background:#e65100;color:#fff",
    "MEDIUM": "background:#f9a825;color:#1a1a1a",
    "LOW": "background:#1565c0;color:#fff",
    "—": "background:#eeeeee;color:#555",
}


def _badge(label: str, style: str) -> str:
    """Render a colored HTML badge span.

    Args:
        label: Visible badge text (HTML-escaped).
        style: Inline CSS declarations (for example ``background:#c00;color:#fff``).

    Returns:
        An HTML ``<span>`` string for the badge.

    Example:
        >>> "<span" in _badge("FAIL", "background:#c62828;color:#fff")
        True
        >>> "FAIL" in _badge("FAIL", "background:#c62828;color:#fff")
        True
    """
    safe = html.escape(label)
    return (
        f'<span style="{style};padding:2px 8px;border-radius:4px;'
        f'font-size:0.8em;font-weight:600;white-space:nowrap">{safe}</span>'
    )


def _md_escape(value: Any) -> str:
    """Escape Markdown table-breaking characters in a scalar value.

    Args:
        value: Any value; ``None`` becomes an empty string.

    Returns:
        A single-line string safe for Markdown table cells.

    Example:
        >>> _md_escape("plain")
        'plain'
        >>> "\\\\|" in repr(_md_escape("a|b"))
        True
        >>> _md_escape(None)
        ''
    """
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").strip()


def collect_rows(
    report: dict[str, Any],
    *,
    include_na: bool = True,
) -> list[dict[str, str]]:
    """Flatten regulation summaries into status rows.

    Rows are ordered FAIL (by criticality CRITICAL→LOW), then PASS, then N/A.

    Args:
        report: Aggregate audit report (``regulations`` map from ``report.json``).
        include_na: When True, include ``not_applicable`` articles.

    Returns:
        List of row dicts with keys ``regulation``, ``article``, ``status``,
        ``criticality``, ``message``, ``remediation``.

    Example:
        >>> report = {
        ...     "regulations": {
        ...         "ai_act": {
        ...             "violations": [{
        ...                 "article": "Art.1",
        ...                 "severity": "HIGH",
        ...                 "message": "gap",
        ...                 "remediation": "fix",
        ...             }],
        ...             "passed": [{"article": "Art.2", "message": "ok"}],
        ...             "not_applicable": [],
        ...         }
        ...     }
        ... }
        >>> rows = collect_rows(report, include_na=False)
        >>> rows[0]["status"], rows[0]["criticality"], rows[0]["remediation"]
        ('FAIL', 'HIGH', 'fix')
    """
    rows: list[dict[str, str]] = []
    regs = report.get("regulations") or {}
    for name in REG_ORDER:
        summary = regs.get(name) or {}
        if not summary:
            continue
        title = REG_TITLES.get(name, name)
        for item in summary.get("violations") or []:
            rows.append(
                {
                    "regulation": title,
                    "article": str(item.get("article") or ""),
                    "status": "FAIL",
                    "criticality": str(item.get("severity") or "—").upper()
                    or "—",
                    "message": str(
                        item.get("message") or item.get("reason") or ""
                    ),
                    "remediation": str(item.get("remediation") or "—"),
                }
            )
        for item in summary.get("passed") or []:
            rows.append(
                {
                    "regulation": title,
                    "article": str(item.get("article") or ""),
                    "status": "PASS",
                    "criticality": "—",
                    "message": str(
                        item.get("message") or item.get("reason") or ""
                    ),
                    "remediation": "—",
                }
            )
        if include_na:
            for item in summary.get("not_applicable") or []:
                rows.append(
                    {
                        "regulation": title,
                        "article": str(item.get("article") or ""),
                        "status": "N/A",
                        "criticality": "—",
                        "message": str(
                            item.get("reason") or item.get("message") or ""
                        ),
                        "remediation": "—",
                    }
                )

    def sort_key(row: dict[str, str]) -> tuple:
        status_rank = {"FAIL": 0, "PASS": 1, "N/A": 2}.get(row["status"], 9)
        return (
            status_rank,
            _SEVERITY_RANK.get(row["criticality"], 9),
            row["regulation"],
            row["article"],
        )

    rows.sort(key=sort_key)
    return rows


def criticality_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    """Count open FAIL rows by criticality level.

    Args:
        rows: Output of :func:`collect_rows`.

    Returns:
        Map with keys ``CRITICAL``, ``HIGH``, ``MEDIUM``, ``LOW``.

    Example:
        >>> criticality_counts([
        ...     {"status": "FAIL", "criticality": "CRITICAL"},
        ...     {"status": "FAIL", "criticality": "HIGH"},
        ...     {"status": "PASS", "criticality": "—"},
        ... ])
        {'CRITICAL': 1, 'HIGH': 1, 'MEDIUM': 0, 'LOW': 0}
    """
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for row in rows:
        if row["status"] != "FAIL":
            continue
        key = row["criticality"]
        if key in counts:
            counts[key] += 1
    return counts


def render_status_table_html(
    report: dict[str, Any],
    *,
    include_na: bool = True,
    table_id: str = "compliance-status",
) -> str:
    """Build a colored HTML fragment: summary strip + full status table.

    Args:
        report: Aggregate audit report from ``report.json``.
        include_na: Forwarded to :func:`collect_rows`.
        table_id: HTML ``id`` for the wrapping ``<section>``.

    Returns:
        HTML string containing status/criticality badges and remediations.

    Example:
        >>> html_out = render_status_table_html({
        ...     "compliant": False,
        ...     "compliance_score": 50,
        ...     "regulations": {
        ...         "ai_act": {
        ...             "compliant": False,
        ...             "compliance_score": 50,
        ...             "violations": [{
        ...                 "article": "Art.1",
        ...                 "severity": "CRITICAL",
        ...                 "message": "gap",
        ...                 "remediation": "attest X",
        ...             }],
        ...             "passed": [],
        ...             "not_applicable": [],
        ...         }
        ...     },
        ... })
        >>> "Criticality" in html_out and "attest X" in html_out
        True
    """
    rows = collect_rows(report, include_na=include_na)
    crit = criticality_counts(rows)
    overall = "COMPLIANT" if report.get("compliant") else "GAPS FOUND"
    overall_style = (
        _STATUS_STYLE["PASS"]
        if report.get("compliant")
        else _STATUS_STYLE["FAIL"]
    )

    reg_chips: list[str] = []
    for name in REG_ORDER:
        summary = (report.get("regulations") or {}).get(name) or {}
        if not summary:
            continue
        ok = bool(summary.get("compliant"))
        chip = _badge(
            f"{REG_TITLES.get(name, name)} "
            f"{summary.get('compliance_score', 0)}%",
            _STATUS_STYLE["PASS"] if ok else _STATUS_STYLE["FAIL"],
        )
        reg_chips.append(chip)

    body_rows: list[str] = []
    for row in rows:
        status_badge = _badge(
            row["status"],
            _STATUS_STYLE.get(row["status"], _STATUS_STYLE["N/A"]),
        )
        crit_badge = _badge(
            row["criticality"],
            _CRIT_STYLE.get(row["criticality"], _CRIT_STYLE["—"]),
        )
        rem = row["remediation"] if row["status"] == "FAIL" else "—"
        body_rows.append(
            "<tr>"
            f"<td>{html.escape(row['regulation'])}</td>"
            f"<td><code>{html.escape(row['article'])}</code></td>"
            f"<td>{status_badge}</td>"
            f"<td>{crit_badge}</td>"
            f"<td>{html.escape(row['message'])}</td>"
            f"<td>{html.escape(rem)}</td>"
            "</tr>"
        )

    fail_n = sum(1 for r in rows if r["status"] == "FAIL")
    pass_n = sum(1 for r in rows if r["status"] == "PASS")
    na_n = sum(1 for r in rows if r["status"] == "N/A")

    return f"""
<section id="{html.escape(table_id)}" class="tkeir-compliance-status">
  <div style="margin:0.75rem 0 1rem 0;line-height:1.8">
    <strong>Overall:</strong>
    {_badge(overall, overall_style)}
    · score <strong>{html.escape(str(report.get('compliance_score', 0)))}%</strong>
    · fail {fail_n} · pass {pass_n} · n/a {na_n}
    · criticality open:
    {_badge(f"CRITICAL {crit['CRITICAL']}", _CRIT_STYLE['CRITICAL'])}
    {_badge(f"HIGH {crit['HIGH']}", _CRIT_STYLE['HIGH'])}
    {_badge(f"MEDIUM {crit['MEDIUM']}", _CRIT_STYLE['MEDIUM'])}
    {_badge(f"LOW {crit['LOW']}", _CRIT_STYLE['LOW'])}
  </div>
  <div style="margin:0 0 1rem 0;display:flex;flex-wrap:wrap;gap:0.35rem">
    {''.join(reg_chips)}
  </div>
  <table style="border-collapse:collapse;width:100%;font-size:0.92em">
    <thead>
      <tr>
        <th style="border:1px solid #ccc;padding:0.35rem 0.5rem;background:#f5f5f5;text-align:left">Regulation</th>
        <th style="border:1px solid #ccc;padding:0.35rem 0.5rem;background:#f5f5f5;text-align:left">Article</th>
        <th style="border:1px solid #ccc;padding:0.35rem 0.5rem;background:#f5f5f5;text-align:left">Status</th>
        <th style="border:1px solid #ccc;padding:0.35rem 0.5rem;background:#f5f5f5;text-align:left">Criticality</th>
        <th style="border:1px solid #ccc;padding:0.35rem 0.5rem;background:#f5f5f5;text-align:left">Message</th>
        <th style="border:1px solid #ccc;padding:0.35rem 0.5rem;background:#f5f5f5;text-align:left">Remediation</th>
      </tr>
    </thead>
    <tbody>
      {''.join(body_rows)}
    </tbody>
  </table>
  <p style="color:#555;font-size:0.85em;margin-top:0.75rem">
    Failures sorted by criticality (CRITICAL → LOW). Remediation is shown only
    for <strong>FAIL</strong> rows. Engineering evidence mapping — not legal advice.
  </p>
</section>
""".strip()


def render_status_page_md(report: dict[str, Any]) -> str:
    """Render the MkDocs body for the one-page compliance status.

    Args:
        report: Aggregate audit report from ``report.json``.

    Returns:
        Markdown text embedding the colored HTML status table.

    Example:
        >>> md = render_status_page_md({
        ...     "version": "1.0.0",
        ...     "generated_at": "2026-01-01T00:00:00+00:00",
        ...     "ai_act_category": "LIMITED_RISK",
        ...     "compliant": True,
        ...     "compliance_score": 100,
        ...     "regulations": {},
        ... })
        >>> "One-page compliance status" in md and "LIMITED_RISK" in md
        True
    """
    header = (
        "<!-- Generated by compliance/opa/scripts/gen_doc_results.py"
        " — do not edit by hand. -->\n"
    )
    version = _md_escape(report.get("version"))
    generated = _md_escape(report.get("generated_at"))
    category = _md_escape(report.get("ai_act_category"))
    table = render_status_table_html(report, include_na=True)
    return (
        f"{header}\n"
        f"**Version:** `{version}`  \n"
        f"**Generated (UTC):** `{generated}`  \n"
        f"**AI Act category:** `{category}`\n\n"
        "> One-page compliance status from the last "
        "`make audit-compliance` / `make ci` run — **not legal advice.**\n\n"
        f"{table}\n"
    )
