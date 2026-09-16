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
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Fixed namespace for deterministic UUID v5 (RFC 4122 type 5 — NIST UUIDDatatype).
NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
TKEIR_NS = uuid.uuid5(NS, "tkeir.eu.compliance.oscal.v1")

# NIST SP 800-53A assessment methods (OSCAL observation.methods enum).
OSCAL_METHOD_TEST = "TEST"

# Stable document UUIDs (uuid5) shared with ssp/tkeir_ssp.json and
# assessments/assessment_plan.json so import-ap / subjects resolve.
SSP_UUID = str(uuid.uuid5(TKEIR_NS, "ssp|tkeir"))
OPA_COMPONENT_UUID = str(uuid.uuid5(TKEIR_NS, "component|opa"))
OSCAL_VERSION = "1.1.2"

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


def oscal_datetime(moment: datetime | None = None) -> str:
    """NIST DateTimeWithTimezoneDatatype requires a ``Z`` offset, not ``+00:00``."""
    stamp = moment or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    stamp = stamp.astimezone(timezone.utc).replace(microsecond=0)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


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
    now_iso = oscal_datetime()
    ar_uuid = det_uuid("assessment-results", version)

    findings: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []

    def _observation(
        *,
        result: str,
        title: str,
        description: str,
        control_id: str,
        extra_props: list[dict[str, str]] | None = None,
        include_subject: bool = True,
    ) -> dict[str, Any]:
        obs_uuid = det_uuid("obs", result, version, control_id)
        props = [
            {"name": "control-id", "value": control_id},
            {"name": "result", "value": result},
        ]
        if extra_props:
            props.extend(extra_props)
        obs: dict[str, Any] = {
            "uuid": obs_uuid,
            "title": title,
            "description": description or title,
            "methods": [OSCAL_METHOD_TEST],
            "types": ["finding"],
            "collected": now_iso,
            "props": props,
        }
        if include_subject and ssp_uuid:
            obs["subjects"] = [
                {
                    "subject-uuid": ssp_uuid,
                    "type": "component",
                    "title": "T-KEIR system",
                }
            ]
        return obs

    for reg_key, result_file in _discover_result_files(results_dir):
        data = json.loads(result_file.read_text(encoding="utf-8"))
        summary = _summary_of(data)

        for p in summary.get("passed") or []:
            article = str(p.get("article") or "")
            control_id = opa_article_to_control_id(reg_key, article)
            observations.append(
                _observation(
                    result="pass",
                    title=f"[PASS] {p.get('regulation', reg_key)} {article}",
                    description=p.get("message") or p.get("requirement") or "",
                    control_id=control_id,
                    extra_props=[
                        {
                            "name": "regulation",
                            "value": str(p.get("regulation") or reg_key),
                        }
                    ],
                )
            )

        for na in summary.get("not_applicable") or []:
            article = str(na.get("article") or "")
            control_id = opa_article_to_control_id(reg_key, article)
            observations.append(
                _observation(
                    result="not-applicable",
                    title=f"[NOT-APPLICABLE] {na.get('regulation', reg_key)} {article}",
                    description=na.get("reason")
                    or "Not applicable to this system category",
                    control_id=control_id,
                    extra_props=[
                        {"name": "reason", "value": str(na.get("reason") or "n-a")}
                    ],
                    include_subject=False,
                )
            )

        for v in summary.get("violations") or []:
            article = str(v.get("article") or "")
            control_id = opa_article_to_control_id(reg_key, article)
            severity = str(v.get("severity") or "MEDIUM")
            oscal_sev = SEVERITY_MAP.get(severity, "moderate")
            finding_uuid = det_uuid("finding", version, control_id)
            risk_uuid = det_uuid("risk", version, control_id)
            rem_uuid = det_uuid("remediation", version, control_id)
            requirement = v.get("message") or v.get("requirement") or ""
            remediation = v.get("remediation") or "See control guidance."
            due = datetime.now(timezone.utc) + DEADLINES.get(
                oscal_sev, timedelta(days=180)
            )

            obs = _observation(
                result="fail",
                title=f"[FAIL] {v.get('regulation', reg_key)} {article}",
                description=requirement,
                control_id=control_id,
                extra_props=[
                    {"name": "severity", "value": severity},
                    {"name": "remediation", "value": remediation},
                ],
            )
            observations.append(obs)

            risks.append(
                {
                    "uuid": risk_uuid,
                    "title": f"Risk: {article} not satisfied",
                    "description": requirement or f"{control_id} failed automated test",
                    "statement": remediation,
                    "status": "open",
                    "deadline": oscal_datetime(due),
                    "props": [
                        {"name": "likelihood", "value": oscal_sev},
                        {"name": "impact", "value": oscal_sev},
                    ],
                    "related-observations": [
                        {"observation-uuid": obs["uuid"]}
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
            )

            findings.append(
                {
                    "uuid": finding_uuid,
                    "title": (
                        f"{v.get('regulation', reg_key)} {article} — "
                        f"{str(requirement)[:80]}"
                    ).strip(" —"),
                    "description": requirement or f"{control_id} not satisfied",
                    "target": {
                        "type": "objective-id",
                        "target-id": control_id,
                        "status": {
                            "state": "not-satisfied",
                            "reason": "fail",
                            "remarks": requirement or control_id,
                        },
                    },
                    "related-observations": [{"observation-uuid": obs["uuid"]}],
                    "related-risks": [{"risk-uuid": risk_uuid}],
                }
            )

    result_body: dict[str, Any] = {
        "uuid": det_uuid("result", version),
        "title": f"Automated OPA Assessment — {version}",
        "description": (
            "Generated by compliance/opa/oscal/opa_to_oscal.py "
            "from OPA policy evaluation (NIST OSCAL 1.1.2 Assessment Results)."
        ),
        "start": now_iso,
        "end": now_iso,
        "reviewed-controls": {"control-selections": [{"include-all": {}}]},
    }
    if observations:
        result_body["observations"] = observations
    if risks:
        result_body["risks"] = risks
    if findings:
        result_body["findings"] = findings

    return {
        "assessment-results": {
            "uuid": ar_uuid,
            "metadata": {
                "title": f"T-KEIR EU Compliance Assessment Results — {version}",
                "last-modified": now_iso,
                "version": version,
                "oscal-version": OSCAL_VERSION,
            },
            "import-ap": {"href": "./assessment_plan.json"},
            "results": [result_body],
        }
    }


def build_poam(findings: list[dict[str, Any]], version: str) -> dict[str, Any]:
    now_iso = oscal_datetime()
    items: list[dict[str, Any]] = []

    for finding in findings:
        item_uuid = det_uuid("poam-item", version, finding["uuid"])
        items.append(
            {
                "uuid": item_uuid,
                "title": finding["title"],
                "description": finding.get("description") or finding["title"],
                "related-findings": [{"finding-uuid": finding["uuid"]}],
            }
        )
        remarks = (
            (finding.get("target") or {}).get("status", {}).get("remarks")
            or finding.get("description")
            or ""
        ).strip()
        if remarks:
            items[-1]["remarks"] = remarks

    if not items:
        items.append(
            {
                "uuid": det_uuid("poam-item", version, "none"),
                "title": "No open findings",
                "description": (
                    "Automated OPA assessment produced no unsatisfied controls."
                ),
            }
        )

    return {
        "plan-of-action-and-milestones": {
            "uuid": det_uuid("poam", version),
            "metadata": {
                "title": f"T-KEIR EU Compliance POA&M — {version}",
                "last-modified": now_iso,
                "version": version,
                "oscal-version": OSCAL_VERSION,
            },
            "import-ssp": {"href": "./tkeir_ssp.json"},
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
    parser.add_argument("--ssp-uuid", default=SSP_UUID)
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
    findings = ar["assessment-results"]["results"][0].get("findings") or []
    poam = build_poam(findings, args.version)

    ar_path = args.output_dir / "assessment_results.json"
    poam_path = args.output_dir / "poam.json"
    ar_path.write_text(json.dumps(ar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    poam_path.write_text(
        json.dumps(poam, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    oscal_root = Path(__file__).resolve().parent
    for src, dest_name in (
        (oscal_root / "assessments" / "assessment_plan.json", "assessment_plan.json"),
        (oscal_root / "ssp" / "tkeir_ssp.json", "tkeir_ssp.json"),
    ):
        if src.is_file():
            shutil.copy2(src, args.output_dir / dest_name)

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
