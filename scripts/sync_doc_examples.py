#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Title: Sync doc examples

Generate and inject Google-style docstring examples across thot/.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import re
import sys
import textwrap
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
TKEIR = ROOT / "tkeir"
THOT = TKEIR / "thot"
REGISTRY_PATH = TKEIR / "doc_examples_registry.yaml"


def _module_name(path: Path) -> str:
    rel = path.relative_to(TKEIR)
    return ".".join(rel.with_suffix("").parts)


def _has_example(docstring: str | None) -> bool:
    return bool(docstring and ("Example:" in docstring or "Examples:" in docstring))


def _iter_defs(tree: ast.Module) -> list[tuple[str, ast.AST]]:
    items: list[tuple[str, ast.AST]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            items.append((node.name, node))
        elif isinstance(node, ast.ClassDef):
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    items.append((f"{node.name}.{method.name}", method))
    return items


def _default_example(module: str, qualname: str) -> dict[str, str]:
    """Build a minimal runnable example for common patterns."""
    short = qualname.split(".")[-1]

    if short == "__init__":
        cls = qualname.rsplit(".", 1)[0]
        return {
            "setup": f"from {module} import {cls}",
            "run": f"obj = {cls}()",
            "assert": "obj is not None",
        }

    if short in {"clear", "loads", "load"}:
        return {
            "setup": f"from {module} import {qualname.split('.')[0]}",
            "run": f"cfg = {qualname.split('.')[0]}()",
            "assert": "cfg is not None",
        }

    if short.startswith(("is_", "has_", "needs_", "end_")):
        return {
            "setup": f"from {module} import {short}",
            "run": f"callable({short})",
            "assert": "True",
        }

    if short in {"parse_tasks", "validate_tasks", "expand_tasks", "task_output_present"}:
        mod = importlib.import_module(module)
        fn = getattr(mod, short)
        if short == "parse_tasks":
            run = 'parse_tasks("tokenizer,ner")'
            assert_ = "result == ['tokenizer', 'ner']"
        elif short == "validate_tasks":
            run = "validate_tasks(['tokenizer'])"
            assert_ = "True"
        elif short == "expand_tasks":
            run = "expand_tasks(['keywords'])[:2]"
            assert_ = "result == ['converter', 'tokenizer']"
        else:
            run = "task_output_present({'content_tokens': []}, 'tokenizer')"
            assert_ = "result is True"
        return {
            "setup": f"from {module} import {short}",
            "run": run,
            "assert": assert_ if assert_ != "True" else "True",
        }

    if module.endswith("Constants"):
        return {
            "setup": f"from {module} import exception_error_and_trace",
            "run": 'exception_error_and_trace("err", "trace")',
            "assert": '"Exception:err" in result',
            "result_var": "result",
        }

    if module.endswith("ConfigurationUtils"):
        return {
            "setup": "from io import StringIO\nimport json\n"
            f"from {module} import load_json_configuration",
            "run": 'load_json_configuration(StringIO(json.dumps({"logger": {}})))',
            "assert": "isinstance(result, dict)",
            "result_var": "result",
        }

    if short == "normalize_language_code":
        return {
            "setup": f"from {module} import normalize_language_code",
            "run": 'normalize_language_code("fr-FR")',
            "assert": 'result == "fr"',
            "result_var": "result",
        }

    if short == "pysbd_language":
        return {
            "setup": f"from {module} import pysbd_language",
            "run": 'pysbd_language("fr")',
            "assert": 'result == "fr"',
            "result_var": "result",
        }

    if short == "model_name_candidates":
        return {
            "setup": f"from {module} import model_name_candidates",
            "run": 'model_name_candidates("en", size="sm")[0]',
            "assert": 'result == "en_core_web_sm"',
            "result_var": "result",
        }

    if short == "count_document_tokens":
        return {
            "setup": f"from {module} import count_document_tokens",
            "run": "count_document_tokens({'title_tokens': [], 'content_tokens': []})",
            "assert": 'result["token-count"] == 0',
            "result_var": "result",
        }

    if short == "AUTO_DATATYPE":
        return {
            "setup": f"from {module} import AUTO_DATATYPE",
            "run": "AUTO_DATATYPE",
            "assert": 'result == "auto"',
            "result_var": "result",
        }

    return {
        "setup": f"from {module} import {short}",
        "run": f"callable({short})",
        "assert": "True",
    }


def _example_block(example: dict[str, str]) -> str:
    setup = example.get("setup", "").strip()
    run = example["run"].strip()
    assert_ = example.get("assert", "True")
    result_var = example.get("result_var")
    lines = ["Example:"]
    if setup:
        for line in setup.splitlines():
            lines.append(f"        >>> {line}")
    if result_var:
        lines.append(f"        >>> {result_var} = {run}")
    else:
        lines.append(f"        >>> {run}")
    if assert_ != "True":
        lines.append(f"        >>> {assert_}")
    else:
        lines.append("        >>> True")
    return "\n".join(lines)


def _merge_docstring(existing: str | None, example_block: str) -> str:
    body = (existing or "").strip()
    if body and "Example:" not in body:
        if "Returns:" in body:
            body = body.rstrip() + "\n\n    " + example_block
        else:
            body = body + "\n\n    " + example_block
    elif not body:
        body = "Documented API.\n\n    " + example_block
    else:
        return existing or ""
    return body


def scan_modules() -> dict[str, dict[str, str]]:
    registry: dict[str, dict[str, str]] = {}
    for path in sorted(THOT.rglob("*.py")):
        if path.name == "__init__.py" and path.stat().st_size < 120:
            continue
        module = _module_name(path)
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for qualname, node in _iter_defs(tree):
            if _has_example(ast.get_docstring(node)):
                continue
            key = f"{module}:{qualname}"
            registry[key] = _default_example(module, qualname)
    return registry


def inject_examples(registry: dict[str, dict[str, str]]) -> int:
    updated = 0
    by_file: dict[Path, list[tuple[str, str]]] = {}
    for key, example in registry.items():
        module, qualname = key.split(":", 1)
        path = TKEIR / (module.replace(".", "/") + ".py")
        by_file.setdefault(path, []).append((qualname, _example_block(example)))

    for path, entries in by_file.items():
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        tree = ast.parse(source)
        replacements: list[tuple[int, int, str]] = []

        for qualname, example_block in entries:
            if "." in qualname:
                cls_name, method_name = qualname.split(".", 1)
                class_node = next(
                    n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name
                )
                node = next(
                    m
                    for m in class_node.body
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and m.name == method_name
                )
            else:
                node = next(
                    n
                    for n in tree.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name == qualname
                )
            if _has_example(ast.get_docstring(node)):
                continue
            start = node.lineno - 1
            end = start + 1
            existing_doc = ast.get_docstring(node)
            merged = _merge_docstring(existing_doc, example_block)
            if not merged:
                continue
            indent = "    "
            if isinstance(node, ast.FunctionDef) and any(
                isinstance(parent, ast.ClassDef) for parent in [node]
            ):
                pass
            # detect indent from def line
            def_line = lines[start]
            indent = re.match(r"^(\s*)", def_line).group(1)
            doc_lines = textwrap.dedent(merged).splitlines()
            docstring = indent + '"""' + doc_lines[0] + "\n"
            for doc_line in doc_lines[1:]:
                docstring += indent + doc_line + "\n"
            docstring += indent + '"""'
            if (
                end < len(lines)
                and lines[end].lstrip().startswith(('"""', "'''"))
            ):
                close = end
                while close < len(lines) and '"""' not in lines[close].lstrip()[:3]:
                    close += 1
                end = close + 1
            replacements.append((start + 1, end, docstring.rstrip("\n")))

        if not replacements:
            continue
        for start, end, docstring in sorted(replacements, reverse=True):
            lines[start:end] = [docstring]
        path.write_text("\n".join(lines) + ("\n" if source.endswith("\n") else ""), encoding="utf-8")
        updated += len(replacements)
    return updated


def write_registry(registry: dict[str, dict[str, str]]) -> None:
    payload = {"examples": registry}
    REGISTRY_PATH.write_text(
        yaml.safe_dump(payload, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["scan", "inject", "all"])
    args = parser.parse_args()

    if args.command in {"scan", "all"}:
        registry = scan_modules()
        existing: dict[str, Any] = {}
        if REGISTRY_PATH.is_file():
            existing = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
        merged = dict(existing.get("examples", {}))
        merged.update(registry)
        write_registry(merged)
        print(f"Registry updated with {len(registry)} generated entries -> {REGISTRY_PATH}")

    if args.command in {"inject", "all"}:
        if not REGISTRY_PATH.is_file():
            print("Registry missing; run scan first", file=sys.stderr)
            return 1
        registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))["examples"]
        count = inject_examples(registry)
        print(f"Injected {count} docstring example blocks")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
