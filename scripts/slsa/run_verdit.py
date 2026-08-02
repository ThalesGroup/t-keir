#!/usr/bin/env python3
"""Assess SLSA level from a local provenance document (verdit-compatible).

``verdit-slsa`` is not published on PyPI at a stable version; this script
implements the same contract the Makefile expects:

1. Prefer ``verdit.assess`` when importable.
2. Otherwise run a local Level-2 assessment (builder id + subject digest).
3. Always attach a ``roadmap`` describing how to reach the next SLSA levels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _roadmap(level: int, checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Build actionable guidance to climb from the achieved level."""
    failed = [c["name"] for c in checks if not c.get("ok")]
    levels = {
        0: {
            "title": "SLSA Level 0 → 1",
            "summary": "Produce build provenance that identifies source + builder.",
            "actions": [
                "Run `make slsa-provenance` so `reports/slsa/provenance.json` exists.",
                "Ensure the wheel digest in the provenance subject matches the built artefact.",
                "Keep `builder.id` pointing at the Makefile (or a CI workflow URI).",
                "Document the build entrypoint (`Makefile:build`).",
            ],
        },
        1: {
            "title": "SLSA Level 1 → 2",
            "summary": "Hosted / scripted build with complete provenance parameters.",
            "actions": [
                "Generate provenance via `make slsa` (prereqs → provenance → assess).",
                "Record `configSource.uri` + commit digest (`git rev-parse HEAD`).",
                "Sign provenance with cosign: `make sign-provenance` (or `make sign-all`).",
                "Gate CI with `make slsa-level-gate SLSA_LEVEL=2`.",
            ],
        },
        2: {
            "title": "SLSA Level 2 → 3",
            "summary": (
                "Hardened, isolated build service that generates non-forgeable "
                "provenance (hermetic + authenticated builder identity)."
            ),
            "actions": [
                "Move release builds off the developer laptop into a trusted builder "
                "(GitHub Actions `slsa-framework/slsa-github-generator`, Tekton Chains, "
                "or Google Cloud Build with SLSA provenance).",
                "Make the build hermetic: pin all inputs (uv.lock digests, base images "
                "by `@sha256`, no network package installs during the release job).",
                "Have the *builder* mint provenance (not a post-hoc Makefile script) "
                "so the builder identity is cryptographically bound.",
                "Publish provenance as an in-toto attestation next to the wheel/images "
                "and verify with `slsa-verifier verify-artifact`.",
                "Attach image attestations: `make sign-attest-images SKIP_IMAGE_ATTEST=0` "
                "after pushing to a registry with OIDC (`cosign sign` / `cosign attest`).",
                "Prefer keyless Sigstore in CI (`id-token: write`) over local keypairs.",
                "Optional aspirational gate: `make slsa-level-gate SLSA_LEVEL=3` once the "
                "hosted builder path is wired (expect fail until then).",
            ],
        },
        3: {
            "title": "SLSA Level 3 → 4",
            "summary": (
                "Two-person review + hermetic, reproducible builds with "
                "strong isolation (highest bar; rarely required)."
            ),
            "actions": [
                "Enforce dual approval on release tags / protected environments.",
                "Prove bit-for-bit reproducibility (`SOURCE_DATE_EPOCH`, locked toolchains).",
                "Run builds in ephemeral, non-persistent builders with no secret exfil paths.",
                "Retain signed build logs and material hashes for every release artefact.",
            ],
        },
    }
    # levels[N] describes how to climb from N → N+1.
    next_level = level + 1 if level < 4 else None
    current = levels.get(level, levels[0])
    upcoming = levels.get(level) if next_level is not None else None
    return {
        "achieved": level,
        "next_level": next_level,
        "current": current,
        "next": upcoming,
        "failed_checks": failed,
        "tkeir_make_targets": [
            "make slsa                 # assess + gate at SLSA_LEVEL (default 2)",
            "make slsa-report          # rewrite report.json + print roadmap",
            "make sign-all             # sign wheel + SBOM + provenance",
            "make verify-signatures    # verify local bundles",
            "make sign-attest-images SKIP_IMAGE_ATTEST=0  # L3-oriented image attest",
            "make slsa-level-gate SLSA_LEVEL=3           # aspirational gate",
        ],
        "references": [
            "https://slsa.dev/spec/v1.0/levels",
            "https://github.com/slsa-framework/slsa-github-generator",
            "https://github.com/slsa-framework/slsa-verifier",
            "https://docs.sigstore.dev/cosign/signing/overview/",
        ],
    }


def _print_roadmap(roadmap: dict[str, Any]) -> None:
    nxt = roadmap.get("next") or {}
    print("")
    print("=== SLSA upgrade path ===")
    print(f"Achieved level: {roadmap.get('achieved')}")
    if roadmap.get("next_level") is None:
        print("Already at the top of the assessed scale (Level 4 aspirational).")
        return
    print(f"Next target:    Level {roadmap['next_level']} — {nxt.get('title', '')}")
    print(nxt.get("summary", ""))
    print("Actions:")
    for idx, action in enumerate(nxt.get("actions") or [], start=1):
        print(f"  {idx}. {action}")
    print("Make targets:")
    for line in roadmap.get("tkeir_make_targets") or []:
        print(f"  · {line}")
    print("Refs:")
    for ref in roadmap.get("references") or []:
        print(f"  · {ref}")


