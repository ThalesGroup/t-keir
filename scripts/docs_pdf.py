#!/usr/bin/env python3
"""Title: Build T-KEIR MkDocs documentation as a single PDF.

Reads ``mkdocs.yml`` navigation order, converts Markdown pages to HTML,
then renders a PDF with PyMuPDF (already a project dependency).

Usage (from repo root)::

    python scripts/docs_pdf.py
    # or
    make docs-pdf

Environment:
    DOCS_PDF_OUTPUT  Output path (default: output/docs/tkeir-docs.pdf)
    DOCS_DIR         MkDocs docs_dir (default: docs)
    MKDOCS_YML       MkDocs config (default: mkdocs.yml)

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required (project dependency).", file=sys.stderr)
    sys.exit(1)

try:
    import markdown as md_lib
except ImportError:  # pragma: no cover
    print("Install markdown: uv run --with markdown …", file=sys.stderr)
    sys.exit(1)

try:
    import pymupdf
except ImportError:  # pragma: no cover
    print("PyMuPDF (pymupdf) is required.", file=sys.stderr)
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MKDOCS = REPO_ROOT / "mkdocs.yml"
DEFAULT_DOCS = REPO_ROOT / "docs"
DEFAULT_OUTPUT = REPO_ROOT / "output" / "docs" / "tkeir-docs.pdf"

CSS = """
body { font-family: Helvetica, Arial, sans-serif; font-size: 11pt; line-height: 1.45; color: #1a1a1a; }
h1 { font-size: 22pt; page-break-before: always; border-bottom: 1px solid #ccc; padding-bottom: 0.3em; }
h1.cover { page-break-before: avoid; border: none; font-size: 28pt; margin-top: 2em; }
h2 { font-size: 16pt; margin-top: 1.4em; }
h3 { font-size: 13pt; margin-top: 1.1em; }
h4 { font-size: 12pt; }
code, pre { font-family: Courier, monospace; font-size: 9pt; }
pre { background: #f4f4f4; padding: 0.6em 0.8em; border: 1px solid #ddd; white-space: pre-wrap; word-wrap: break-word; }
code { background: #f4f4f4; padding: 0 0.2em; }
table { border-collapse: collapse; width: 100%; margin: 0.8em 0; font-size: 9.5pt; }
th, td { border: 1px solid #bbb; padding: 0.35em 0.5em; vertical-align: top; }
th { background: #eee; }
blockquote { border-left: 3px solid #888; margin-left: 0; padding-left: 0.8em; color: #444; }
a { color: #1a4d8f; text-decoration: none; }
.cover-meta { color: #555; margin-top: 1em; }
.toc { margin: 1.5em 0; }
.toc li { margin: 0.25em 0; }
.page-label { color: #666; font-size: 9pt; margin-bottom: 0.5em; }
"""


class _MkDocsYamlLoader(yaml.SafeLoader):
    """SafeLoader that tolerates MkDocs ``!!python/name:…`` tags.

    PDF export only needs ``site_*`` and ``nav``; markdown extension callables
    are irrelevant and must not force ``FullLoader``.
    """


def _ignore_python_name(
    loader: yaml.SafeLoader, suffix: str, node: yaml.Node
) -> None:
    return None


_MkDocsYamlLoader.add_multi_constructor(
    "tag:yaml.org,2002:python/name:",
    _ignore_python_name,
)


def _load_mkdocs_yml(mkdocs_yml: Path) -> dict[str, Any]:
    cfg = yaml.load(
        mkdocs_yml.read_text(encoding="utf-8"),
        Loader=_MkDocsYamlLoader,
    )
    if not isinstance(cfg, dict):
        raise ValueError(f"expected mapping in {mkdocs_yml}")
    return cfg


def _walk_nav(nodes: list[Any]) -> list[tuple[str, str]]:
    """Flatten MkDocs nav to (title, relative path) pairs."""
    pages: list[tuple[str, str]] = []
    for node in nodes:
        if isinstance(node, str):
            pages.append((Path(node).stem.replace("_", " ").title(), node))
        elif isinstance(node, dict):
            for title, value in node.items():
                if isinstance(value, str):
                    pages.append((str(title), value))
                elif isinstance(value, list):
                    pages.extend(_walk_nav(value))
    return pages


def _rewrite_md_links(text: str) -> str:
    """Turn intra-doc Markdown links into plain labels (PDF has no site nav)."""

    def repl(match: re.Match[str]) -> str:
        label, target = match.group(1), match.group(2)
        if target.startswith(("http://", "https://", "mailto:")):
            return match.group(0)
        return label

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", repl, text)


def _md_to_html(text: str) -> str:
    text = _rewrite_md_links(text)
    # Drop mermaid fences (not renderable in this PDF path)
    text = re.sub(
        r"```mermaid\n.*?```",
        "\n*(diagram omitted in PDF)*\n",
        text,
        flags=re.DOTALL,
    )
    return md_lib.markdown(
        text,
        extensions=[
            "extra",
            "tables",
            "fenced_code",
            "sane_lists",
            "toc",
        ],
    )


def build_html(docs_dir: Path, mkdocs_yml: Path) -> str:
    cfg = _load_mkdocs_yml(mkdocs_yml)
    site_name = cfg.get("site_name", "T-KEIR")
    site_description = cfg.get("site_description", "")
    nav = cfg.get("nav") or []
    pages = _walk_nav(nav)

    parts: list[str] = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>{html.escape(site_name)} — Documentation</title>",
        f"<style>{CSS}</style></head><body>",
        f"<h1 class='cover'>{html.escape(site_name)}</h1>",
        f"<p class='cover-meta'>{html.escape(str(site_description))}</p>",
        "<p class='cover-meta'>Documentation export (PDF)</p>",
        "<h2>Table of contents</h2><ol class='toc'>",
    ]
    for title, _rel in pages:
        parts.append(f"<li>{html.escape(title)}</li>")
    parts.append("</ol>")

    missing: list[str] = []
    for title, rel in pages:
        path = docs_dir / rel
        if not path.is_file():
            missing.append(rel)
            continue
        body = _md_to_html(path.read_text(encoding="utf-8"))
        parts.append(f"<h1>{html.escape(title)}</h1>")
        parts.append(f"<p class='page-label'>{html.escape(rel)}</p>")
        parts.append(body)

    parts.append("</body></html>")
    if missing:
        print(f"Warning: {len(missing)} nav page(s) missing:", file=sys.stderr)
        for rel in missing:
            print(f"  - {rel}", file=sys.stderr)
    return "\n".join(parts)


def html_to_pdf(html_doc: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (48, 48, -48, -48)
    story = pymupdf.Story(html=html_doc)
    writer = pymupdf.DocumentWriter(str(output))
    more = 1
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate T-KEIR docs PDF from MkDocs sources.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(
            __import__("os").environ.get("DOCS_PDF_OUTPUT", str(DEFAULT_OUTPUT))
        ),
        help=f"PDF output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path(__import__("os").environ.get("DOCS_DIR", str(DEFAULT_DOCS))),
        help=f"MkDocs docs directory (default: {DEFAULT_DOCS})",
    )
    parser.add_argument(
        "--mkdocs-yml",
        type=Path,
        default=Path(__import__("os").environ.get("MKDOCS_YML", str(DEFAULT_MKDOCS))),
        help=f"MkDocs config (default: {DEFAULT_MKDOCS})",
    )
    parser.add_argument(
        "--keep-html",
        type=Path,
        default=None,
        help="Optional path to also write the intermediate HTML",
    )
    args = parser.parse_args(argv)

    if not args.mkdocs_yml.is_file():
        print(f"MkDocs config not found: {args.mkdocs_yml}", file=sys.stderr)
        return 1
    if not args.docs_dir.is_dir():
        print(f"Docs directory not found: {args.docs_dir}", file=sys.stderr)
        return 1

    print(f"Reading nav from {args.mkdocs_yml}")
    html_doc = build_html(args.docs_dir, args.mkdocs_yml)
    if args.keep_html is not None:
        args.keep_html.parent.mkdir(parents=True, exist_ok=True)
        args.keep_html.write_text(html_doc, encoding="utf-8")
        print(f"Wrote HTML: {args.keep_html}")

    print(f"Rendering PDF → {args.output}")
    html_to_pdf(html_doc, args.output)
    size_kib = args.output.stat().st_size / 1024
    print(f"Done: {args.output} ({size_kib:.1f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
