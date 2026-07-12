# -*- coding: utf-8 -*-
"""Run doctest examples embedded in thot package docstrings."""

from __future__ import annotations

import doctest
import importlib
from pathlib import Path

import pytest

import thot

DOCTEST_FLAGS = (
    doctest.NORMALIZE_WHITESPACE
    | doctest.ELLIPSIS
    | doctest.IGNORE_EXCEPTION_DETAIL
)

SKIP_MODULES = {
    "thot.tasks.document_ontology.ShaclShapes",
}


def _discover_modules() -> list[str]:
    root = Path(thot.__file__).resolve().parent
    modules: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path.name == "__init__.py" and path.stat().st_size < 120:
            continue
        source = path.read_text(encoding="utf-8")
        if ">>>" not in source:
            continue
        rel = path.relative_to(root.parent)
        module_name = ".".join(rel.with_suffix("").parts)
        if module_name in SKIP_MODULES:
            continue
        modules.append(module_name)
    return modules


def _run_module_doctests(module_name: str) -> tuple[int, int]:
    import logging

    logging.disable(logging.CRITICAL)
    module = importlib.import_module(module_name)
    result = doctest.testmod(module, optionflags=DOCTEST_FLAGS, verbose=False)
    logging.disable(logging.NOTSET)
    return result


@pytest.mark.parametrize("module_name", _discover_modules())
def test_module_doc_examples(module_name: str):
    failures, tests = _run_module_doctests(module_name)
    assert tests > 0, f"No doctest examples discovered in {module_name}"
    assert failures == 0, f"{failures} doctest failure(s) in {module_name}"
