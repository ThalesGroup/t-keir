#!/usr/bin/env python3
"""Scan git-tracked files for accidentally committed secrets."""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = ROOT / ".secrets-allowlist.yaml"

BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".gz",
    ".zip",
    ".tgz",
    ".whl",
    ".pkl",
    ".bin",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".sqlite",
    ".db",
    ".coverage",
}

FORBIDDEN_TRACKED_NAMES = (
    re.compile(r"(^|/)\.env$"),
    re.compile(r"\.pem$"),
    re.compile(r"(^|/)id_rsa$"),
    re.compile(r"credentials\.json$"),
    re.compile(r"\.p12$"),
    re.compile(r"\.pfx$"),
)

RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "private_key_pem",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    ),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_pat", re.compile(r"\bghp_[A-Za-z0-9_]{20,}\b")),
    ("github_fine_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    (
        "openai_api_key",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}\b"),
    ),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    (
        "jwt_like",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
        ),
    ),
    (
        "assignment_secret",
        re.compile(
            r"(?i)(?:api[_-]?key|secret[_-]?key|client[_-]?secret|"
            r"auth[_-]?secret|password|private[_-]?key)"
            r"\s*[:=]\s*['\"]([^'\"]{12,})['\"]"
        ),
    ),
    (
        "postgres_url",
        re.compile(
            r"postgres(?:ql)?://[^:]+:([^@\s'\"]+)@",
            re.IGNORECASE,
        ),
    ),
]


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    excerpt: str


def _load_allowlist() -> tuple[list[str], set[str]]:
    paths: list[str] = []
    placeholders: set[str] = set()
    if not ALLOWLIST_PATH.is_file():
        return paths, placeholders
    try:
        import yaml
    except ImportError:
        return paths, placeholders

    data = yaml.safe_load(ALLOWLIST_PATH.read_text(encoding="utf-8")) or {}
    paths.extend(str(item) for item in data.get("paths", []) or [])
    placeholders.update(str(item) for item in data.get("placeholders", []) or [])
    return paths, placeholders


def _git_lines(args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _tracked_files(*, staged: bool) -> list[str]:
    if staged:
        return _git_lines(["diff", "--cached", "--name-only", "--diff-filter=ACM"])
    return _git_lines(["ls-files"])


def _is_allowlisted(path: str, allow_paths: list[str]) -> bool:
    for pattern in allow_paths:
        if fnmatch.fnmatch(path, pattern):
            return True
    return False


def _is_binary(path: str) -> bool:
    return Path(path).suffix.lower() in BINARY_SUFFIXES


def _is_placeholder(value: str, placeholders: set[str]) -> bool:
    cleaned = value.strip().strip("'\"")
    if not cleaned:
        return True
    if cleaned in placeholders:
        return True
    lowered = cleaned.lower()
    if any(token in lowered for token in ("change-me", "example", "placeholder", "xxx")):
        return True
    if cleaned.startswith("${") or cleaned.startswith("$("):
        return True
    if cleaned == "secret" or cleaned == "token":
        return True
    return False


def _check_forbidden_tracked(files: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        if path.endswith(".env.example") or path.endswith(".env.local.example"):
            continue
        for pattern in FORBIDDEN_TRACKED_NAMES:
            if pattern.search(path):
                findings.append(
                    Finding(
                        path=path,
                        line=0,
                        rule="forbidden_tracked_file",
                        excerpt="tracked credential file pattern",
                    )
                )
                break
    return findings


def _scan_file(
    path: str,
    *,
    placeholders: set[str],
) -> list[Finding]:
    abs_path = ROOT / path
    if not abs_path.is_file():
        return []
    try:
        text = abs_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if "sk-test" in line or "secrets.token_bytes" in line:
            continue
        for rule_id, pattern in RULES:
            match = pattern.search(line)
            if match is None:
                continue
            if rule_id in {"assignment_secret", "postgres_url"}:
                captured = match.group(1)
                if _is_placeholder(captured, placeholders):
                    continue
            if rule_id == "openai_api_key" and "sk-test" in match.group(0):
                continue
            excerpt = line.strip()
            if len(excerpt) > 120:
                excerpt = excerpt[:117] + "..."
            findings.append(
                Finding(
                    path=path,
                    line=line_no,
                    rule=rule_id,
                    excerpt=excerpt,
                )
            )
    return findings


def scan(*, staged: bool) -> list[Finding]:
    allow_paths, placeholders = _load_allowlist()
    files = _tracked_files(staged=staged)
    findings = _check_forbidden_tracked(files)
    for path in files:
        if _is_allowlisted(path, allow_paths) or _is_binary(path):
            continue
        findings.extend(_scan_file(path, placeholders=placeholders))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Scan only staged files (pre-commit fast path).",
    )
    args = parser.parse_args(argv)

    if not (ROOT / ".git").is_dir():
        print("Not a git repository — skipping secret scan.", file=sys.stderr)
        return 0

    findings = scan(staged=args.staged)
    if not findings:
        scope = "staged files" if args.staged else "tracked files"
        print(f"Secret scan passed ({scope}).")
        return 0

    print("Secret scan failed:", file=sys.stderr)
    for item in findings:
        location = f"{item.path}:{item.line}" if item.line else item.path
        print(f"  [{item.rule}] {location}", file=sys.stderr)
        print(f"    {item.excerpt}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
