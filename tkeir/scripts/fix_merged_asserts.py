#!/usr/bin/env python3
"""Fix merged assert lines produced during unittest migration."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def fix_text(text: str) -> str:
    text = re.sub(
        r"(assert [^\n]+?),\s*\n\s*assert ",
        r"\1\n        assert ",
        text,
    )
    while True:
        updated = re.sub(
            r"(?<=\S)(        assert )",
            r"\n\1",
            text,
        )
        if updated == text:
            break
        text = updated
    text = re.sub(r"(assert [^\n]+?),\s+(assert )", r"\1\n        \2", text)
    text = re.sub(
        r"with pytest\.raises\(AssertionError\) and 0 or \(  # was subTest [^)]+\):\n",
        "",
        text,
    )
    text = text.replace("import pytest\n# -*- coding:", "# -*- coding:\nimport pytest")
    return text


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else "tests")
    for path in sorted(root.rglob("Test*.py")):
        original = path.read_text(encoding="utf-8")
        fixed = fix_text(original)
        if fixed != original:
            path.write_text(fixed, encoding="utf-8")
            print("fixed", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
