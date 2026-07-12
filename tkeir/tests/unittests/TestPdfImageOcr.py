# -*- coding: utf-8 -*-
"""Tests for PDF image OCR enrichment."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from thot.tasks.converters.MarkItDownConverter import MarkItDownConverter
from thot.tasks.converters.PdfImageOcr import (
    _bbox_is_large_enough,
    _ocr_image_region,
    _run_ocr,
    _text_from_block,
    build_pdf_content_with_ocr,
    extract_pdf_image_text,
)


class TestPdfImageOcr:
    def test_disabled_returns_empty(self, pdf_bytes):
        assert extract_pdf_image_text(pdf_bytes, {"enabled": False}) == []
        content, stats = build_pdf_content_with_ocr(
            pdf_bytes, {"enabled": False}
        )
        assert content == ""
        assert stats["enabled"] is False
        content, _stats = build_pdf_content_with_ocr(pdf_bytes, None)
        assert content == ""

    @patch("thot.tasks.converters.PdfImageOcr._run_ocr")
    def test_page_image_ocr_comes_before_page_text(
        self, mock_run_ocr, pdf_bytes
    ):
        mock_run_ocr.return_value = "Diagram labels"
        content, _stats = build_pdf_content_with_ocr(
            pdf_bytes,
            {"enabled": True, "mode": "tesseract", "min-image-pixels": 10000},
        )
        image_pos = content.find("[Image page 1]")
        title_pos = content.find("T-SHAPED SKILLS")
        assert image_pos != -1
        assert title_pos != -1
        assert image_pos < title_pos
        assert "Diagram labels" in content

    @patch("thot.tasks.converters.PdfImageOcr._run_ocr")
    def test_extract_snippets_from_image_blocks(self, mock_run_ocr, pdf_bytes):
        mock_run_ocr.return_value = "Diagram labels"
        snippets = extract_pdf_image_text(
            pdf_bytes,
            {"enabled": True, "mode": "tesseract", "min-image-pixels": 10000},
        )
        assert snippets
        assert any("[Image page 1]" in snippet for snippet in snippets)

    @patch(
        "thot.tasks.converters.MarkItDownConverter.build_pdf_content_with_ocr"
    )
    def test_markitdown_uses_page_ordered_pdf_content(self, mock_build):
        mock_build.return_value = (
            "[Image page 1]\nDiagram labels\n\nTitle text",
            {
                "enabled": True,
                "used": True,
                "mode": None,
                "image-regions": 1,
                "scanned-pages": 0,
            },
        )
        document = MarkItDownConverter.convert(
            b"%PDF",
            "file://doc.pdf",
            "pdf",
            ocr_config={"enabled": True},
        )
        assert "Diagram labels" in document["content"][0]
        assert document["content"][0].find("Diagram labels") < document[
            "content"
        ][0].find("Title text")

    @patch("pytesseract.image_to_string", return_value="  hello world  ")
    @patch("PIL.Image.open")
    def test_tesseract_mode_strips_text(self, mock_open, mock_tesseract):
        mock_open.return_value = MagicMock()
        text = _run_ocr(b"image-bytes", {"mode": "tesseract"})
        assert text == "hello world"

    def test_llm_mode_uses_api_key(self):
        mock_client = MagicMock()
        mock_openai_cls = MagicMock(return_value=mock_client)
        mock_openai_mod = MagicMock(OpenAI=mock_openai_cls)
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="  chart text  "))]
        )
        with patch.dict(sys.modules, {"openai": mock_openai_mod}):
            text = _run_ocr(
                b"image-bytes",
                {
                    "mode": "llm",
                    "llm-api-key": "test-key",
                    "llm-model": "gpt-4o",
                    "llm-base-url": "http://localhost/v1",
                },
            )
        assert text == "chart text"
        mock_openai_cls.assert_called_once_with(
            api_key="test-key", base_url="http://localhost/v1"
        )

    def test_llm_mode_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError):
                _run_ocr(b"image-bytes", {"mode": "llm"})

    def test_helpers_cover_block_parsing_and_bbox(self):
        assert not _bbox_is_large_enough((0, 0, 10, 10), {})
        assert _bbox_is_large_enough(
            (0, 0, 200, 200), {"min-image-pixels": 100}
        )
        assert (
            _text_from_block(
                {
                    "lines": [
                        {
                            "spans": [
                                {"text": "Hello"},
                                {"text": " world"},
                            ]
                        }
                    ]
                }
            )
            == "Hello world"
        )

    @patch("thot.tasks.converters.PdfImageOcr._run_ocr", return_value="scan")
    def test_scanned_page_fallback(self, mock_run_ocr):
        mock_page = MagicMock()

        def get_text(arg=None):
            if arg == "dict":
                return {"blocks": []}
            return "ab"

        mock_page.get_text.side_effect = get_text
        mock_page.get_pixmap.return_value = MagicMock(
            tobytes=lambda fmt: b"png-bytes"
        )

        with patch("fitz.open") as mock_open:
            mock_document = MagicMock()
            mock_document.__enter__.return_value = mock_document
            mock_document.__exit__.return_value = False
            mock_document.__iter__.return_value = iter([mock_page])
            mock_open.return_value = mock_document

            content, stats = build_pdf_content_with_ocr(
                b"%PDF", {"enabled": True, "min-page-text-chars": 40}
            )

        assert "[Scanned page 1]" in content
        assert "scan" in content
        assert stats["scanned-pages"] == 1
        mock_run_ocr.assert_called()

    @patch("thot.tasks.converters.PdfImageOcr._run_ocr", return_value="")
    def test_ocr_image_region_handles_errors(self, mock_run_ocr):
        mock_page = MagicMock()
        mock_page.get_pixmap.side_effect = RuntimeError("render failed")
        text = _ocr_image_region(
            mock_page, (0, 0, 200, 200), {"render-dpi": 200}
        )
        assert text == ""
        mock_run_ocr.assert_not_called()

    def test_missing_pymupdf_returns_empty(self, pdf_bytes):
        real_import = __import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "fitz":
                raise ImportError("no pymupdf")
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            content, _stats = build_pdf_content_with_ocr(
                pdf_bytes, {"enabled": True}
            )
            assert content == ""
            assert extract_pdf_image_text(pdf_bytes, {"enabled": True}) == []
