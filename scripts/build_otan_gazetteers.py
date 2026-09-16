#!/usr/bin/env python3
"""Split the NATO/OTAN C2 gazetteer into tokenizer annotation list files.

One ``.txt`` list per gazetteer ``type`` (the catalog ``label``), then register
those lists in ``annotation-resources.json``.

Usage:
    python3 scripts/build_otan_gazetteers.py
    python3 scripts/build_otan_gazetteers.py --source /path/to/gazetteer_c2_otan.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANY_DIR = ROOT / "tkeir" / "resources" / "modeling" / "tokenizer" / "any"
OTAN_DIR = ANY_DIR / "otan"
CATALOG_PATH = ANY_DIR / "annotation-resources.json"
REPO_SOURCE = OTAN_DIR / "gazetteer_c2_otan.json"

# Proper-name organizations, units, systems, and roles.
NAMED_ENTITY_TYPES = {
    "ORG",
    "UNIT",
    "CMD",
    "SYSTEM",
    "FACILITY",
    "FORUM",
    "ROLE",
}

LIST_PREFIX = "otan-"


def _slug(gazetteer_type: str) -> str:
    return gazetteer_type.strip().lower().replace("_", "-")


def _catalog_label(gazetteer_type: str) -> str:
    return "otan." + gazetteer_type.strip().lower()


def _unique_sorted_terms(rows: list[dict]) -> list[str]:
    """Keep first-seen casing; skip blanks and comment-looking lines."""
    seen: set[str] = set()
    unique: list[str] = []
    for row in rows:
        term = " ".join(str(row.get("term") or "").split())
        if not term or term.startswith("#"):
            continue
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(term)
    unique.sort(key=lambda value: (value.casefold(), value))
    return unique


def _write_list_file(path: Path, gazetteer_type: str, terms: list[str]) -> None:
    header = (
        f"# OTAN/NATO C2 terminology ({gazetteer_type}).\n"
        "# Source: otan/gazetteer_c2_otan.json. "
        "Rebuild: python3 scripts/build_otan_gazetteers.py\n"
        "\n"
    )
    path.write_text(header + "\n".join(terms) + "\n", encoding="utf-8")


def _list_entry(gazetteer_type: str) -> dict:
    slug = _slug(gazetteer_type)
    entry = {
        "format": {"type": "list"},
        "name": LIST_PREFIX + slug,
        "path": f"otan/{slug}.txt",
        "exceptions": [
            "stopwords.txt",
            "../en/stopwords.txt",
        ],
        "pos": "PROPN" if gazetteer_type in NAMED_ENTITY_TYPES else "NOUN",
        "add-ascii-folding": True,
        "label": _catalog_label(gazetteer_type),
    }
    if gazetteer_type in NAMED_ENTITY_TYPES:
        entry["type"] = "named-entity"
    else:
        entry["type"] = "concept"
    entry["weight"] = 10
    return entry


def _update_catalog(gazetteer_types: list[str]) -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    lists = catalog["data"][0]["lists"]
    kept = [item for item in lists if not str(item.get("name", "")).startswith(LIST_PREFIX)]
    otan_entries = [_list_entry(gazetteer_type) for gazetteer_type in gazetteer_types]
    catalog["data"][0]["lists"] = kept + otan_entries
    CATALOG_PATH.write_text(
        json.dumps(catalog, indent=4, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _resolve_source(cli_source: Path | None) -> Path:
    if cli_source is not None:
        return cli_source
    return REPO_SOURCE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Gazetteer JSON (default: tkeir/resources/modeling/tokenizer/any/otan/gazetteer_c2_otan.json).",
    )
    args = parser.parse_args(argv)

    source = _resolve_source(args.source)
    if not source.is_file():
        print(
            f"error: gazetteer not found: {source}\n"
            "Pass --source /path/to/gazetteer_c2_otan.json",
            file=sys.stderr,
        )
        return 1

    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        print("error: gazetteer must be a JSON array", file=sys.stderr)
        return 1

    by_type: dict[str, list[dict]] = defaultdict(list)
    for row in data:
        if not isinstance(row, dict):
            continue
        gazetteer_type = str(row.get("type") or row.get("label") or "").strip()
        if not gazetteer_type:
            continue
        by_type[gazetteer_type].append(row)

    if not by_type:
        print("error: no gazetteer rows with type/label", file=sys.stderr)
        return 1

    OTAN_DIR.mkdir(parents=True, exist_ok=True)
    if source.resolve() != REPO_SOURCE.resolve():
        shutil.copy2(source, REPO_SOURCE)

    # Drop previously generated lists that no longer exist in the source.
    for leftover in OTAN_DIR.glob("*.txt"):
        leftover.unlink()

    gazetteer_types = sorted(by_type)
    counts: list[tuple[str, int]] = []
    for gazetteer_type in gazetteer_types:
        terms = _unique_sorted_terms(by_type[gazetteer_type])
        _write_list_file(OTAN_DIR / f"{_slug(gazetteer_type)}.txt", gazetteer_type, terms)
        counts.append((gazetteer_type, len(terms)))

    _update_catalog(gazetteer_types)

    total = sum(count for _, count in counts)
    print(f"Wrote {len(gazetteer_types)} OTAN list files ({total} unique terms) under {OTAN_DIR}")
    for gazetteer_type, count in counts:
        print(f"  {gazetteer_type:14} {count:4}  {_catalog_label(gazetteer_type)}")
    print(f"Updated {CATALOG_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
