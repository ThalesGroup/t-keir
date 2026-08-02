#!/usr/bin/env python3
"""Fuzz target: ``sha256_hex`` must stay stable and hex-shaped."""

from __future__ import annotations

import os
import re
import sys


def _test_one(data: bytes) -> None:
    from thot.action.models import sha256_hex

    digest = sha256_hex(data)
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert sha256_hex(data) == digest


def main() -> None:
    mode = os.environ.get("FUZZ_MODE", "")
    if mode != "atheris":
        _test_one(b"radamsa-seed")
        print("atheris smoke ok (set FUZZ_MODE=atheris on Linux)")
        return

    import atheris  # type: ignore[import-not-found]

    atheris.Setup(sys.argv, _test_one)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
