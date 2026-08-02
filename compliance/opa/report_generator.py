#!/usr/bin/env python3
"""Title: Report generator

Build HTML + JSON EU compliance audit reports from OPA evaluation outputs.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Shared one-page status table (also published into MkDocs).
_OPA_DIR = Path(__file__).resolve().parent
if str(_OPA_DIR) not in sys.path:
    sys.path.insert(0, str(_OPA_DIR))
from status_page import render_status_table_html  # noqa: E402


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _summary_of(blob: Any) -> dict[str, Any]:
    if (
        isinstance(blob, dict)
        and "summary" in blob
        and isinstance(blob["summary"], dict)
    ):
        return blob["summary"]
    if isinstance(blob, dict) and "result" in blob:
        try:
            return blob["result"][0]["expressions"][0]["value"]
        except (IndexError, KeyError, TypeError):
            pass
    return blob if isinstance(blob, dict) else {}


def build_report(
    input_data: dict[str, Any],
    summaries: dict[str, dict[str, Any]],
    version: str,
) -> dict[str, Any]:
    overall_violations = sum(
        int(s.get("violations_count") or 0) for s in summaries.values()
    )
    overall_passed = sum(int(s.get("passed_count") or 0) for s in summaries.values())
    overall_na = sum(int(s.get("not_applicable_count") or 0) for s in summaries.values())
    denom = overall_passed + overall_violations
    score = round((overall_passed / denom) * 100) if denom else 100
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": version,
        "ai_act_category": (
            (input_data.get("ai_act") or {})
            .get("classification", {})
            .get("determined_category")
        ),
        "compliant": overall_violations == 0,
        "compliance_score": score,
        "violations_count": overall_violations,
        "passed_count": overall_passed,
        "not_applicable_count": overall_na,
        "regulations": summaries,
        "input_meta": input_data.get("meta") or {},
    }


def _oscal_counts(ar_path: Path) -> dict[str, int] | None:
    data = _load(ar_path)
    results = data.get("assessment-results", {}).get("results") or []
    if not results:
        return None
    obs = results[0].get("observations") or []
    findings = results[0].get("findings") or []
    tallies = {"pass": 0, "fail": 0, "not-applicable": 0, "findings": len(findings)}
    for observation in obs:
        for prop in observation.get("props") or []:
            if prop.get("name") == "result":
                key = str(prop.get("value"))
                if key in tallies:
                    tallies[key] += 1
    return tallies


def _posture_trend(eu_audit_root: Path, current_version: str) -> list[dict[str, Any]]:
    """Read historical assessment_results.json under reports/compliance/eu-audit/*/oscal/."""
    rows: list[dict[str, Any]] = []
    if not eu_audit_root.is_dir():
        return rows
    for version_dir in sorted(eu_audit_root.iterdir()):
        if not version_dir.is_dir():
            continue
        ar = version_dir / "oscal" / "assessment_results.json"
        counts = _oscal_counts(ar)
        if counts is None:
            continue
        rows.append({"version": version_dir.name, **counts})
    # Ensure current appears even if just written
    if not any(r["version"] == current_version for r in rows):
        current = eu_audit_root / current_version / "oscal" / "assessment_results.json"
        counts = _oscal_counts(current)
        if counts:
            rows.append({"version": current_version, **counts})
    return rows[-12:]


def render_html(
    report: dict[str, Any],
    *,
    oscal_dir: Path | None = None,
    trend: list[dict[str, Any]] | None = None,
) -> str:
    rows = []
    for name, summary in (report.get("regulations") or {}).items():
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(name))}</td>"
            f"<td>{html.escape(str(summary.get('category') or summary.get('entity_type') or '—'))}</td>"
            f"<td>{'yes' if summary.get('compliant') else 'no'}</td>"
            f"<td>{summary.get('violations_count', 0)}</td>"
            f"<td>{summary.get('passed_count', 0)}</td>"
            f"<td>{summary.get('not_applicable_count', 0)}</td>"
            f"<td>{summary.get('compliance_score', 0)}</td>"
            "</tr>"
        )
    viol_blocks = []
    for name, summary in (report.get("regulations") or {}).items():
        for v in summary.get("violations") or []:
            viol_blocks.append(
                "<li>"
                f"<strong>{html.escape(str(name))}</strong> "
                f"{html.escape(str(v.get('article')))}: "
                f"{html.escape(str(v.get('message') or v.get('reason') or ''))}"
                "</li>"
            )

    oscal_section = ""
    if oscal_dir is not None:
        ar = oscal_dir / "assessment_results.json"
        poam = oscal_dir / "poam.json"
        poam_items = 0
        if poam.is_file():
            poam_data = _load(poam)
            poam_items = len(
                poam_data.get("plan-of-action-and-milestones", {}).get("poam-items")
                or []
            )
        total = (
            int(report.get("passed_count") or 0)
            + int(report.get("violations_count") or 0)
            + int(report.get("not_applicable_count") or 0)
        )
        trend_rows = []
        for item in trend or []:
            trend_rows.append(
                "<tr>"
                f"<td>{html.escape(str(item.get('version')))}</td>"
                f"<td>{item.get('pass', 0)}</td>"
                f"<td>{item.get('fail', 0)}</td>"
                f"<td>{item.get('not-applicable', 0)}</td>"
                f"<td>{item.get('findings', 0)}</td>"
                "</tr>"
            )
        oscal_section = f"""
  <h2>OSCAL exchange (NIST SP 800-53 / OSCAL 1.1.2)</h2>
  <p>Machine-readable artefacts for GRC / regulator ingestion:</p>
  <ul>
    <li><a href="oscal/assessment_results.json">assessment_results.json</a>
      {"✓" if ar.is_file() else "(pending)"}</li>
    <li><a href="oscal/poam.json">poam.json</a>
      {"✓" if poam.is_file() else "(pending)"} — open items: {poam_items}</li>
  </ul>
  <table>
    <thead>
      <tr>
        <th>Total controls (OPA)</th><th>Passed</th><th>Failed</th>
        <th>Not applicable</th><th>Open POA&amp;M</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>{total}</td>
        <td>{report.get('passed_count', 0)}</td>
        <td>{report.get('violations_count', 0)}</td>
        <td>{report.get('not_applicable_count', 0)}</td>
        <td>{poam_items}</td>
      </tr>
    </tbody>
  </table>
  <h3>Compliance posture over time</h3>
  <table>
    <thead>
      <tr>
        <th>Version</th><th>Pass</th><th>Fail</th>
        <th>Not applicable</th><th>Findings</th>
      </tr>
    </thead>
    <tbody>
      {''.join(trend_rows) if trend_rows else '<tr><td colspan="5">No historical OSCAL results yet</td></tr>'}
    </tbody>
  </table>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>T-KEIR EU Compliance Audit — {html.escape(str(report.get('version')))}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; }}
    th {{ background: #f0f0f0; }}
    .ok {{ color: #0a7; }}
    .bad {{ color: #c00; }}
    .meta {{ color: #555; }}
  </style>
</head>
<body>
  <h1>T-KEIR EU Compliance Audit</h1>
  <p class="meta">Version: {html.escape(str(report.get('version')))} ·
     Generated: {html.escape(str(report.get('generated_at')))}</p>
  <p>AI Act category: <strong>{html.escape(str(report.get('ai_act_category')))}</strong></p>
  <p>Overall:
    <strong class="{'ok' if report.get('compliant') else 'bad'}">
      {'COMPLIANT' if report.get('compliant') else 'GAPS FOUND'}
    </strong>
    · score {report.get('compliance_score')}%
    · violations {report.get('violations_count')}
  </p>
  <p><em>Engineering evidence mapping — not legal advice.</em></p>
  <h2>One-page compliance status</h2>
  {render_status_table_html(report, include_na=True)}
  <h2>Per regulation</h2>
  <table>
    <thead>
      <tr>
        <th>Regulation</th><th>Context</th><th>Compliant</th>
        <th>Violations</th><th>Passed</th><th>Not mandatory</th><th>Score</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
  <h2>Violations</h2>
  <ul>
    {''.join(viol_blocks) if viol_blocks else '<li>None</li>'}
  </ul>
  {oscal_section}
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--version", default="unknown")
    parser.add_argument("--ai-act", dest="ai_act", type=Path, required=True)
    parser.add_argument("--cra", dest="cra", type=Path, required=True)
    parser.add_argument("--gdpr", dest="gdpr", type=Path, required=True)
    parser.add_argument("--nis2", dest="nis2", type=Path, required=True)
    parser.add_argument("--dora", dest="dora", type=Path, required=True)
    parser.add_argument("--pld", dest="pld", type=Path, required=True)
    parser.add_argument(
        "--oscal-dir",
        type=Path,
        default=None,
        help="Directory with assessment_results.json / poam.json",
    )
    args = parser.parse_args(argv)

    input_data = _load(args.input)
    summaries = {
        "ai_act": _summary_of(_load(args.ai_act)),
        "cra": _summary_of(_load(args.cra)),
        "gdpr": _summary_of(_load(args.gdpr)),
        "nis2": _summary_of(_load(args.nis2)),
        "dora": _summary_of(_load(args.dora)),
        "pld": _summary_of(_load(args.pld)),
    }
    report = build_report(input_data, summaries, args.version)
    args.outdir.mkdir(parents=True, exist_ok=True)

    oscal_dir = args.oscal_dir or (args.outdir / "oscal")
    trend = _posture_trend(args.outdir.parent, args.version)

    json_path = args.outdir / "report.json"
    html_path = args.outdir / "report.html"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(
        render_html(report, oscal_dir=oscal_dir, trend=trend), encoding="utf-8"
    )
    print(f"[eu-audit] report: {html_path}")
    print(
        f"[eu-audit] compliant={report['compliant']} "
        f"score={report['compliance_score']} "
        f"violations={report['violations_count']}"
    )
    return 0 if report["compliant"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
