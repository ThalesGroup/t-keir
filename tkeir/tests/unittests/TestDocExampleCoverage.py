# -*- coding: utf-8 -*-
"""Verify every thot function has a Google-style Example section."""

from __future__ import annotations

from unittests.doc_example_audit import find_missing_examples


def test_all_functions_have_doc_examples():
    missing = find_missing_examples()
    if missing:
        lines = [
            f"  {item.module}:{item.qualname} (line {item.lineno})"
            for item in missing[:40]
        ]
        suffix = ""
        if len(missing) > 40:
            suffix = f"\n  ... and {len(missing) - 40} more"
        raise AssertionError(
            f"{len(missing)} function(s) missing Example: docstring sections:\n"
            + "\n".join(lines)
            + suffix
        )
