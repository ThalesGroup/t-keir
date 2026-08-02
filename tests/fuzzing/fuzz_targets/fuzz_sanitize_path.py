#!/usr/bin/env python3
"""Atheris target: fuzz ``sanitize_relative_path`` (Linux / libFuzzer only)."""

from __future__ import annotations

import os
import sys


def _test_one(data: bytes) -> None:
    from thot.tools.ingest.user_workspace import sanitize_relative_path

    text = data.decode("utf-8", errors="ignore")
    try:
        out = sanitize_relative_path(text or "x", allow_empty=False)
    except ValueError:
        return
    assert isinstance(out, str)
    assert ".." not in out.split("/")


def main() -> None:
    mode = os.environ.get("FUZZ_MODE", "")
    if mode != "atheris":
        # Smoke one seed so the file is importable on macOS CI.
        _test_one(b"inbox/report.md")
        print("atheris smoke ok (set FUZZ_MODE=atheris on Linux)")
        return

    import atheris  # type: ignore[import-not-found]

    atheris.Setup(sys.argv, _test_one)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