def _local_assess(provenance_path: Path, subject_path: Path) -> dict[str, Any]:
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    add(
        "statement_type",
        provenance.get("_type") == "https://in-toto.io/Statement/v0.1",
    )
    add(
        "predicate_type",
        provenance.get("predicateType")
        == "https://slsa.dev/provenance/v0.2",
    )
    predicate = provenance.get("predicate") or {}
    builder_id = (predicate.get("builder") or {}).get("id", "")
    add("builder_id", bool(builder_id), builder_id)
    add(
        "build_type",
        bool((predicate.get("buildType") or "").startswith("https://")),
    )
    subjects = provenance.get("subject") or []
    add("subject_present", bool(subjects))
    subject_ok = False
    detail = ""
    if subjects and subject_path.is_file():
        expected = (subjects[0].get("digest") or {}).get("sha256", "")
        actual = _sha256_file(subject_path)
        subject_ok = expected == actual
        detail = f"expected={expected[:12]}… actual={actual[:12]}…"
    add("subject_digest_match", subject_ok, detail)
    invocation = predicate.get("invocation") or {}
    config = invocation.get("configSource") or {}
    add("config_source_uri", bool(config.get("uri")))
    add("config_source_digest", bool((config.get("digest") or {}).get("sha1")))
    add("entrypoint", config.get("entryPoint") == "Makefile:build")

    # Extra signals toward L3 (informational — do not raise level yet).
    completeness = (predicate.get("metadata") or {}).get("completeness") or {}
    add(
        "materials_declared",
        bool(predicate.get("materials")),
        "empty materials[] — pin lockfile/image digests for L3",
    )
    add(
        "environment_complete",
        bool(completeness.get("environment")),
        "set metadata.completeness.environment=true in a hermetic builder",
    )
    # A repo Makefile URL is NOT a hosted builder. Require a known
    # non-forgeable builder identity (SLSA generator, Tekton, Cloud Build…).
    builder_is_hosted = any(
        token in builder_id
        for token in (
            "slsa-framework/slsa-github-generator",
            "slsa-github-generator",
            "tekton.dev",
            "tekton-chains",
            "cloudbuild.googleapis.com",
            "https://github.com/slsa-framework/",
        )
    ) and "Makefile" not in builder_id
    add(
        "hosted_builder",
        builder_is_hosted,
        builder_id or "local Makefile builder (L2 max)",
    )

    passed_core = sum(
        1
        for item in checks
        if item["ok"]
        and item["name"]
        not in {
            "materials_declared",
            "environment_complete",
            "hosted_builder",
        }
    )
    # Local Makefile builds with recorded provenance map to SLSA Level 2.
    # L3 requires a hosted non-forgeable builder (hosted_builder check).
    if passed_core >= 7 and subject_ok and builder_is_hosted:
        level = 3
    elif passed_core >= 7 and subject_ok:
        level = 2
    elif passed_core >= 4:
        level = 1
    else:
        level = 0

    roadmap = _roadmap(level, checks)
    return {
        "level": level,
        "checks": checks,
        "passed": passed_core,
        "total": 9,
        "timestamp": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "assessor": "scripts/slsa/run_verdit.py#local",
        "roadmap": roadmap,
    }


def _try_verdit(
    provenance_path: Path, subject_path: Path
) -> dict[str, Any] | None:
    try:
        import verdit  # type: ignore[import-not-found]
    except ImportError:
        return None
    assess = getattr(verdit, "assess", None)
    if assess is None:
        return None
    result = assess(str(provenance_path), str(subject_path))
    if isinstance(result, dict):
        result.setdefault(
            "timestamp",
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        result.setdefault("assessor", "verdit")
        level = int(result.get("level", 0))
        result["roadmap"] = _roadmap(level, list(result.get("checks") or []))
        return result
    level = int(result) if result is not None else 0
    return {
        "level": level,
        "checks": [],
        "timestamp": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "assessor": "verdit",
        "roadmap": _roadmap(level, []),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--subject", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--print-roadmap",
        action="store_true",
        help="Print the upgrade path to stdout (also used by make slsa-report).",
    )
    args = parser.parse_args(argv)

    if not args.provenance.is_file():
        print(f"ERROR: provenance missing: {args.provenance}", file=sys.stderr)
        return 1
    if not args.subject.is_file():
        print(f"ERROR: subject missing: {args.subject}", file=sys.stderr)
        return 1

    report = _try_verdit(args.provenance, args.subject)
    if report is None:
        report = _local_assess(args.provenance, args.subject)
    elif "roadmap" not in report:
        report["roadmap"] = _roadmap(int(report.get("level", 0)), [])

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    # Always write a concise markdown companion for humans / docs.
    md_path = args.report.with_name("roadmap.md")
    roadmap = report.get("roadmap") or {}
    nxt = roadmap.get("next") or {}
    lines = [
        f"# SLSA roadmap (achieved level {roadmap.get('achieved', '?')})",
        "",
        f"**Next target:** Level {roadmap.get('next_level')} — "
        f"{nxt.get('title', 'n/a')}",
        "",
        nxt.get("summary", ""),
        "",
        "## Actions",
        "",
    ]
    for idx, action in enumerate(nxt.get("actions") or [], start=1):
        lines.append(f"{idx}. {action}")
    lines.extend(["", "## Make targets", ""])
    for line in roadmap.get("tkeir_make_targets") or []:
        lines.append(f"- `{line}`")
    lines.extend(["", "## References", ""])
    for ref in roadmap.get("references") or []:
        lines.append(f"- {ref}")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    level = int(report.get("level", 0))
    print(f"SLSA Level achieved: {level}")
    print(f"Wrote report → {args.report}")
    print(f"Wrote roadmap → {md_path}")
    if args.print_roadmap:
        _print_roadmap(roadmap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
