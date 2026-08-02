#!/usr/bin/env python3
"""Emit an in-toto SLSA v0.2 BuildProvenance statement for T-KEIR artefacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_statement(
    *,
    version: str,
    commit: str,
    branch: str,
    build_date: str,
    wheel: Path,
    python: str,
    uv_version: str,
) -> dict:
    subject_name = wheel.name
    subject_digest = _sha256_file(wheel)
    return {
        "_type": "https://in-toto.io/Statement/v0.1",
        "predicateType": "https://slsa.dev/provenance/v0.2",
        "subject": [
            {
                "name": subject_name,
                "digest": {"sha256": subject_digest},
            }
        ],
        "predicate": {
            "builder": {
                "id": "https://github.com/thalesgroup/t-keir/Makefile"
            },
            "buildType": (
                "https://github.com/thalesgroup/t-keir/build-types/make@v1"
            ),
            "invocation": {
                "configSource": {
                    "uri": "git+https://github.com/thalesgroup/t-keir",
                    "digest": {"sha1": commit},
                    "entryPoint": "Makefile:build",
                },
                "parameters": {
                    "VERSION": version,
                    "GIT_BRANCH": branch,
                },
                "environment": {
                    "PYTHON": python,
                    "UV": uv_version,
                },
            },
            "metadata": {
                "buildStartedOn": build_date,
                "completeness": {
                    "parameters": True,
                    "environment": False,
                    "materials": False,
                },
            },
            "materials": [],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--build-date", required=True)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--python", default="3.11")
    parser.add_argument("--uv-version", default="unknown")
    args = parser.parse_args(argv)

    if not args.wheel.is_file():
        print(f"ERROR: wheel not found: {args.wheel}", file=sys.stderr)
        return 1

    statement = build_statement(
        version=args.version,
        commit=args.commit,
        branch=args.branch,
        build_date=args.build_date,
        wheel=args.wheel,
        python=args.python,
        uv_version=args.uv_version,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(statement, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote SLSA provenance → {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
