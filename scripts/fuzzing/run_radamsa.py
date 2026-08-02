#!/usr/bin/env python3
"""Mutate corpus seeds with radamsa and feed fuzz targets.

Exit 0 when all mutants are handled (expected ValueError / no crash).
Exit 1 on unexpected exceptions or missing radamsa.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path


def _load_target(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    fn = getattr(module, "_test_one", None)
    if not callable(fn):
        raise RuntimeError(f"{path} missing _test_one(data: bytes)")
    return fn


def _generate(radamsa: str, seeds: list[Path], out_dir: Path, count: int, seed: int) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("mut-*"):
        old.unlink()
    pattern = str(out_dir / "mut-%n")
    cmd = [
        radamsa,
        "-n",
        str(count),
        "-s",
        str(seed),
        "-o",
        pattern,
        *[str(p) for p in seeds],
    ]
    subprocess.run(cmd, check=True)
    return sorted(out_dir.glob("mut-*"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--targets-dir", type=Path, required=True)
    parser.add_argument("--count", type=int, default=int(os.environ.get("RADAMSA_COUNT", "200")))
    parser.add_argument("--seed", type=int, default=int(os.environ.get("RADAMSA_SEED", "42")))
    parser.add_argument("--radamsa", default=os.environ.get("RADAMSA", "radamsa"))
    args = parser.parse_args()

    radamsa = shutil.which(args.radamsa) or args.radamsa
    if not shutil.which(args.radamsa) and not Path(radamsa).is_file():
        print(f"ERROR: radamsa not found ({args.radamsa})", file=sys.stderr)
        return 1

    seeds = sorted(
        p
        for p in args.corpus_dir.iterdir()
        if p.is_file() and not p.name.startswith(".")
    )
    if not seeds:
        print(f"ERROR: no seeds in {args.corpus_dir}", file=sys.stderr)
        return 1

    targets = sorted(args.targets_dir.glob("fuzz_*.py"))
    if not targets:
        print(f"ERROR: no fuzz_*.py under {args.targets_dir}", file=sys.stderr)
        return 1

    gen_dir = args.report_dir / "radamsa-gen"
    mutants = _generate(radamsa, seeds, gen_dir, args.count, args.seed)
    print(f"radamsa generated {len(mutants)} mutants from {len(seeds)} seeds")

    crashes = 0
    tested = 0
    for target_path in targets:
        harness = _load_target(target_path)
        for mutant in mutants:
            data = mutant.read_bytes()
            tested += 1
            try:
                harness(data)
            except Exception:  # noqa: BLE001 — intentional crash capture
                crashes += 1
                crash_path = (
                    args.report_dir
                    / f"crash-radamsa-{target_path.stem}-{mutant.name}"
                )
                crash_path.write_bytes(data)
                meta = crash_path.with_suffix(".txt")
                meta.write_text(traceback.format_exc(), encoding="utf-8")
                print(f"CRASH → {crash_path}", file=sys.stderr)

    summary = {
        "engine": "radamsa",
        "seeds": len(seeds),
        "mutants": len(mutants),
        "targets": [p.name for p in targets],
        "tested": tested,
        "crashes": crashes,
        "seed": args.seed,
        "count": args.count,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    out = args.report_dir / "radamsa-summary.json"
    args.report_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out} (crashes={crashes})")
    return 1 if crashes else 0


if __name__ == "__main__":
    raise SystemExit(main())
