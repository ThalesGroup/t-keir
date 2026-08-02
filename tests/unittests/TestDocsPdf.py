"""Tests for scripts/docs_pdf.py (MkDocs → PDF helpers)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = REPO_ROOT / "scripts" / "docs_pdf.py"


def _load_docs_pdf():
    spec = importlib.util.spec_from_file_location("docs_pdf", MOD_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def docs_pdf():
    return _load_docs_pdf()


def test_expand_snippets_resolves_docs_and_tkeir_bases(
    docs_pdf, tmp_path: Path
):
    repo = tmp_path / "repo"
    docs = repo / "docs"
    tkeir = repo / "tkeir"
    (docs / "compliance" / "generated").mkdir(parents=True)
    (tkeir / "configs").mkdir(parents=True)
    (docs / "compliance" / "generated" / "dora_articles.md").write_text(
        "| Art.5 | gate |\n", encoding="utf-8"
    )
    (tkeir / "configs" / "converter.yaml").write_text(
        "logger: {}\n", encoding="utf-8"
    )

    bases = docs_pdf._snippet_bases(repo, docs)
    text = (
        "## Full OPA article catalogue\n\n"
        '--8<-- "./docs/compliance/generated/dora_articles.md"\n\n'
        "```yaml\n"
        '--8<-- "./configs/converter.yaml"\n'
        "```\n"
    )
    out = docs_pdf.expand_snippets(text, bases)
    assert "| Art.5 | gate |" in out
    assert "logger: {}" in out
    assert "--8<--" not in out


def test_expand_snippets_missing_marker(docs_pdf, tmp_path: Path):
    bases = docs_pdf._snippet_bases(tmp_path, tmp_path)
    out = docs_pdf.expand_snippets('--8<-- "./missing.md"\n', bases)
    assert "snippet not found" in out


def test_replace_mermaid_fallback_when_skip(docs_pdf, tmp_path: Path):
    text = "```mermaid\nflowchart TD\n  A-->B\n```\n"
    out, n = docs_pdf.replace_mermaid(text, tmp_path, skip=True, mmdc_cmd=None)
    assert n == 1
    assert "flowchart TD" in out
    assert "rendering skipped" in out


def test_prepare_snippet_strips_html_comments(docs_pdf):
    body = docs_pdf._prepare_snippet_body(
        "<!-- Generated -->\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
    )
    assert "<!--" not in body
    assert "| A | B |\n|---|---|\n| 1 | 2 |" in body


def test_prepare_snippet_keeps_table_rows_contiguous(docs_pdf):
    raw = "<!-- x -->\n| A | B |\n|---|---|\n| 1 | 2 |\n"
    body = docs_pdf._prepare_snippet_body(raw)
    # Blank lines between rows would break python-markdown tables.
    assert "|\n\n|" not in body
    docs_dir = REPO_ROOT / "docs"
    dora = docs_dir / "compliance" / "dora.md"
    if not dora.is_file():
        pytest.skip("docs/compliance/dora.md missing")
    bases = docs_pdf._snippet_bases(REPO_ROOT, docs_dir)
    out = docs_pdf.expand_snippets(dora.read_text(encoding="utf-8"), bases)
    assert "--8<--" not in out
    assert "Art.5(1)" in out or "`Art.5(1)`" in out
    assert "Full OPA article catalogue" in out
