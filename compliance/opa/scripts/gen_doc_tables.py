#!/usr/bin/env python3
"""Title: Gen doc tables

Regenerate MkDocs article tables from OPA Rego catalogues.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from catalogue_parse import OWNER_LABEL, owner_for_checks, parse_rego_articles

POL = ROOT / "compliance" / "opa" / "policies"
LEGAL = ROOT / "compliance" / "opa" / "legal"
OUT = ROOT / "docs" / "compliance" / "generated"

GATE_LABELS = {
    "high_risk": "HIGH_RISK only",
    "high_risk_biometric": "HIGH_RISK + biometric",
    "high_risk_importer": "HIGH_RISK + importer role",
    "high_risk_distributor": "HIGH_RISK + distributor role",
    "high_risk_notified_body": "HIGH_RISK + notified body",
    "limited_or_high": "LIMITED_RISK or HIGH_RISK",
    "limited_or_high_emotion": "LIMITED/HIGH + emotion recognition",
    "limited_or_high_biometric_cat": "LIMITED/HIGH + biometric categorisation",
    "gpai": "GPAI_STANDARD or GPAI_SYSTEMIC",
    "gpai_systemic": "GPAI_SYSTEMIC only",
    "ai_system_active": "is_ai_system (not UNACCEPTABLE)",
    "all": "Always evaluated",
    "in_scope": "When regulation in scope",
}


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
        gate = gate_m.group(1) if gate_m else ""
        keys = re.findall(r'"key":\s*"([^"]+)"', chunk)
        paths: list[str] = []
        for path_lit in re.findall(r'"path":\s*\[([^\]]+)\]', chunk):
            paths.append(".".join(re.findall(r'"([^"]+)"', path_lit)))
        msgs = re.findall(r'"message":\s*"([^"]*)"', chunk)
        anchors: list[str] = []
        for key in keys:
            anchors.append(f"`evidence.{key}`")
        for path_name in paths:
            if path_name:
                anchors.append(f"`attestation.{path_name}`")
        seen: set[str] = set()
        uniq: list[str] = []
        for item in anchors:
            if item not in seen:
                seen.add(item)
                uniq.append(item)
        rows.append(
            {
                "id": aid,
                "gate": gate,
                "anchors": ", ".join(uniq) if uniq else "—",
                "message": msgs[0] if msgs else "",
            }
        )
    return rows


def md_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def article_anchor(article_id: str) -> str:
    """Stable HTML anchor for an OPA article id (``Art.5(1)`` → ``art-5-1``)."""
    return re.sub(r"[^a-zA-Z0-9]+", "-", article_id).strip("-").lower()


def load_legal(reg_key: str) -> dict:
    path = LEGAL / f"{reg_key}.yaml"
    if yaml is None or not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def legal_texts_markdown(reg_key: str, article_ids: list[str]) -> str:
    """Render exact EUR-Lex excerpts for each catalogue id."""
    legal = load_legal(reg_key)
    articles = legal.get("articles") or {}
    source = legal.get("source_url") or "https://eur-lex.europa.eu/"
    celex = legal.get("celex") or ""
    disclaimer = legal.get("disclaimer") or (
        "Official EU legal text. Not legal advice. © European Union, EUR-Lex."
    )
    lines = [
        HEADER,
        "",
        f"> **Source:** [EUR-Lex]({source})"
        + (f" (CELEX `{celex}`)" if celex else "")
        + f"  \n> {disclaimer}",
        "",
    ]
    if not articles:
        lines.append(
            "_Legal texts not bundled. Run "
            "`python3 compliance/opa/scripts/fetch_legal_texts.py` "
            f"then re-run this generator (`{reg_key}.yaml` missing)._\n"
        )
        return "\n".join(lines)

    for aid in article_ids:
        entry = articles.get(aid) or {}
        text = (entry.get("text") or "").strip()
        title = (entry.get("title") or "").strip()
        note = (entry.get("note") or "").strip()
        anchor = article_anchor(aid)
        heading = f"`{aid}`"
        if title:
            heading += f" — {title}"
        lines.append(f'<a id="{anchor}"></a>\n')
        lines.append(f"### {heading}\n")
        if note:
            lines.append(f"_{md_escape(note)}_\n")
        if text:
            quoted = "\n".join(f"> {line}" if line else ">" for line in text.splitlines())
            lines.append(quoted + "\n")
        else:
            lines.append("_No legal text available for this citation._\n")
        lines.append("")
    return "\n".join(lines)


def catalogue_ids_for(reg_key: str, path: Path | None = None) -> list[str]:
    ids: list[str] = []
    if reg_key == "ai_act":
        ids.extend(
            [
                "Art.5(1)(a)",
                "Art.5(1)(b)",
                "Art.5(1)(c)",
                "Art.5(1)(d)",
                "Art.5(1)(e)",
                "Art.5(1)(f)",
                "Art.5(1)(g)",
            ]
        )
    if path is not None:
        ids.extend(row["id"] for row in parse_articles(path))
    seen: set[str] = set()
    out: list[str] = []
    for aid in ids:
        if aid not in seen:
            seen.add(aid)
            out.append(aid)
    return out


def table(rows: list[dict[str, str]]) -> str:
    lines = [
        "| Article | Applicability gate | OPA check (evidence / attestation) | Requirement (policy message) |",
        "|---|---|---|---|",
    ]
    for row in rows:
        gate = GATE_LABELS.get(row["gate"], row["gate"] or "—")
        aid = row["id"]
        link = f"[`{aid}`](#{article_anchor(aid)})"
        lines.append(
            f"| {link} | {gate} | {row['anchors']} | {md_escape(row['message'])} |"
        )
    return "\n".join(lines)


def table_with_owner(path: Path) -> str:
    """GDPR/CRA catalogue table including who closes the control."""
    lines = [
        "| Article | Fix by | Applicability gate | OPA check | Requirement |",
        "|---|---|---|---|---|",
    ]
    for article in parse_rego_articles(path):
        owner = OWNER_LABEL[owner_for_checks(article["checks"])]
        gate = GATE_LABELS.get(article["gate"], article["gate"] or "—")
        checks = article["checks"]
        anchors: list[str] = []
        for check in checks:
            if check.get("key"):
                anchors.append(f"`evidence.{check['key']}`")
            if check.get("path"):
                anchors.append("`attestation." + ".".join(check["path"]) + "`")
        msg = checks[0]["message"] if checks else ""
        mark = ""
        if owner.startswith("Legal"):
            mark = " **(reviewer/legal — not code)**"
        aid = article["id"]
        link = f"[`{aid}`](#{article_anchor(aid)})"
        lines.append(
            f"| {link} | {owner}{mark} | {gate} | "
            f"{', '.join(anchors) if anchors else '—'} | {md_escape(msg)} |"
        )
    return "\n".join(lines)


ART5 = """| Article | Prohibited practice flag (`overrides.yaml`) | Severity if true |
|---|---|---|
| [`Art.5(1)(a)`](#art-5-1-a) | `prohibited_practices.subliminal_manipulation` | CRITICAL |
| [`Art.5(1)(b)`](#art-5-1-b) | `prohibited_practices.exploits_vulnerabilities` | CRITICAL |
| [`Art.5(1)(c)`](#art-5-1-c) | `prohibited_practices.social_scoring_public_authority` | CRITICAL |
| [`Art.5(1)(d)`](#art-5-1-d) | `prohibited_practices.real_time_biometric_public_space` | CRITICAL |
| [`Art.5(1)(e)`](#art-5-1-e) | `prohibited_practices.emotion_recognition_workplace_education` | CRITICAL |
| [`Art.5(1)(f)`](#art-5-1-f) | `prohibited_practices.biometric_categorisation_sensitive_attributes` | CRITICAL |
| [`Art.5(1)(g)`](#art-5-1-g) | `prohibited_practices.predictive_policing_individual` | CRITICAL |

**Rule:** Title II applies to **all** categories. If any flag is `true` (or
`determined_category == UNACCEPTABLE`), each active practice yields a CRITICAL
`violations[]` entry. If category is not `UNACCEPTABLE` and every flag is
`false`, all seven Art.5 checks emit `passed[]`. When category is
`UNACCEPTABLE`, every non-Art.5 article emits `NOT_MANDATORY`.
"""

HEADER = """<!-- Generated by compliance/opa/scripts/gen_doc_tables.py — do not edit by hand. -->
"""


def _write_texts(reg_key: str, path: Path | None) -> None:
    ids = catalogue_ids_for(reg_key, path)
    (OUT / f"{reg_key}_article_texts.md").write_text(
        legal_texts_markdown(reg_key, ids),
        encoding="utf-8",
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ai_path = POL / "ai_act" / "ai_act.rego"
    (OUT / "ai_act_articles.md").write_text(
        HEADER
        + "\n### Title II — Prohibited practices (Art.5)\n\n"
        + ART5
        + "\n\n### Title III–VI catalogue\n\n"
        + table(parse_articles(ai_path))
        + "\n",
        encoding="utf-8",
    )
    _write_texts("ai_act", ai_path)

    owned = {
        "cra": POL / "cra" / "cra.rego",
        "gdpr": POL / "gdpr" / "gdpr.rego",
    }
    for key, path in owned.items():
        (OUT / f"{key}_articles.md").write_text(
            HEADER
            + "\n"
            + "> **Fix by:** *Legal / reviewer (not code)* means a human must "
            "attest in `overrides.yaml` after review — shipping code alone "
            "cannot close the article.\n\n"
            + table_with_owner(path)
            + "\n",
            encoding="utf-8",
        )
        _write_texts(key, path)

    mapping = {
        "nis2": POL / "nis2" / "nis2.rego",
        "dora": POL / "dora" / "dora.rego",
        "pld": POL / "pld" / "pld.rego",
    }
    for key, path in mapping.items():
        (OUT / f"{key}_articles.md").write_text(
            HEADER + "\n" + table(parse_articles(path)) + "\n", encoding="utf-8"
        )
        _write_texts(key, path)

    print(f"wrote tables + article texts under {OUT}")


if __name__ == "__main__":
    main()
