#!/usr/bin/env python3
"""Title: Validate T-KEIR OSCAL JSON against NIST production schemas.

Uses the Draft-07 JSON Schema files vendored from the NIST OSCAL v1.1.2
release (https://github.com/usnistgov/OSCAL/releases/tag/v1.1.2).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

OSCAL_DIR = Path(__file__).resolve().parent
SCHEMA_DIR = OSCAL_DIR / "schemas" / "nist-v1.1.2"

# Root object key → NIST schema filename (OSCAL 1.1.2 release assets).
ROOT_TO_SCHEMA = {
    "assessment-results": "oscal_assessment-results_schema.json",
    "plan-of-action-and-milestones": "oscal_poam_schema.json",
    "assessment-plan": "oscal_assessment-plan_schema.json",
    "catalog": "oscal_catalog_schema.json",
    "profile": "oscal_profile_schema.json",
    "system-security-plan": "oscal_ssp_schema.json",
    "component-definition": "oscal_component_schema.json",
}


def _require_jsonschema():
    try:
        from jsonschema import Draft7Validator
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "jsonschema is required to validate OSCAL JSON.\n"
            "Install: pip install jsonschema\n"
            "or: cd tkeir && uv run --with jsonschema python "
            "../compliance/opa/oscal/validate_oscal.py"
        ) from exc
    return Draft7Validator


def detect_model(document: dict[str, Any]) -> str | None:
    """Return the OSCAL root key if this is a known model document."""
    for key in ROOT_TO_SCHEMA:
        if key in document:
            return key
    return None


def load_schema(model: str) -> dict[str, Any]:
    name = ROOT_TO_SCHEMA[model]
    path = SCHEMA_DIR / name
    if not path.is_file():
        raise FileNotFoundError(
            f"NIST OSCAL schema missing: {path} "
            "(see compliance/opa/oscal/schemas/README.md)"
        )
    return _pythonize_token_patterns(
        json.loads(path.read_text(encoding="utf-8"))
    )


def _pythonize_token_patterns(node: Any) -> Any:
    """NIST TokenDatatype uses ``\\p{L}`` / ``\\p{N}`` (XML Schema).

Python's ``re`` engine cannot compile those classes; map them to the ASCII
token alphabet used in this repo. The on-disk NIST schema files are not
modified.
    """
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if (
                key == "pattern"
                and isinstance(value, str)
                and r"\p{L}" in value
            ):
                out[key] = r"^[A-Za-z_][A-Za-z0-9.\-_]*$"
            else:
                out[key] = _pythonize_token_patterns(value)
        return out
    if isinstance(node, list):
        return [_pythonize_token_patterns(item) for item in node]
    return node


def iter_errors(document: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    Draft7Validator = _require_jsonschema()
    validator = Draft7Validator(schema)
    messages: list[str] = []
    for error in sorted(validator.iter_errors(document), key=lambda e: list(e.path)):
        path = "/".join(str(p) for p in error.absolute_path) or "<root>"
        messages.append(f"{path}: {error.message}")
    return messages


def validate_document(path: Path) -> tuple[str, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return "unknown", [f"{path}: document is not a JSON object"]
    model = detect_model(data)
    if model is None:
        return "unknown", [
            f"{path}: no OSCAL root key "
            f"(expected one of {', '.join(ROOT_TO_SCHEMA)})"
        ]
    return model, iter_errors(data, load_schema(model))


def default_static_docs() -> list[Path]:
    return [
        *sorted((OSCAL_DIR / "catalogs").glob("eu_*_catalog.json")),
        OSCAL_DIR / "profiles" / "tkeir_eu_profile.json",
        OSCAL_DIR / "component-definitions" / "tkeir_components.json",
        OSCAL_DIR / "ssp" / "tkeir_ssp.json",
        OSCAL_DIR / "assessments" / "assessment_plan.json",
    ]


def collect_generated(reports_root: Path) -> list[Path]:
    if not reports_root.is_dir():
        return []
    found: list[Path] = []
    for name in ("assessment_results.json", "poam.json"):
        found.extend(sorted(reports_root.glob(f"**/oscal/{name}")))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="OSCAL JSON files (default: static layer + latest audit reports)",
    )
    parser.add_argument(
        "--docs",
        type=Path,
        action="append",
        default=[],
        help="Directory of generated OSCAL files (assessment_results.json, poam.json)",
    )
    parser.add_argument(
        "--skip-static",
        action="store_true",
        help="Do not validate catalogs / profile / SSP / AP / components",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=OSCAL_DIR.parents[2],
        help="Repository root (for reports/ discovery)",
    )
    args = parser.parse_args(argv)

    targets: list[Path] = []
    if args.paths:
        targets.extend(args.paths)
    for folder in args.docs:
        targets.extend(
            p
            for p in (folder / "assessment_results.json", folder / "poam.json")
            if p.is_file()
        )
        targets.extend(sorted(folder.glob("*.json")))
    if not args.paths and not args.docs:
        if not args.skip_static:
            targets.extend(p for p in default_static_docs() if p.is_file())
        targets.extend(
            collect_generated(args.repo_root / "reports" / "compliance" / "eu-audit")
        )

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in targets:
        resolved = path.resolve()
        if resolved in seen or not path.is_file():
            continue
        seen.add(resolved)
        unique.append(path)

    if not unique:
        print("[oscal] No OSCAL JSON files to validate.", file=sys.stderr)
        return 0

    failures = 0
    for path in unique:
        rel: Path | str = path
        try:
            rel = path.resolve().relative_to(args.repo_root.resolve())
        except ValueError:
            pass
        model, errors = validate_document(path)
        if errors:
            failures += 1
            print(f"[oscal] FAIL {rel} ({model}) — {len(errors)} error(s)")
            for msg in errors[:40]:
                print(f"        {msg}")
            if len(errors) > 40:
                print(f"        … {len(errors) - 40} more")
        else:
            print(f"[oscal] OK   {rel} ({model})")
    if failures:
        print(
            f"[oscal] {failures}/{len(unique)} document(s) failed NIST OSCAL "
            "v1.1.2 JSON Schema validation.",
            file=sys.stderr,
        )
        return 1
    print(f"[oscal] {len(unique)} document(s) valid against NIST OSCAL v1.1.2.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
