#!/usr/bin/env python3
"""Title: Bridge: OPA JSON results → OSCAL Assessment Results + POA&M (OSCAL 1.1.2).

UUIDs are deterministic (UUID v5) so diffs between runs show genuine changes only.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Fixed namespace for deterministic UUID v5
NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
TKEIR_NS = uuid.uuid5(NS, "tkeir.eu.compliance.oscal.v1")

SEVERITY_MAP = {
    "CRITICAL": "very-high",
    "HIGH": "high",
    "MEDIUM": "moderate",
    "LOW": "low",
    "INFO": "informational",
}

DEADLINES = {
    "very-high": timedelta(days=30),
    "high": timedelta(days=90),
    "moderate": timedelta(days=180),
    "low": timedelta(days=365),
    "informational": timedelta(days=365),
}

REG_PREFIX = {
    "ai_act": "ai-act",
    "cra": "cra",
    "gdpr": "gdpr",
    "nis2": "nis2",
    "dora": "dora",
    "pld": "pld",
}


def det_uuid(*parts: str) -> str:
    return str(uuid.uuid5(TKEIR_NS, "|".join(parts)))


def opa_article_to_control_id(regulation: str, article: str) -> str:
    """Convert OPA article string to OSCAL control-id slug."""
    prefix = REG_PREFIX.get(regulation, regulation.lower().replace("_", "-"))
    slug = (
        article.lower()
        .replace("art.", "art-")
        .replace("annexi.", "annex-i-")
        .replace("annex i", "annex-i")
        .replace("annex ", "annex-")
        .replace("parti.", "part-i-")
        .replace("partii.", "part-ii-")
        .replace("§", "")
        .replace("(", "-")
        .replace(")", "")
        .replace(".", "-")
        .replace(" ", "-")
        .replace("--", "-")
        .strip("-")
    )
    if slug.startswith(prefix + "-"):
        return slug
    return f"{prefix}-{slug}"


def _summary_of(blob: Any) -> dict[str, Any]:
    if isinstance(blob, dict) and "summary" in blob and isinstance(blob["summary"], dict):
        return blob["summary"]
    if isinstance(blob, dict) and "result" in blob:
        try:
            return blob["result"][0]["expressions"][0]["value"]
        except (IndexError, KeyError, TypeError):
            pass
    return blob if isinstance(blob, dict) else {}


def _discover_result_files(results_dir: Path) -> list[tuple[str, Path]]:
    """Accept opa-<reg>.json (current) or result_<reg>.json (spec alias)."""
    found: list[tuple[str, Path]] = []
    for path in sorted(results_dir.glob("opa-*.json")):
        reg = path.stem.replace("opa-", "")
        found.append((reg, path))
    if found:
        return found
    for path in sorted(results_dir.glob("result_*.json")):
        reg = path.stem.replace("result_", "")
        found.append((reg, path))
    return found


def build_assessment_results(
    results_dir: Path,
    ssp_uuid: str,
    version: str,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    ar_uuid = det_uuid("assessment-results", version)

    findings: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []

    for reg_key, result_file in _discover_result_files(results_dir):
        data = json.loads(result_file.read_text(encoding="utf-8"))
        summary = _summary_of(data)

        for p in summary.get("passed") or []:
            article = str(p.get("article") or "")
            control_id = opa_article_to_control_id(reg_key, article)
            obs_uuid = det_uuid("obs", "pass", version, control_id)
            observations.append(
                {
                    "uuid": obs_uuid,
                    "title": f"[PASS] {p.get('regulation', reg_key)} {article}",
                    "description": p.get("message") or p.get("requirement") or "",
                    "methods": ["AUTOMATED"],
                    "types": ["finding"],
                    "subjects": [{"subject-uuid": ssp_uuid, "type": "component"}],
                    "collected": now_iso,
                    "props": [
                        {"name": "control-id", "value": control_id},
                        {"name": "result", "value": "pass"},
                        {"name": "regulation", "value": str(p.get("regulation") or reg_key)},
                    ],
                }
            )

        for na in summary.get("not_applicable") or []:
            article = str(na.get("article") or "")
            control_id = opa_article_to_control_id(reg_key, article)
            obs_uuid = det_uuid("obs", "na", version, control_id)
            observations.append(
                {
                    "uuid": obs_uuid,
                    "title": f"[NOT-APPLICABLE] {na.get('regulation', reg_key)} {article}",
                    "description": na.get("reason") or "Not applicable to this system category",
                    "methods": ["AUTOMATED"],
                    "types": ["finding"],
                    "collected": now_iso,
                    "props": [
                        {"name": "control-id", "value": control_id},
                        {"name": "result", "value": "not-applicable"},
                        {"name": "reason", "value": str(na.get("reason") or "")},
                    ],
                }
            )

        for v in summary.get("violations") or []:
            article = str(v.get("article") or "")
            control_id = opa_article_to_control_id(reg_key, article)
            severity = str(v.get("severity") or "MEDIUM")
            oscal_sev = SEVERITY_MAP.get(severity, "moderate")
            finding_uuid = det_uuid("finding", version, control_id)
            obs_uuid = det_uuid("obs", "fail", version, control_id)
            risk_uuid = det_uuid("risk", version, control_id)
            rem_uuid = det_uuid("remediation", version, control_id)
            requirement = v.get("message") or v.get("requirement") or ""
            remediation = v.get("remediation") or ""

            observations.append(
                {
                    "uuid": obs_uuid,
                    "title": f"[FAIL] {v.get('regulation', reg_key)} {article}",
                    "description": requirement,
                    "methods": ["AUTOMATED"],
                    "types": ["finding"],
                    "collected": now_iso,
                    "props": [
                        {"name": "control-id", "value": control_id},
                        {"name": "result", "value": "fail"},
                        {"name": "severity", "value": severity},
                        {"name": "remediation", "value": remediation},
                    ],
                }
            )

            findings.append(
                {
                    "uuid": finding_uuid,
                    "title": f"{v.get('regulation', reg_key)} {article} — {str(requirement)[:80]}",
                    "description": requirement,
                    "target": {
                        "type": "objective-id",
                        "target-id": control_id,
                        "status": {
                            "state": "not-satisfied",
                            "reason": "fail",
                            "remarks": requirement,
                        },
                    },
                    "related-observations": [{"observation-uuid": obs_uuid}],
                    "risks": [
                        {
                            "uuid": risk_uuid,
                            "title": f"Risk: {article} not satisfied",
                            "description": requirement,
                            "statement": remediation,
                            "status": "open",
                            "characterizations": [
                                {
                                    "facets": [
                                        {
                                            "name": "likelihood",
                                            "system": "https://nvd.nist.gov/vuln-metrics/cvss",
                                            "value": oscal_sev,
                                        },
                                        {
                                            "name": "impact",
                                            "system": "https://nvd.nist.gov/vuln-metrics/cvss",
                                            "value": oscal_sev,
                                        },
                                    ]
                                }
                            ],
                            "remediations": [
                                {
                                    "uuid": rem_uuid,
                                    "lifecycle": "recommendation",
                                    "title": "Remediation",
                                    "description": remediation,
                                }
                            ],
                        }
                    ],
                }
            )

    result_uuid = det_uuid("result", version)
    return {
        "assessment-results": {
            "uuid": ar_uuid,
            "metadata": {
                "title": f"T-KEIR EU Compliance Assessment Results — {version}",
                "last-modified": now_iso,
                "version": version,
                "oscal-version": "1.1.2",
            },
            "import-ap": {"href": "../../assessments/assessment_plan.json"},
            "results": [
                {
                    "uuid": result_uuid,
                    "title": f"Automated OPA Assessment — {version}",
                    "description": (
                        "Generated by compliance/opa/oscal/opa_to_oscal.py "
                        "from OPA policy evaluation."
                    ),
                    "start": now_iso,
                    "end": now_iso,
                    "reviewed-controls": {
                        "control-selections": [{"include-all": {}}]
                    },
                    "observations": observations,
                    "findings": findings,
                }
            ],
        }
    }


def build_poam(findings: list[dict[str, Any]], version: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []

    for finding in findings:
        risk = (finding.get("risks") or [{}])[0]
        facets = ((risk.get("characterizations") or [{}])[0].get("facets") or [{}])
        severity = "moderate"
        for facet in facets:
            if facet.get("name") == "impact":
                severity = str(facet.get("value") or "moderate")
                break
        due = (now + DEADLINES.get(severity, timedelta(days=180))).date().isoformat()
        rem = ((risk.get("remediations") or [{}])[0]).get("description") or ""
        item_uuid = det_uuid("poam-item", version, finding["uuid"])
        ms_uuid = det_uuid("milestone", version, finding["uuid"])

        items.append(
            {
                "uuid": item_uuid,
                "title": finding["title"],
                "description": finding.get("description") or "",
                "related-findings": [{"finding-uuid": finding["uuid"]}],
                "origins": [],
                "status": {"state": "open"},
                "remarks": rem,
                "milestones": [
                    {
                        "uuid": ms_uuid,
                        "title": "Remediate finding",
                        "description": rem,
                        "due-date": due,
                    }
                ],
            }
        )

    return {
        "plan-of-action-and-milestones": {
            "uuid": det_uuid("poam", version),
            "metadata": {
                "title": f"T-KEIR EU Compliance POA&M — {version}",
                "last-modified": now.isoformat(),
                "version": version,
                "oscal-version": "1.1.2",
            },
            "import-ssp": {"href": "../../ssp/tkeir_ssp.json"},
            "poam-items": items,
        }
    }


def diff_assessment_results(baseline: Path, current: Path) -> dict[str, Any]:
    def counts(path: Path) -> dict[str, int]:
        data = json.loads(path.read_text(encoding="utf-8"))
        results = data.get("assessment-results", {}).get("results") or []
        if not results:
            return {"pass": 0, "fail": 0, "not-applicable": 0, "findings": 0}
        obs = results[0].get("observations") or []
        findings = results[0].get("findings") or []
        tallies = {"pass": 0, "fail": 0, "not-applicable": 0, "findings": len(findings)}
        for o in obs:
            for prop in o.get("props") or []:
                if prop.get("name") == "result":
                    key = str(prop.get("value"))
                    if key in tallies:
                        tallies[key] += 1
        return tallies

    b = counts(baseline)
    c = counts(current)
    return {
        "baseline": str(baseline),
        "current": str(current),
        "baseline_counts": b,
        "current_counts": c,
        "delta": {k: c.get(k, 0) - b.get(k, 0) for k in ("pass", "fail", "not-applicable", "findings")},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--ssp-uuid", default="tkeir-ssp-v2")
    parser.add_argument("--version", default="unknown")
    parser.add_argument("--diff", action="store_true")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--current", type=Path)
    args = parser.parse_args(argv)

    if args.diff:
        if not args.baseline or not args.current:
            parser.error("--diff requires --baseline and --current")
        report = diff_assessment_results(args.baseline, args.current)
        print(json.dumps(report, indent=2))
        return 0

    if not args.results_dir or not args.output_dir:
        parser.error("--results-dir and --output-dir are required (unless --diff)")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ar = build_assessment_results(args.results_dir, args.ssp_uuid, args.version)
    findings = ar["assessment-results"]["results"][0]["findings"]
    poam = build_poam(findings, args.version)

    ar_path = args.output_dir / "assessment_results.json"
    poam_path = args.output_dir / "poam.json"
    ar_path.write_text(json.dumps(ar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    poam_path.write_text(
        json.dumps(poam, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # Also mirror into tracked oscal/assessments/assessment_results for history hooks
    mirror = (
        Path(__file__).resolve().parent
        / "assessments"
        / "assessment_results"
        / f"assessment_results_{re.sub(r'[^A-Za-z0-9._-]+', '_', args.version)}.json"
    )
    try:
        mirror.write_text(ar_path.read_text(encoding="utf-8"), encoding="utf-8")
    except OSError:
        pass

    print(f"[oscal] Assessment Results → {ar_path}")
    print(f"[oscal] POA&M              → {poam_path}")
    print(f"[oscal] Open findings: {len(findings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
