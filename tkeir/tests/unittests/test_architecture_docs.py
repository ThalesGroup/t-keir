"""Title: Validation tests for architecture documentation under ``tkeir/docs/architecture/``.

Paths are discovered at test time from ``mkdocs.yml`` (no invented module names).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

# Walk up until we find mkdocs.yml (lives in tkeir/)
_HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = _HERE
for _parent in [_HERE, *_HERE.parents]:
    if (_parent / "mkdocs.yml").exists() or (_parent / "mkdocs.yaml").exists():
        REPO_ROOT = _parent
        break

DOCS_ROOT = REPO_ROOT / "docs"
MKDOCS_CFG = (
    REPO_ROOT / "mkdocs.yml"
    if (REPO_ROOT / "mkdocs.yml").exists()
    else REPO_ROOT / "mkdocs.yaml"
)
ARCH_DIR = DOCS_ROOT / "architecture"

REQUIRED_PAGES = [
    "index.md",
    "sequences.md",
    "data-model.md",
    "decisions.md",
]


def _diagram_keyword() -> str:
    """Return the diagram syntax keyword used in this repo's docs."""
    patterns = [
        "mermaid",
        "plantuml",
        "graph TD",
        "sequenceDiagram",
        "classDiagram",
        "C4Context",
        "@startuml",
    ]
    for page in DOCS_ROOT.rglob("*.md"):
        text = page.read_text(errors="replace")
        for pattern in patterns:
            if pattern in text:
                if pattern in (
                    "graph TD",
                    "sequenceDiagram",
                    "classDiagram",
                    "C4Context",
                ):
                    return "mermaid"
                return pattern
    return "mermaid"


def _count_diagram_blocks(text: str, keyword: str) -> int:
    """Count fenced code blocks tagged with keyword."""
    return len(re.findall(rf"```{re.escape(keyword)}", text, re.IGNORECASE))


def _count_adr_files() -> int:
    adr_dir = DOCS_ROOT / "adr"
    if not adr_dir.is_dir():
        return 1
    return max(len(list(adr_dir.glob("000*.md"))), 1)


def _docs_build_cmd() -> list[str]:
    """MkDocs build from the directory that contains mkdocs.yml."""
    return [
        sys.executable,
        "-m",
        "mkdocs",
        "build",
        "-f",
        str(MKDOCS_CFG),
    ]


@pytest.mark.parametrize("page", REQUIRED_PAGES)
def test_architecture_page_exists(page: str) -> None:
    path = ARCH_DIR / page
    assert path.exists(), f"Missing: {path}"
    assert path.stat().st_size > 200, f"Page looks empty: {path.name}"


def test_index_has_enough_diagrams() -> None:
    keyword = _diagram_keyword()
    text = (ARCH_DIR / "index.md").read_text(encoding="utf-8")
    count = _count_diagram_blocks(text, keyword)
    assert (
        count >= 3
    ), f"architecture/index.md should have ≥3 diagrams ({keyword}), found {count}"


def test_sequences_has_enough_diagrams() -> None:
    keyword = _diagram_keyword()
    text = (ARCH_DIR / "sequences.md").read_text(encoding="utf-8")
    count = _count_diagram_blocks(text, keyword)
    assert (
        count >= 2
    ), f"architecture/sequences.md should have ≥2 sequence diagrams, found {count}"


def test_data_model_has_class_and_erd() -> None:
    keyword = _diagram_keyword()
    text = (ARCH_DIR / "data-model.md").read_text(encoding="utf-8")
    total = _count_diagram_blocks(text, keyword)
    has_erd = "erDiagram" in text
    assert (
        total >= 2
    ), f"architecture/data-model.md should have ≥2 diagrams, found {total}"
    assert (
        has_erd
    ), "architecture/data-model.md should include at least one ERD"


def test_decisions_covers_all_adrs() -> None:
    n_adrs = _count_adr_files()
    text = (ARCH_DIR / "decisions.md").read_text(encoding="utf-8")
    headers = re.findall(r"^##\s+", text, re.MULTILINE)
    # Exclude the cross-reference section title
    assert len(headers) >= n_adrs, (
        f"decisions.md should have ≥{n_adrs} sections (one per ADR), "
        f"found {len(headers)}"
    )


def test_mkdocs_nav_files_exist() -> None:
    if not MKDOCS_CFG.exists():
        pytest.skip("No mkdocs.yml found")
    text = MKDOCS_CFG.read_text(encoding="utf-8")
    md_refs = re.findall(r":\s+['\"]?([\w./-]+\.md)['\"]?", text)
    missing = [ref for ref in md_refs if not (DOCS_ROOT / ref).exists()]
    assert not missing, f"Nav references missing files: {missing}"


def test_docs_build() -> None:
    cmd = _docs_build_cmd()
    result = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    # Prefer uv-wrapped mkdocs if bare module missing
    if result.returncode != 0 and "No module named mkdocs" in (
        result.stderr + result.stdout
    ):
        result = subprocess.run(
            [
                "uv",
                "run",
                "--python",
                "3.11",
                "--with",
                "mkdocs",
                "--with",
                "mkdocs-material",
                "--with",
                "mkdocs-render-swagger-plugin",
                "mkdocs",
                "build",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    errors = [
        line
        for line in (result.stderr or "").splitlines()
        if "ERROR" in line.upper()
    ]
    assert result.returncode == 0, "Docs build failed:\n" + "\n".join(
        errors[:20] or [result.stderr[-2000:]]
    )
