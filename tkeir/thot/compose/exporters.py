"""Render and export composed documents (markdown always; docx/pdf hooks)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from thot.compose.template_models import ComposeResult


def export_markdown(result: ComposeResult, path: Path) -> Path:
    """Write markdown to ``path``.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.compose.exporters import export_markdown
        >>> from thot.compose.template_models import ComposeResult
        >>> with tempfile.TemporaryDirectory() as td:
        ...     out = Path(td) / "note.md"
        ...     r = ComposeResult(
        ...         template="synthesis_note",
        ...         user_space="dev@tkeir",
        ...         markdown="# Hi\\n",
        ...     )
        ...     export_markdown(r, out).read_text(encoding="utf-8").startswith("# Hi")
        True
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.markdown or "", encoding="utf-8")
    return path


def export_structured_json(result: ComposeResult, path: Path) -> Path:
    """Write structured JSON (slots + citations + unfilled) to ``path``.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.compose.exporters import export_structured_json
        >>> from thot.compose.template_models import ComposeResult
        >>> with tempfile.TemporaryDirectory() as td:
        ...     out = Path(td) / "note.json"
        ...     r = ComposeResult(
        ...         template="synthesis_note",
        ...         user_space="dev@tkeir",
        ...         structured_json={"a": 1},
        ...         citations_map={"a": ["c1"]},
        ...     )
        ...     data = json.loads(export_structured_json(r, out).read_text())
        ...     data["citations_map"]["a"]
        ['c1']
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = result.model_dump(by_alias=True, mode="json")
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def export_docx_stub(result: ComposeResult, path: Path) -> Path:
    """Placeholder for future docx export — writes a notice file.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.compose.exporters import export_docx_stub
        >>> from thot.compose.template_models import ComposeResult
        >>> with tempfile.TemporaryDirectory() as td:
        ...     out = Path(td) / "note.docx.txt"
        ...     export_docx_stub(
        ...         ComposeResult(template="t", user_space="u"), out
        ...     ).is_file()
        True
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "DOCX export not implemented yet. Use markdown export.\n"
        f"template={result.template} user_space={result.user_space}\n",
        encoding="utf-8",
    )
    return path


def export_pdf_stub(result: ComposeResult, path: Path) -> Path:
    """Placeholder for future PDF export — writes a notice file.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.compose.exporters import export_pdf_stub
        >>> from thot.compose.template_models import ComposeResult
        >>> with tempfile.TemporaryDirectory() as td:
        ...     out = Path(td) / "note.pdf.txt"
        ...     export_pdf_stub(
        ...         ComposeResult(template="t", user_space="u"), out
        ...     ).is_file()
        True
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "PDF export not implemented yet. Use markdown export.\n"
        f"template={result.template} user_space={result.user_space}\n",
        encoding="utf-8",
    )
    return path
