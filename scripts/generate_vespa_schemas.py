#!/usr/bin/env python3
"""Render Vespa .sd files for doc_base / global / user from rag.yaml.

Retention / TTL fields (`doc_timestamp`, `freshness_ttl_seconds`, `pinned`,
`pin_reason`, `source_type`) live in ``templates/doc_base.sd.j2`` so both
``global`` and ``user`` inherit them. Keep-selection + GC interval are in
``vespa/vespa_app/services.xml`` (see ``docs/vespa_retention_migration.md``).

Usage:
    python scripts/generate_vespa_schemas.py
    python scripts/generate_vespa_schemas.py --check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "tkeir" / "configs" / "rag.yaml"
TEMPLATE_DIR = ROOT / "vespa" / "vespa_app" / "schemas" / "templates"
OUTPUT_DIR = ROOT / "vespa" / "vespa_app" / "schemas"

# BGE-M3 native dense size; sparse is mapped tensor (token{}).
DEFAULT_EMBEDDING_DIM = 1024


def _load_context() -> dict:
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    models = payload.get("models") or {}
    dual = payload.get("dual_hybrid") or {}
    ranks = (dual.get("rank_profiles") or {}).get("passage") or {}
    hybrid = ranks.get("hybrid") or {}
    dim = int(models.get("embedding_dim", DEFAULT_EMBEDDING_DIM))
    return {
        "config_path": "tkeir/configs/rag.yaml",
        "embedding_dim": dim,
        "w_dense": float(hybrid.get("dense", 0.55)),
        "w_sparse": float(hybrid.get("sparse", 0.30)),
        "w_bm25": float(hybrid.get("bm25", 0.15)),
    }


def render_all() -> dict[str, str]:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    ctx = _load_context()
    header = (
        f"# Generated from {ctx['config_path']} via `make schemas`.\n"
        f"# DO NOT hand-edit — change rag.yaml and regenerate.\n"
        f"# Source: scripts/generate_vespa_schemas.py\n"
    )
    return {
        "doc_base.sd": header + env.get_template("doc_base.sd.j2").render(**ctx),
        "global.sd": header + env.get_template("global.sd.j2").render(**ctx),
        "user.sd": header + env.get_template("user.sd.j2").render(**ctx),
    }


def write_schemas(rendered: dict[str, str]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, body in rendered.items():
        (OUTPUT_DIR / name).write_text(body, encoding="utf-8")
        print(f"Wrote {OUTPUT_DIR / name}")


def check_stale(rendered: dict[str, str]) -> int:
    stale = False
    for name, body in rendered.items():
        path = OUTPUT_DIR / name
        if not path.is_file():
            print(f"MISSING {path}", file=sys.stderr)
            stale = True
            continue
        if path.read_text(encoding="utf-8") != body:
            print(f"STALE {path}", file=sys.stderr)
            stale = True
    # Legacy dual-hybrid schemas must be gone.
    for legacy in ("chunk.sd", "tkeir_document.sd"):
        legacy_path = OUTPUT_DIR / legacy
        if legacy_path.is_file():
            print(f"LEGACY schema still present: {legacy_path}", file=sys.stderr)
            stale = True
    return 1 if stale else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if committed schemas are stale",
    )
    args = parser.parse_args()
    rendered = render_all()
    if args.check:
        return check_stale(rendered)
    write_schemas(rendered)
    # Remove legacy dual-hybrid schemas if still present.
    for legacy in ("chunk.sd", "tkeir_document.sd"):
        path = OUTPUT_DIR / legacy
        if path.is_file():
            path.unlink()
            print(f"Removed legacy {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
