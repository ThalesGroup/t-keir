#!/usr/bin/env python3
"""Title: Gen oscal catalogs

Generate OSCAL 1.1.2 catalogs from OPA Rego article catalogues.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
POL = ROOT / "compliance" / "opa" / "policies"
OUT = Path(__file__).resolve().parent / "catalogs"

# Fixed namespace for deterministic UUID v5 (T-KEIR EU compliance OSCAL)
NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # URL namespace
TKEIR_NS = uuid.uuid5(NS, "tkeir.eu.compliance.oscal.v1")

REGULATIONS: dict[str, dict[str, str]] = {
    "ai_act": {
        "file": "ai_act/ai_act.rego",
        "out": "eu_ai_act_catalog.json",
        "title": "EU AI Act (Regulation 2024/1689) — OSCAL Control Catalog",
        "version": "2024/1689",
        "prefix": "ai-act",
        "uuid_key": "eu-ai-act-2024-1689",
    },
    "cra": {
        "file": "cra/cra.rego",
        "out": "eu_cra_catalog.json",
        "title": "EU CRA (Regulation 2024/2847) — OSCAL Control Catalog",
        "version": "2024/2847",
        "prefix": "cra",
        "uuid_key": "eu-cra-2024-2847",
    },
    "gdpr": {
        "file": "gdpr/gdpr.rego",
        "out": "eu_gdpr_catalog.json",
        "title": "EU GDPR (Regulation 2016/679) — OSCAL Control Catalog",
        "version": "2016/679",
        "prefix": "gdpr",
        "uuid_key": "eu-gdpr-2016-679",
    },
    "nis2": {
        "file": "nis2/nis2.rego",
        "out": "eu_nis2_catalog.json",
        "title": "EU NIS2 (Directive 2022/2555) — OSCAL Control Catalog",
        "version": "2022/2555",
        "prefix": "nis2",
        "uuid_key": "eu-nis2-2022-2555",
    },
    "dora": {
        "file": "dora/dora.rego",
        "out": "eu_dora_catalog.json",
        "title": "EU DORA (Regulation 2022/2554) — OSCAL Control Catalog",
        "version": "2022/2554",
        "prefix": "dora",
        "uuid_key": "eu-dora-2022-2554",
    },
    "pld": {
        "file": "pld/pld.rego",
        "out": "eu_pld_catalog.json",
        "title": "EU PLD (Directive 2024/2853) — OSCAL Control Catalog",
        "version": "2024/2853",
        "prefix": "pld",
        "uuid_key": "eu-pld-2024-2853",
    },
}


def det_uuid(*parts: str) -> str:
    return str(uuid.uuid5(TKEIR_NS, "|".join(parts)))


def article_to_control_id(prefix: str, article: str) -> str:
    slug = (
        article.lower()
        .replace("art.", "art-")
        .replace("annexi.", "annex-i-")
        .replace("annex i", "annex-i")
        .replace("annex ", "annex-")
        .replace("parti.", "part-i-")
        .replace("partii.", "part-ii-")
        .replace("part i", "part-i")
        .replace("part ii", "part-ii")
        .replace("§", "")
        .replace("(", "-")
        .replace(")", "")
        .replace(".", "-")
        .replace(" ", "-")
        .replace("--", "-")
        .strip("-")
    )
    # Avoid double prefix if already present
    if slug.startswith(prefix + "-"):
        return slug
    return f"{prefix}-{slug}"


def parse_articles(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r'\{\s*\n\s*"id":\s*"', text)
    rows: list[dict[str, str]] = []
    for block in blocks[1:]:
        match = re.match(r'([^"]+)"', block)
        if not match:
            continue
        chunk = block[:2500]
        aid = match.group(1)
        gate_m = re.search(r'"gate":\s*"([^"]+)"', chunk)
        gate = gate_m.group(1) if gate_m else "all"
        msgs = re.findall(r'"message":\s*"([^"]*)"', chunk)
        rems = re.findall(r'"remediation":\s*"([^"]*)"', chunk)
        keys = re.findall(r'"key":\s*"([^"]+)"', chunk)
        paths = []
        for path_lit in re.findall(r'"path":\s*\[([^\]]+)\]', chunk):
            paths.append(".".join(re.findall(r'"([^"]+)"', path_lit)))
        sev = re.findall(r'"severity":\s*"([^"]+)"', chunk)
        evidence = ", ".join(dict.fromkeys(keys + [p for p in paths if p]))
        rows.append(
            {
                "article": aid,
                "gate": gate,
                "message": msgs[0] if msgs else aid,
                "remediation": rems[0] if rems else "",
                "evidence": evidence,
                "severity": sev[0] if sev else "MEDIUM",
            }
        )
    return rows


def art5_controls(prefix: str) -> list[dict[str, Any]]:
    practices = [
        ("Art.5(1)(a)", "subliminal_manipulation", "No subliminal manipulation"),
        ("Art.5(1)(b)", "exploits_vulnerabilities", "No exploitation of vulnerabilities"),
        (
            "Art.5(1)(c)",
            "social_scoring_public_authority",
            "No public-authority social scoring",
        ),
        (
            "Art.5(1)(d)",
            "real_time_biometric_public_space",
            "No real-time remote biometric ID in public spaces",
        ),
        (
            "Art.5(1)(e)",
            "emotion_recognition_workplace_education",
            "No emotion recognition in workplace/education",
        ),
        (
            "Art.5(1)(f)",
            "biometric_categorisation_sensitive_attributes",
            "No biometric categorisation by sensitive attributes",
        ),
        (
            "Art.5(1)(g)",
            "predictive_policing_individual",
            "No predictive policing targeting individuals",
        ),
    ]
    controls = []
    for article, flag, title in practices:
        cid = article_to_control_id(prefix, article)
        controls.append(
            {
                "id": cid,
                "class": "prohibited-practice",
                "title": f"{article} — {title}",
                "props": [
                    {"name": "regulation", "value": "EU AI Act 2024/1689"},
                    {"name": "article", "value": article},
                    {"name": "applies-to", "value": "ALL"},
                    {"name": "severity-if-violated", "value": "CRITICAL"},
                    {"name": "opa-rule", "value": "eu.ai_act.violations"},
                    {
                        "name": "tkeir-evidence",
                        "value": f"overrides.yaml prohibited_practices.{flag}",
                    },
                ],
                "parts": [
                    {
                        "id": f"{cid}-statement",
                        "name": "statement",
                        "prose": title,
                    },
                    {
                        "id": f"{cid}-guidance",
                        "name": "guidance",
                        "prose": (
                            f"Check overrides.yaml prohibited_practices.{flag}. "
                            "Evidence: authorised representative attestation."
                        ),
                    },
                ],
            }
        )
    return controls


def build_catalog(reg_key: str, meta: dict[str, str]) -> dict[str, Any]:
    path = POL / meta["file"]
    rows = parse_articles(path)
    prefix = meta["prefix"]
    catalog_uuid = det_uuid("catalog", meta["uuid_key"])
    party_uuid = det_uuid("party", "thales")
    now = datetime(2024, 8, 1, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

    groups: list[dict[str, Any]] = []
    if reg_key == "ai_act":
        groups.append(
            {
                "id": "title-ii",
                "title": "Title II — Prohibited AI Practices",
                "controls": art5_controls(prefix),
            }
        )

    # Bucket remaining by gate
    by_gate: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_gate.setdefault(row["gate"] or "all", []).append(row)

    for gate, items in by_gate.items():
        controls = []
        for row in items:
            cid = article_to_control_id(prefix, row["article"])
            controls.append(
                {
                    "id": cid,
                    "class": f"{prefix}-obligation",
                    "title": f"{row['article']} — {row['message'][:80]}",
                    "props": [
                        {"name": "article", "value": row["article"]},
                        {"name": "applies-to", "value": gate},
                        {"name": "opa-rule", "value": f"eu.{reg_key}.violations"},
                        {"name": "tkeir-evidence", "value": row["evidence"] or "overrides.yaml"},
                        {
                            "name": "severity-if-violated",
                            "value": row["severity"],
                        },
                    ],
                    "parts": [
                        {
                            "id": f"{cid}-statement",
                            "name": "statement",
                            "prose": row["message"],
                        },
                        {
                            "id": f"{cid}-tkeir-implementation",
                            "name": "tkeir-implementation",
                            "prose": row["remediation"]
                            or (
                                f"Evidence anchors: {row['evidence'] or 'manual attestation'}."
                            ),
                        },
                    ],
                }
            )
        groups.append(
            {
                "id": f"gate-{gate}",
                "title": f"Controls (gate: {gate})",
                "props": [{"name": "applies-to-category", "value": gate}],
                "controls": controls,
            }
        )

    return {
        "catalog": {
            "uuid": catalog_uuid,
            "metadata": {
                "title": meta["title"],
                "last-modified": now,
                "version": meta["version"],
                "oscal-version": "1.1.2",
                "roles": [{"id": "creator", "title": "T-KEIR Compliance Team"}],
                "parties": [
                    {
                        "uuid": party_uuid,
                        "type": "organization",
                        "name": "Thales Group",
                    }
                ],
            },
            "groups": groups,
        }
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for reg_key, meta in REGULATIONS.items():
        catalog = build_catalog(reg_key, meta)
        out_path = OUT / meta["out"]
        out_path.write_text(
            json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        n = sum(len(g.get("controls") or []) for g in catalog["catalog"]["groups"])
        print(f"[oscal] {out_path.name}: {n} controls")


if __name__ == "__main__":
    main()
