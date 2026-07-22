#!/usr/bin/env python3
"""Title: Catalogue parse

Parse OPA Rego article catalogues into structured Python objects.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _extract_checks(block: str) -> list[dict[str, Any]]:
    """Parse ``checks: [ {…}, … ]`` objects from one article block."""
    checks: list[dict[str, Any]] = []
    # Split on object starts inside checks array (heuristic, catalogue-style Rego).
    for chunk in re.split(r"\{\s*\n\s*\"source\":", block):
        if '"severity"' not in chunk and "severity" not in chunk[:200]:
            # First split piece is preamble before first check.
            if not chunk.strip().startswith('"'):
                continue
        if not chunk.lstrip().startswith('"'):
            chunk = '"source":' + chunk
        else:
            chunk = '"source":' + chunk if not chunk.startswith('"source"') else chunk
        src_m = re.search(r'"source":\s*"([^"]+)"', chunk)
        if not src_m:
            continue
        sev_m = re.search(r'"severity":\s*"([^"]+)"', chunk)
        msg_m = re.search(r'"message":\s*"([^"]*)"', chunk)
        rem_m = re.search(r'"remediation":\s*"([^"]*)"', chunk)
        key_m = re.search(r'"key":\s*"([^"]+)"', chunk)
        path_m = re.search(r'"path":\s*\[([^\]]*)\]', chunk)
        path: list[str] = []
        if path_m:
            path = re.findall(r'"([^"]+)"', path_m.group(1))
        checks.append(
            {
                "source": src_m.group(1),
                "severity": sev_m.group(1) if sev_m else "",
                "message": msg_m.group(1) if msg_m else "",
                "remediation": rem_m.group(1) if rem_m else "",
                "key": key_m.group(1) if key_m else None,
                "path": path,
            }
        )
    return checks


def parse_rego_articles(path: Path) -> list[dict[str, Any]]:
    """Return catalogue articles with id, gate, and checks."""
    text = path.read_text(encoding="utf-8")
    # Restrict to the articles = [ ... ] array when present.
    art_m = re.search(r"articles\s*=\s*\[", text)
    body = text[art_m.start() :] if art_m else text
    blocks = re.split(r'\{\s*\n\s*"id":\s*"', body)
    rows: list[dict[str, Any]] = []
    for block in blocks[1:]:
        match = re.match(r'([^"]+)"', block)
        if not match:
            continue
        aid = match.group(1)
        gate_m = re.search(r'"gate":\s*"([^"]+)"', block[:400])
        # Truncate at next top-level article-ish end: look for checks then closing.
        # Use a generous window of the article object.
        end = block.find('\n  },\n  {\n    "id":')
        if end < 0:
            end = block.find("\n]\n\nviolations")
        chunk = block if end < 0 else block[:end]
        checks = _extract_checks(chunk)
        rows.append(
            {
                "id": aid,
                "gate": gate_m.group(1) if gate_m else "",
                "checks": checks,
            }
        )
    return rows


def owner_for_checks(checks: list[dict[str, Any]]) -> str:
    """Classify who can close the article: engineering, legal, or hybrid."""
    sources = {c.get("source") for c in checks}
    if sources <= {"attestation"}:
        return "legal"
    if sources <= {"evidence", "evidence_gte"}:
        return "engineering"
    if "attestation" in sources and sources & {"evidence", "evidence_gte", "either"}:
        return "hybrid"
    if sources == {"either"} or "either" in sources:
        return "hybrid"
    if "attestation" in sources:
        return "legal"
    return "engineering"


OWNER_LABEL = {
    "legal": "Legal / reviewer (not code)",
    "engineering": "Engineering / automatic",
    "hybrid": "Engineering or legal attestation",
}
