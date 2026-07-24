#!/usr/bin/env python3
"""Render Vespa .sd files from rag.yaml dual_hybrid rank-profile weights.

Usage:
    python scripts/generate_vespa_schemas.py
    python scripts/generate_vespa_schemas.py --check   # exit 1 if stale
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


def _load_context() -> dict:
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    dual = payload.get("dual_hybrid") or {}
    models = payload.get("models") or {}
    ranks = dual.get("rank_profiles") or {}
    avg = dual.get("average_field_length") or {}
    chunk_avg = avg.get("chunk") or {}
    doc_avg = avg.get("document") or {}
    chunk_profiles = ranks.get("chunk") or {}
    doc_profiles = ranks.get("document") or {}
    doc_profile = doc_profiles.get("document_bm25") or {
        "bm25_title": 0.30,
        "bm25_title_lemmatized": 0.20,
        "bm25_content": 0.30,
        "bm25_content_lemmatized": 0.20,
    }
    return {
        "config_path": "tkeir/configs/rag.yaml",
        "embedding_dim": int(models.get("embedding_dim", 384)),
        "chunk_profiles": chunk_profiles,
        "avg_text_raw": int(chunk_avg.get("text_raw", 180)),
        "avg_title": int(doc_avg.get("title", 12)),
        "avg_title_lemmatized": int(doc_avg.get("title_lemmatized", 7)),
        "avg_content": int(doc_avg.get("content", 800)),
        "avg_content_lemmatized": int(doc_avg.get("content_lemmatized", 420)),
        "doc_profile": doc_profile,
    }


def render_all() -> dict[str, str]:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    ctx = _load_context()
    return {
        "chunk.sd": env.get_template("chunk.sd.j2").render(**ctx),
        "tkeir_document.sd": env.get_template("tkeir_document.sd.j2").render(
            **ctx
        ),
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
        current = path.read_text(encoding="utf-8")
        if current != body:
            print(f"STALE {path} — run `make schemas`", file=sys.stderr)
            stale = True
    return 1 if stale else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed schemas differ from templates+config",
    )
    args = parser.parse_args()
    if not CONFIG_PATH.is_file():
        print(f"Missing config: {CONFIG_PATH}", file=sys.stderr)
        return 1
    if not TEMPLATE_DIR.is_dir():
        print(f"Missing templates: {TEMPLATE_DIR}", file=sys.stderr)
        return 1
    rendered = render_all()
    if args.check:
        return check_stale(rendered)
    write_schemas(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
