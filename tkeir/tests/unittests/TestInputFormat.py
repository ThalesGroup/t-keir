"""Tests for converter input format detection."""

import os
import tempfile

import pytest

from thot.tasks.converters.InputFormat import (
    AUTO_DATATYPE,
    detect_input_format,
    has_extractable_text,
)

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n"


class TestInputFormat:
    def test_detects_pdf_from_extension_and_content(self):
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False
        ) as handle:
            handle.write(PDF_BYTES)
            path = handle.name
        try:
            assert detect_input_format(path, PDF_BYTES, AUTO_DATATYPE) == "pdf"
        finally:
            os.unlink(path)

    def test_detects_pdf_from_content_when_extension_is_text(self):
        with tempfile.NamedTemporaryFile(
            suffix=".txt", delete=False
        ) as handle:
            handle.write(PDF_BYTES)
            path = handle.name
        try:
            assert detect_input_format(path, PDF_BYTES, AUTO_DATATYPE) == "pdf"
        finally:
            os.unlink(path)

    def test_detects_raw_text(self):
        data = b"Plain text document.\n"
        with tempfile.NamedTemporaryFile(
            suffix=".txt", delete=False
        ) as handle:
            handle.write(data)
            path = handle.name
        try:
            assert detect_input_format(path, data, AUTO_DATATYPE) == "raw"
        finally:
            os.unlink(path)

    def test_explicit_pdf_is_verified(self):
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False
        ) as handle:
            handle.write(PDF_BYTES)
            path = handle.name
        try:
            assert detect_input_format(path, PDF_BYTES, "pdf") == "pdf"
        finally:
            os.unlink(path)

    def test_pdf_extension_with_text_content_falls_back_to_raw(self):
        data = b"not a pdf"
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False
        ) as handle:
            handle.write(data)
            path = handle.name
        try:
            assert detect_input_format(path, data, AUTO_DATATYPE) == "raw"
        finally:
            os.unlink(path)

    def test_unknown_extension_with_text_falls_back_to_raw(self):
        data = b"Hello from an unknown file type.\n"
        with tempfile.NamedTemporaryFile(
            suffix=".xyz", delete=False
        ) as handle:
            handle.write(data)
            path = handle.name
        try:
            assert detect_input_format(path, data, AUTO_DATATYPE) == "raw"
        finally:
            os.unlink(path)

    def test_explicit_pdf_on_text_content_falls_back_to_raw(self):
        data = b"not a pdf"
        with tempfile.NamedTemporaryFile(
            suffix=".txt", delete=False
        ) as handle:
            handle.write(data)
            path = handle.name
        try:
            assert detect_input_format(path, data, "pdf") == "raw"
        finally:
            os.unlink(path)

    def test_rejects_unknown_binary_without_extension(self):
        data = b"\x00\x01\x02\x03\xff"
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(data)
            path = handle.name
        try:
            with pytest.raises(
                ValueError, match="Unable to detect input format"
            ):
                detect_input_format(path, data, AUTO_DATATYPE)
        finally:
            os.unlink(path)

    def test_has_extractable_text_empty(self):
        assert not has_extractable_text(b"")

    def test_has_extractable_text_rejects_pdf_bytes(self):
        assert not has_extractable_text(PDF_BYTES)

    def test_explicit_raw_on_pdf_uses_structured_converter(self):
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False
        ) as handle:
            handle.write(PDF_BYTES)
            path = handle.name
        try:
            assert detect_input_format(path, PDF_BYTES, "raw") == "pdf"
        finally:
            os.unlink(path)

    def test_detects_rtf_content(self):
        data = b"{\\rtf1\\ansi hello}"
        with tempfile.NamedTemporaryFile(
            suffix=".rtf", delete=False
        ) as handle:
            handle.write(data)
            path = handle.name
        try:
            assert detect_input_format(path, data, AUTO_DATATYPE) == "rtf"
        finally:
            os.unlink(path)

    def test_detects_html_content(self):
        data = b"<!doctype html><html><body>Hi</body></html>"
        with tempfile.NamedTemporaryFile(
            suffix=".html", delete=False
        ) as handle:
            handle.write(data)
            path = handle.name
        try:
            assert detect_input_format(path, data, AUTO_DATATYPE) == "html"
        finally:
            os.unlink(path)

    def test_detects_docx_zip_magic_with_extension(self):
        data = b"PK\x03\x04" + b"\x00" * 32
        with tempfile.NamedTemporaryFile(
            suffix=".docx", delete=False
        ) as handle:
            handle.write(data)
            path = handle.name
        try:
            assert detect_input_format(path, data, AUTO_DATATYPE) == "docx"
        finally:
            os.unlink(path)
