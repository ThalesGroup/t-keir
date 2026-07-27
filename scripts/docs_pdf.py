#!/usr/bin/env python3
"""Title: Build T-KEIR MkDocs documentation as a single PDF.

Reads ``mkdocs.yml`` navigation order, expands pymdownx-style
``--8<--`` snippets, renders Mermaid fences to PNG (via ``mmdc`` /
``npx @mermaid-js/mermaid-cli`` when available), converts Markdown pages
to HTML, then writes a PDF with PyMuPDF.

Usage (from repo root)::

    python scripts/docs_pdf.py
    # or
    make docs-pdf

Environment:
    DOCS_PDF_OUTPUT       Output path (default: output/docs/tkeir-docs.pdf)
    DOCS_DIR              MkDocs docs_dir (default: docs)
    MKDOCS_YML            MkDocs config (default: mkdocs.yml)
    DOCS_PDF_SKIP_MERMAID If set to 1/true, keep Mermaid source as a code block

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required (project dependency).", file=sys.stderr)
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MKDOCS = REPO_ROOT / "mkdocs.yml"
DEFAULT_DOCS = REPO_ROOT / "docs"
DEFAULT_OUTPUT = REPO_ROOT / "output" / "docs" / "tkeir-docs.pdf"

# pymdownx.snippets markers used across docs (compliance catalogues, tool configs).
_SNIPPET_RE = re.compile(
    r"""^[ \t]*--8<--[ \t]+(?:"([^"]+)"|'([^']+)'|(\S+))[ \t]*$""",
    re.MULTILINE,
)
_MERMAID_RE = re.compile(r"```mermaid[ \t]*\n(.*?)```", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _prepare_snippet_body(body: str) -> str:
    """Normalize included Markdown for PDF-friendly HTML.

    Generated compliance tables start with an HTML comment. When that comment
    sits between a heading and a Markdown table, python-markdown + PyMuPDF
    Story can enter an infinite pagination loop. Strip comments only — do not
    insert blank lines inside GFM tables (rows must stay contiguous).
    """
    body = _HTML_COMMENT_RE.sub("", body)
    body = body.lstrip("\n")
    if body and not body.startswith("\n"):
        # Separate include from the preceding heading/paragraph.
        body = "\n" + body
    return body

CSS = """
body { font-family: Helvetica, Arial, sans-serif; font-size: 11pt; line-height: 1.45; color: #1a1a1a; }
h1 { font-size: 22pt; border-bottom: 1px solid #ccc; padding-bottom: 0.3em; }
h1.cover { border: none; font-size: 28pt; margin-top: 2em; }
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
img { max-width: 100%; height: auto; display: block; margin: 0.8em 0; }
.diagram-caption { color: #555; font-size: 9pt; margin-top: -0.4em; margin-bottom: 1em; }
.cover-meta { color: #555; margin-top: 1em; }
.toc { margin: 1.5em 0; }
.toc li { margin: 0.25em 0; }
.page-label { color: #666; font-size: 9pt; margin-bottom: 0.5em; }
.snippet-missing { color: #a40; font-style: italic; }
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


def _snippet_bases(repo_root: Path, docs_dir: Path) -> list[Path]:
    """Search roots matching pymdownx.snippets as used by this repo.

    Snippet paths are written relative to the repository root
    (``./docs/...``) or the ``tkeir/`` package root (``./configs/...``,
    ``./resources/...``).
    """
    bases = [repo_root, repo_root / "tkeir", docs_dir]
    # Deduplicate while preserving order.
    seen: set[Path] = set()
    out: list[Path] = []
    for base in bases:
        resolved = base.resolve()
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def _resolve_snippet_path(ref: str, bases: list[Path]) -> Path | None:
    ref = ref.strip()
    # Section / line-range suffixes are not used in this repo; strip if present.
    path_part = ref.split(":", 1)[0].strip()
    candidates: list[Path] = []
    stripped = path_part[2:] if path_part.startswith("./") else path_part
    for base in bases:
        candidates.append(base / path_part)
        candidates.append(base / stripped)
        if stripped.startswith("docs/"):
            # When base is docs_dir itself: docs/foo → foo
            candidates.append(base / stripped[len("docs/") :])
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def expand_snippets(
    text: str,
    bases: list[Path],
    *,
    max_depth: int = 8,
    _depth: int = 0,
    _stack: frozenset[Path] | None = None,
) -> str:
    """Expand pymdownx ``--8<-- "path"`` markers (including inside fences)."""
    if _depth > max_depth:
        return text
    stack = _stack or frozenset()

    def repl(match: re.Match[str]) -> str:
        ref = match.group(1) or match.group(2) or match.group(3) or ""
        path = _resolve_snippet_path(ref, bases)
        if path is None:
            return (
                f'\n\n<p class="snippet-missing">'
                f"(snippet not found: {html.escape(ref)})"
                f"</p>\n\n"
            )
        if path in stack:
            return (
                f'\n\n<p class="snippet-missing">'
                f"(snippet cycle: {html.escape(str(path))})"
                f"</p>\n\n"
            )
        body = path.read_text(encoding="utf-8")
        body = _prepare_snippet_body(body)
        return expand_snippets(
            body,
            bases,
            max_depth=max_depth,
            _depth=_depth + 1,
            _stack=stack | {path},
        )

    return _SNIPPET_RE.sub(repl, text)


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _find_mmdc() -> list[str] | None:
    """Return argv prefix to run mermaid-cli, or None if unavailable."""
    which = shutil.which("mmdc")
    if which:
        return [which]
    which_npx = shutil.which("npx")
    if which_npx:
        return [which_npx, "--yes", "@mermaid-js/mermaid-cli@11"]
    return None


def render_mermaid_png(source: str, output: Path, *, mmdc_cmd: list[str] | None) -> bool:
    """Render a Mermaid diagram to PNG. Returns True on success."""
    if not mmdc_cmd:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    mmd_path = output.with_suffix(".mmd")
    mmd_path.write_text(source.rstrip() + "\n", encoding="utf-8")
    cmd = [*mmdc_cmd, "-i", str(mmd_path), "-o", str(output), "-b", "white"]
    env = os.environ.copy()
    # Keep npx cache inside the workspace (avoids broken shared sandbox caches).
    npm_cache = output.parent / ".npm-cache"
    npm_cache.mkdir(parents=True, exist_ok=True)
    env["NPM_CONFIG_CACHE"] = str(npm_cache)
    env.pop("npm_config_devdir", None)
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            timeout=180,
            text=True,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Warning: mermaid render failed ({output.name}): {exc}", file=sys.stderr)
        return False
    if proc.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        err = (proc.stderr or proc.stdout or "").strip()
        if err:
            print(
                f"Warning: mermaid render failed ({output.name}): {err[:400]}",
                file=sys.stderr,
            )
        return False
    return True


def replace_mermaid(
    text: str,
    assets_dir: Path,
    *,
    skip: bool = False,
    mmdc_cmd: list[str] | None = None,
    counter_start: int = 0,
) -> tuple[str, int]:
    """Replace ```mermaid fences with <img> tags (or fenced source fallback)."""
    counter = counter_start

    def repl(match: re.Match[str]) -> str:
        nonlocal counter
        source = match.group(1).strip()
        idx = counter
        counter += 1
        if skip:
            return (
                "\n\n**Mermaid diagram** (rendering skipped):\n\n"
                f"```\n{source}\n```\n\n"
            )
        name = f"mermaid-{idx:03d}.png"
        out = assets_dir / name
        if render_mermaid_png(source, out, mmdc_cmd=mmdc_cmd):
            return (
                f'\n\n<img src="{html.escape(name)}" width="500" '
                f'alt="Mermaid diagram {idx}"/>\n'
                f'<p class="diagram-caption">Figure: Mermaid diagram</p>\n\n'
            )
        return (
            "\n\n**Mermaid diagram** (not rendered — install "
            "`@mermaid-js/mermaid-cli` or ensure `npx`/`mmdc` is on PATH):\n\n"
            f"```\n{source}\n```\n\n"
        )

    return _MERMAID_RE.sub(repl, text), counter


def _rewrite_md_links(text: str) -> str:
    """Turn intra-doc Markdown links into plain labels (PDF has no site nav)."""

    def repl(match: re.Match[str]) -> str:
        label, target = match.group(1), match.group(2)
        if target.startswith(("http://", "https://", "mailto:")):
            return match.group(0)
        return label

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", repl, text)


def _md_to_html(text: str) -> str:
    try:
        import markdown as md_lib
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Install markdown: uv run --with markdown …"
        ) from exc
    text = _rewrite_md_links(text)
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


def build_chapters(
    docs_dir: Path,
    mkdocs_yml: Path,
    *,
    assets_dir: Path | None = None,
    repo_root: Path | None = None,
    skip_mermaid: bool | None = None,
) -> tuple[dict[str, Any], list[tuple[str, str, str]], Path]:
    """Expand snippets / Mermaid and return (meta, chapters, assets_dir).

    Each chapter is ``(title, rel_path, html_body)``.
    """
    cfg = _load_mkdocs_yml(mkdocs_yml)
    site_name = cfg.get("site_name", "T-KEIR")
    site_description = cfg.get("site_description", "")
    nav = cfg.get("nav") or []
    pages = _walk_nav(nav)
    root = (repo_root or mkdocs_yml.resolve().parent).resolve()
    docs_dir = docs_dir.resolve()
    bases = _snippet_bases(root, docs_dir)
    if assets_dir is None:
        assets_dir = Path(tempfile.mkdtemp(prefix="tkeir-docs-pdf-"))
    else:
        assets_dir.mkdir(parents=True, exist_ok=True)

    if skip_mermaid is None:
        skip_mermaid = _truthy_env("DOCS_PDF_SKIP_MERMAID")
    mmdc_cmd = None if skip_mermaid else _find_mmdc()
    if not skip_mermaid and mmdc_cmd is None:
        print(
            "Warning: mmdc/npx not found — Mermaid diagrams will appear as source.",
            file=sys.stderr,
        )

    missing: list[str] = []
    mermaid_i = 0
    chapters: list[tuple[str, str, str]] = []
    for title, rel in pages:
        path = docs_dir / rel
        if not path.is_file():
            missing.append(rel)
            continue
        raw = path.read_text(encoding="utf-8")
        raw = expand_snippets(raw, bases)
        raw, mermaid_i = replace_mermaid(
            raw,
            assets_dir,
            skip=bool(skip_mermaid),
            mmdc_cmd=mmdc_cmd,
            counter_start=mermaid_i,
        )
        body = _md_to_html(raw)
        chapters.append((title, rel, body))

    if missing:
        print(f"Warning: {len(missing)} nav page(s) missing:", file=sys.stderr)
        for rel in missing:
            print(f"  - {rel}", file=sys.stderr)
    if mermaid_i and not skip_mermaid:
        print(f"Rendered Mermaid diagrams: {mermaid_i}", file=sys.stderr)

    meta = {
        "site_name": site_name,
        "site_description": site_description,
        "toc_titles": [t for t, _, _ in chapters],
    }
    return meta, chapters, assets_dir


def _split_html_body(body: str, *, max_chars: int = 20000) -> list[str]:
    """Split a large HTML body on ``<h2>`` so Story never sees huge multi-table docs.

    PyMuPDF Story can infinite-paginate certain combinations of multiple HTML
    tables in one document (observed on the EU AI Act page). Chunking on
    section headings avoids that while keeping catalogues intact.
    """
    if len(body) <= max_chars:
        return [body]
    parts = re.split(r"(?=<h2\b)", body)
    parts = [p for p in parts if p and p.strip()]
    if len(parts) <= 1:
        return [body]
    chunks: list[str] = []
    buf = ""
    for part in parts:
        if buf and len(buf) + len(part) > max_chars:
            chunks.append(buf)
            buf = part
        else:
            buf += part
    if buf:
        chunks.append(buf)
    return chunks or [body]


def _wrap_html(title: str, body: str, *, cover: bool = False) -> str:
    h1_class = " class='cover'" if cover else ""
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        f"<style>{CSS}</style></head><body>"
        f"<h1{h1_class}>{html.escape(title)}</h1>"
        f"{body}</body></html>"
    )


def build_html(
    docs_dir: Path,
    mkdocs_yml: Path,
    *,
    assets_dir: Path | None = None,
    repo_root: Path | None = None,
    skip_mermaid: bool | None = None,
) -> tuple[str, Path]:
    """Build a single HTML document (debug / --keep-html). Returns (html, assets_dir)."""
    meta, chapters, assets_dir = build_chapters(
        docs_dir,
        mkdocs_yml,
        assets_dir=assets_dir,
        repo_root=repo_root,
        skip_mermaid=skip_mermaid,
    )
    parts: list[str] = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>{html.escape(meta['site_name'])} — Documentation</title>",
        f"<style>{CSS}</style></head><body>",
        f"<h1 class='cover'>{html.escape(meta['site_name'])}</h1>",
        f"<p class='cover-meta'>{html.escape(str(meta['site_description']))}</p>",
        "<p class='cover-meta'>Documentation export (PDF)</p>",
        "<h2>Table of contents</h2><ol class='toc'>",
    ]
    for title in meta["toc_titles"]:
        parts.append(f"<li>{html.escape(title)}</li>")
    parts.append("</ol>")
    for title, rel, body in chapters:
        parts.append(f"<h1>{html.escape(title)}</h1>")
        parts.append(f"<p class='page-label'>{html.escape(rel)}</p>")
        parts.append(body)
    parts.append("</body></html>")
    return "\n".join(parts), assets_dir


def _write_story(
    writer: Any,
    html_doc: str,
    *,
    mediabox: Any,
    where: Any,
    assets_dir: Path | None,
    max_pages: int = 200,
) -> None:
    import pymupdf

    archive = str(assets_dir) if assets_dir is not None else None
    story = pymupdf.Story(html=html_doc, archive=archive)
    more = 1
    pages = 0
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
        pages += 1
        if pages >= max_pages:
            print(
                f"Warning: stopped Story after {max_pages} pages "
                "(possible unbreakable HTML); continuing.",
                file=sys.stderr,
            )
            break


def html_to_pdf(html_doc: str, output: Path, *, assets_dir: Path | None = None) -> None:
    """Render one HTML document to PDF (small docs / tests)."""
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyMuPDF (pymupdf) is required.") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (48, 48, -48, -48)
    writer = pymupdf.DocumentWriter(str(output))
    _write_story(
        writer, html_doc, mediabox=mediabox, where=where, assets_dir=assets_dir
    )
    writer.close()


def chapters_to_pdf(
    meta: dict[str, Any],
    chapters: list[tuple[str, str, str]],
    output: Path,
    *,
    assets_dir: Path | None = None,
) -> None:
    """Write PDF one MkDocs page at a time (avoids Story hangs on huge HTML)."""
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyMuPDF (pymupdf) is required.") from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (48, 48, -48, -48)
    writer = pymupdf.DocumentWriter(str(output))

    toc_items = "".join(f"<li>{html.escape(t)}</li>" for t in meta["toc_titles"])
    cover_body = (
        f"<p class='cover-meta'>{html.escape(str(meta['site_description']))}</p>"
        "<p class='cover-meta'>Documentation export (PDF)</p>"
        f"<h2>Table of contents</h2><ol class='toc'>{toc_items}</ol>"
    )
    _write_story(
        writer,
        _wrap_html(str(meta["site_name"]), cover_body, cover=True),
        mediabox=mediabox,
        where=where,
        assets_dir=assets_dir,
    )

    total = len(chapters)
    for i, (title, rel, body) in enumerate(chapters, start=1):
        print(f"  PDF chapter {i}/{total}: {title}", file=sys.stderr, flush=True)
        label = f"<p class='page-label'>{html.escape(rel)}</p>\n"
        chunks = _split_html_body(body)
        for j, chunk in enumerate(chunks):
            prefix = label if j == 0 else ""
            chunk_title = title if j == 0 else f"{title} (continued)"
            _write_story(
                writer,
                _wrap_html(chunk_title, prefix + chunk),
                mediabox=mediabox,
                where=where,
                assets_dir=assets_dir,
            )

    writer.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate T-KEIR docs PDF from MkDocs sources.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(os.environ.get("DOCS_PDF_OUTPUT", str(DEFAULT_OUTPUT))),
        help=f"PDF output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path(os.environ.get("DOCS_DIR", str(DEFAULT_DOCS))),
        help=f"MkDocs docs directory (default: {DEFAULT_DOCS})",
    )
    parser.add_argument(
        "--mkdocs-yml",
        type=Path,
        default=Path(os.environ.get("MKDOCS_YML", str(DEFAULT_MKDOCS))),
        help=f"MkDocs config (default: {DEFAULT_MKDOCS})",
    )
    parser.add_argument(
        "--keep-html",
        type=Path,
        default=None,
        help="Optional path to also write the intermediate HTML",
    )
    parser.add_argument(
        "--skip-mermaid",
        action="store_true",
        default=_truthy_env("DOCS_PDF_SKIP_MERMAID"),
        help="Do not render Mermaid diagrams (keep source as code blocks)",
    )
    args = parser.parse_args(argv)

    if not args.mkdocs_yml.is_file():
        print(f"MkDocs config not found: {args.mkdocs_yml}", file=sys.stderr)
        return 1
    if not args.docs_dir.is_dir():
        print(f"Docs directory not found: {args.docs_dir}", file=sys.stderr)
        return 1

    assets_dir = args.output.parent / "_pdf_assets"
    if assets_dir.exists():
        shutil.rmtree(assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading nav from {args.mkdocs_yml}")
    meta, chapters, assets_dir = build_chapters(
        args.docs_dir,
        args.mkdocs_yml,
        assets_dir=assets_dir,
        repo_root=args.mkdocs_yml.resolve().parent,
        skip_mermaid=args.skip_mermaid,
    )
    if args.keep_html is not None:
        parts: list[str] = [
            "<!DOCTYPE html><html><head><meta charset='utf-8'>",
            f"<title>{html.escape(meta['site_name'])} — Documentation</title>",
            f"<style>{CSS}</style></head><body>",
            f"<h1 class='cover'>{html.escape(meta['site_name'])}</h1>",
            f"<p class='cover-meta'>{html.escape(str(meta['site_description']))}</p>",
            "<p class='cover-meta'>Documentation export (PDF)</p>",
            "<h2>Table of contents</h2><ol class='toc'>",
        ]
        for title in meta["toc_titles"]:
            parts.append(f"<li>{html.escape(title)}</li>")
        parts.append("</ol>")
        for title, rel, body in chapters:
            parts.append(f"<h1>{html.escape(title)}</h1>")
            parts.append(f"<p class='page-label'>{html.escape(rel)}</p>")
            parts.append(body)
        parts.append("</body></html>")
        args.keep_html.parent.mkdir(parents=True, exist_ok=True)
        args.keep_html.write_text("\n".join(parts), encoding="utf-8")
        print(f"Wrote HTML: {args.keep_html}")

    print(f"Rendering PDF → {args.output}")
    chapters_to_pdf(meta, chapters, args.output, assets_dir=assets_dir)
    size_kib = args.output.stat().st_size / 1024
    print(f"Done: {args.output} ({size_kib:.1f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
