#!/usr/bin/env python3
"""Write reports/fuzzing/summary.json from atheris artefacts."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--corpus-dir", required=True, type=Path)
    args = parser.parse_args()

    root = args.report_dir
    corpus = args.corpus_dir
    root.mkdir(parents=True, exist_ok=True)
    corpus.mkdir(parents=True, exist_ok=True)

    for crash in root.glob("crash-*"):
        dest = corpus / crash.name
        if not dest.exists():
            dest.write_bytes(crash.read_bytes())

    logs = (
        list(root.glob("*.log"))
        + list(root.glob("crash-*"))
        + list(root.glob("leak-*"))
    )
    radamsa_summary = root / "radamsa-summary.json"
    radamsa_meta = {}
    if radamsa_summary.is_file():
        try:
            radamsa_meta = json.loads(radamsa_summary.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            radamsa_meta = {"error": "invalid radamsa-summary.json"}
    summary = {
        "target": "tests/fuzzing/fuzz_targets",
        "crashes": len(list(root.glob("crash-*"))),
        "radamsa_crashes": len(list(root.glob("crash-radamsa-*"))),
        "radamsa": radamsa_meta,
        "runs": int(os.environ.get("FUZZ_RUNS", "0") or 0),
        "corpus_size": len([p for p in corpus.iterdir() if p.is_file()]),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "logs": [p.name for p in logs],
    }
    out = root / "summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
