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

# Entire ``thot`` tree requires a Google-style docstring with an Example:
# section on every module-level function and class method (nested defs
# excluded — cover those via the enclosing function's Example).
STRICT_EXAMPLE_PREFIXES: tuple[str, ...] = ("thot.",)


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


def _is_strict_module(module_name: str) -> bool:
    return any(module_name.startswith(prefix) for prefix in STRICT_EXAMPLE_PREFIXES)


def _has_example(docstring: str | None, *, strict: bool) -> bool:
    """Return whether ``docstring`` satisfies the Example coverage rule.

    Args:
        docstring: Function/method docstring (may be None).
        strict: When True, require a non-empty docstring containing
            ``Example:`` / ``Examples:``. When False, only flag docstrings
            that embed ``>>>`` without a Google-style Example section.

    Returns:
        True when the coverage gate should pass for this symbol.

    Example:
        >>> from unittests.doc_example_audit import _has_example
        >>> _has_example(None, strict=False)
        True
        >>> _has_example(None, strict=True)
        False
        >>> _has_example("Summary.\\n\\nExample:\\n    >>> 1\\n    1", strict=True)
        True
    """
    if not docstring:
        return not strict
    has_example_section = "Example:" in docstring or "Examples:" in docstring
    if strict:
        return has_example_section
    has_doctest = ">>>" in docstring
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
        strict = _is_strict_module(module_name)
        for qualname, node, lineno in _iter_functions(tree):
            if not isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            if not _has_example(ast.get_docstring(node), strict=strict):
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
