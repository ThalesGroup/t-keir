#!/usr/bin/env python3
"""Estimate averageFieldLength values from pipeline JSON (or Vespa summaries).

Writes suggested values under dual_hybrid.average_field_length in rag.yaml.
Does not overwrite other keys.

Usage:
    python scripts/measure_field_lengths.py -i workspace/tmp/pipeline-out
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "tkeir" / "configs" / "rag.yaml"


def _token_len(text: str) -> int:
    return len((text or "").split())


def measure_directory(input_dir: Path) -> dict[str, dict[str, float]]:
    title_lens: list[int] = []
    content_lens: list[int] = []
    chunk_lens: list[int] = []
    for path in sorted(input_dir.glob("*.pipeline.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        title_lens.append(_token_len(str(doc.get("title") or "")))
        content = doc.get("content") or []
        if isinstance(content, list):
            content_lens.append(sum(_token_len(str(part)) for part in content))
        else:
            content_lens.append(_token_len(str(content)))
        for chunk in doc.get("golden_chunks") or []:
            text = chunk.get("text_raw") or chunk.get("text") or ""
            if text:
                chunk_lens.append(_token_len(str(text)))

    def avg(values: list[int], fallback: int) -> int:
        if not values:
            return fallback
        return max(1, int(round(statistics.mean(values))))

    # Lemmatized lengths are typically shorter; apply a conservative ratio.
    title = avg(title_lens, 12)
    content = avg(content_lens, 800)
    text_raw = avg(chunk_lens, 180)
    return {
        "chunk": {"text_raw": text_raw},
        "document": {
            "title": title,
            "title_lemmatized": max(1, int(round(title * 0.6))),
            "content": content,
            "content_lemmatized": max(1, int(round(content * 0.55))),
        },
    }


def patch_config(averages: dict[str, dict[str, float]]) -> None:
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    dual = payload.setdefault("dual_hybrid", {})
    dual["average_field_length"] = averages
    CONFIG_PATH.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"Updated {CONFIG_PATH} average_field_length:")
    print(yaml.safe_dump(averages, sort_keys=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        required=True,
        help="Directory of *.pipeline.json files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print averages without writing rag.yaml",
    )
    args = parser.parse_args()
    if not args.input.is_dir():
        raise SystemExit(f"Not a directory: {args.input}")
    averages = measure_directory(args.input)
    if args.dry_run:
        print(yaml.safe_dump(averages, sort_keys=False))
        return 0
    patch_config(averages)
    print("Re-run `make schemas` after updating average_field_length.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
