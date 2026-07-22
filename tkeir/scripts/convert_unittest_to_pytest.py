#!/usr/bin/env python3
"""Title: Convert unittest to pytest

Convert unittest-style tests to pytest-style tests.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ACTIVE_TESTS = [
    "tests/unittests/TestConstants.py",
    "tests/unittests/TestDictionaryTrie.py",
    "tests/unittests/TestAnnotationConfiguration.py",
    "tests/unittests/TestCommonConfiguration.py",
    "tests/unittests/TestConverterConfiguration.py",
    "tests/unittests/TestKeywordsConfiguration.py",
    "tests/unittests/TestLoggerConfiguration.py",
    "tests/unittests/TestMorphoSyntacticTaggerConfiguration.py",
    "tests/unittests/TestNERTaggerConfiguration.py",
    "tests/unittests/TestSyntacticTaggerConfiguration.py",
    "tests/unittests/TestTokenizerConfiguration.py",
    "tests/unittests/TestTkeirPaths.py",
    "tests/unittests/TestLanguageDetector.py",
    "tests/unittests/TestSentenceSegmenter.py",
    "tests/unittests/TestSpacyModelLoader.py",
    "tests/unittests/TestResourceSelector.py",
    "tests/unittests/TestPipelineConfiguration.py",
    "tests/unittests/TestPipelineTasks.py",
    "tests/unittests/TestPipelineRunner.py",
    "tests/unittests/TestPipeline.py",
    "tests/unittests/TestSyntacticTagger.py",
    "tests/unittests/TestConverter.py",
    "tests/unittests/TestAnnotationResources.py",
    "tests/unittests/TestMarkItDownConverter.py",
    "tests/unittests/TestPdfImageOcr.py",
    "tests/unittests/TestKeywordsExtractor.py",
    "tests/unittests/TestMorphoSyntacticTagger.py",
    "tests/unittests/TestTokenizerMultilingual.py",
    "tests/unittests/TestRawConverter.py",
    "tests/unittests/TestThotLogger.py",
    "tests/unittests/TestUtils.py",
    "tests/functional_tests/TestPipeline.py",
]


def _find_matching_paren(text: str, open_index: int) -> int:
    depth = 0
    in_string: str | None = None
    escape = False
    for index in range(open_index, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == in_string:
                in_string = None
            continue
        if char in {"'", '"'}:
            in_string = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("Unbalanced parentheses")


def _split_top_level_args(args_text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    in_string: str | None = None
    escape = False
    for char in args_text:
        if in_string:
            current.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == in_string:
                in_string = None
            continue
        if char in {"'", '"'}:
            in_string = char
            current.append(char)
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        parts.append("".join(current).strip())
    return parts


def _line_indent(text: str, position: int) -> str:
    line_start = text.rfind("\n", 0, position) + 1
    indent = []
    for char in text[line_start:position]:
        if char in " \t":
            indent.append(char)
        else:
            break
    return "".join(indent)


def _replace_assert_call(text: str, start: int, method: str) -> tuple[str, bool]:
    open_paren = text.index("(", start)
    close_paren = _find_matching_paren(text, open_paren)
    args = _split_top_level_args(text[open_paren + 1 : close_paren])
    indent = _line_indent(text, start)
    replacement = None
    if method == "assertEqual" and len(args) >= 2:
        msg = ""
        if len(args) >= 3:
            msg = ", " + args[2]
        replacement = f"{indent}assert {args[0]} == {args[1]}{msg}\n"
    elif method == "assertNotEqual" and len(args) >= 2:
        replacement = f"{indent}assert {args[0]} != {args[1]}\n"
    elif method == "assertTrue" and args:
        replacement = f"{indent}assert {args[0]}\n"
    elif method == "assertFalse" and args:
        replacement = f"{indent}assert not {args[0]}\n"
    elif method == "assertIn" and len(args) >= 2:
        msg = ""
        if len(args) >= 3:
            msg = ", " + args[2]
        replacement = f"{indent}assert {args[0]} in {args[1]}{msg}\n"
    elif method == "assertNotIn" and len(args) >= 2:
        replacement = f"{indent}assert {args[0]} not in {args[1]}\n"
    elif method == "assertIsNone" and args:
        replacement = f"{indent}assert {args[0]} is None\n"
    elif method == "assertIsNotNone" and args:
        replacement = f"{indent}assert {args[0]} is not None\n"
    elif method == "assertGreater" and len(args) >= 2:
        replacement = f"{indent}assert {args[0]} > {args[1]}\n"
    elif method == "assertLess" and len(args) >= 2:
        replacement = f"{indent}assert {args[0]} < {args[1]}\n"
    if replacement is None:
        return text, False
    end = close_paren + 1
    while end < len(text) and text[end] in " \t":
        end += 1
    if end < len(text) and text[end] == "\n":
        end += 1
    return text[:start] + replacement + text[end:], True


def convert_asserts(text: str) -> str:
    methods = [
        "assertEqual",
        "assertNotEqual",
        "assertTrue",
        "assertFalse",
        "assertIn",
        "assertNotIn",
        "assertIsNone",
        "assertIsNotNone",
        "assertGreater",
        "assertLess",
    ]
    while True:
        changed = False
        for method in methods:
            match = re.search(rf"self\.{method}\(", text)
            if not match:
                continue
            text, replaced = _replace_assert_call(text, match.start(), method)
            if replaced:
                changed = True
                break
        if not changed:
            break
    return text


def convert_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    original = text

    text = text.replace("import unittest\n", "")
    text = re.sub(r"class (\w+)\(unittest\.TestCase\):", r"class \1:", text)
    text = re.sub(
        r"\nif __name__ == [\"']__main__[\"']:\n    unittest\.main\(\)\n?",
        "\n",
        text,
    )
    text = text.replace("self.assertRaises(", "pytest.raises(")
    text = text.replace("with self.subTest(", "with pytest.raises(AssertionError) and 0 or (  # was subTest ")
    # subTest: just remove the with block wrapper - replace with nothing
    text = re.sub(
        r"\s*with self\.subTest\([^)]*\):\n",
        "",
        text,
    )
    text = convert_asserts(text)

    needs_pytest = (
        "pytest.raises(" in text
        or "setUp" in text
        or "@pytest.fixture" in text
    )
    if needs_pytest and "import pytest" not in text:
        lines = text.splitlines(keepends=True)
        insert_at = 0
        for index, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                insert_at = index + 1
            elif line.strip() and not line.startswith("#"):
                break
        lines.insert(insert_at, "import pytest\n")
        text = "".join(lines)

    return text


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".")
    for relative in ACTIVE_TESTS:
        path = root / relative
        if not path.exists():
            print("skip missing", path)
            continue
        converted = convert_file(path)
        path.write_text(converted, encoding="utf-8")
        print("converted", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
