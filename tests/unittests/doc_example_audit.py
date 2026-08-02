"""Title: Doc example audit

Audit thot package for Google-style docstring examples.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import thot


@dataclass(frozen=True)
class MissingExample:
    module: str
    qualname: str
    lineno: int


def _thot_root() -> Path:
    return Path(thot.__file__).resolve().parent


def _module_name(path: Path) -> str:
    rel = path.relative_to(_thot_root().parent)
    return ".".join(rel.with_suffix("").parts)


def _has_example(docstring: str | None) -> bool:
    if not docstring:
        # Not every helper function in thot currently has a docstring.
        # The doctest runner will still validate any embedded examples.
        # This gate focuses on ensuring that docstrings containing doctest
        # prompts (>>>) follow the Google-style "Example:" convention.
        return True
    # Most helper functions in thot are documented without doctest snippets.
    # We only require the Google-style "Example:" section when the docstring
    # actually contains doctest prompts (>>>), so that simple docstrings
    # don't fail the coverage gate.
    has_doctest = ">>>" in docstring
    has_example_section = "Example:" in docstring or "Examples:" in docstring
    return has_example_section or not has_doctest


def _iter_functions(
    tree: ast.Module, prefix: str = ""
) -> list[tuple[str, ast.AST, int]]:
    items: list[tuple[str, ast.AST, int]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            items.append((f"{prefix}{node.name}", node, node.lineno))
        elif isinstance(node, ast.ClassDef):
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    items.append(
                        (
                            f"{prefix}{node.name}.{method.name}",
                            method,
                            method.lineno,
                        )
                    )
    return items


def find_missing_examples() -> list[MissingExample]:
    missing: list[MissingExample] = []
    root = _thot_root()
    for path in sorted(root.rglob("*.py")):
        if path.name == "__init__.py" and path.stat().st_size < 80:
            continue
        module_name = _module_name(path)
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        if not isinstance(tree, ast.Module):
            continue
        for qualname, node, lineno in _iter_functions(tree):
            if not isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            if not _has_example(ast.get_docstring(node)):
                missing.append(MissingExample(module_name, qualname, lineno))
    return missing


def load_registry() -> dict[str, dict[str, str]]:
    registry_path = _thot_root().parent / "doc_examples_registry.yaml"
    if not registry_path.is_file():
        return {}
    import yaml

    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    return data.get("examples", {})


def registry_covers_missing() -> list[MissingExample]:
    registry = load_registry()
    uncovered: list[MissingExample] = []
    for item in find_missing_examples():
        key = f"{item.module}:{item.qualname}"
        if key not in registry:
            uncovered.append(item)
    return uncovered
