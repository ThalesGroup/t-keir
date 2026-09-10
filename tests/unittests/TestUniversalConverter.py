"""Title: Universal Converter

Tests for classify / extract and pipeline conversion of mixed file types.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import base64
import io
import zipfile

from thot.tasks.converters.Converter import Converter
from thot.tasks.converters.UniversalConverter import (
    UniversalConverter,
    classify_kind,
    extract_markdown,
)


class TestUniversalConverter:
    def test_classify_text_and_image_magic(self):
        assert classify_kind("note.txt", b"Hello") == "raw"
        assert classify_kind("scan.jpg", bytes([0xFF, 0xD8, 0xFF, 0xE0])) == (
            "image"
        )
        assert classify_kind("data.json", b'{"a": 1}') == "json"
        assert classify_kind("blob.bin", b"\x00\x01\xff") == "unknown"

    def test_extract_csv_markdown(self):
        text = extract_markdown(b"Name,Age\nAda,36\n", "t.csv", "csv")
        assert "Name" in text
        assert "Ada" in text

    def test_extract_html(self):
        html = b"<html><head><title>T</title></head><body>Hi</body></html>"
        text = extract_markdown(html, "p.html", "html")
        assert "Hi" in text

    def test_extract_zip_nested_text(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("inner.txt", "nested body")
        markdown = extract_markdown(buf.getvalue(), "pack.zip", "zip")
        assert "nested body" in markdown

    def test_convert_json_and_markdown(self):
        doc = UniversalConverter.convert(b'{"k": "v"}', "a.json", "json")
        assert "k" in doc["content"][0] or "v" in doc["content"][0]
        assert "k" in doc["markdown"]
        md = UniversalConverter.convert(b"# Title\n\nBody.\n", "a.md", "md")
        assert md["title"] == "Title"
        assert "Body." in md["content"][0]
        assert md["markdown"].startswith("# Title")

    def test_pipeline_auto_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("readme.txt", "from archive")
        payload = base64.b64encode(buf.getvalue()).decode()
        document = Converter().convert(
            data_type="auto", data=payload, source="file://pack.zip"
        )
        joined = "\n".join(document["content"])
        assert "from archive" in joined
        assert document["conversion-info"]["datatype"] == "zip"

    def test_extract_image_markdown(self):
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (256, 256), (12, 80, 200)).save(buf, format="PNG")
        markdown = extract_markdown(
            buf.getvalue(),
            "chart.png",
            "image",
            ocr_config={"enabled": False, "analyze-images": True},
        )
        assert markdown.startswith("# chart.png")
        assert "## Image analysis" in markdown
        assert "256x256" in markdown
        assert "scene" in markdown.lower()

    def test_pipeline_auto_image(self):
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (256, 256), "navy").save(buf, format="PNG")
        payload = base64.b64encode(buf.getvalue()).decode()
        document = Converter().convert(
            data_type="auto", data=payload, source="file://photo.png"
        )
        joined = "\n".join(document["content"])
        assert "Image analysis" in joined
        assert document["conversion-info"]["datatype"] == "image"

    def test_pipeline_auto_json(self):
        payload = base64.b64encode(b'{"hello": "world"}').decode()
        document = Converter().convert(
            data_type="auto", data=payload, source="file://rec.json"
        )
        joined = "\n".join(document["content"])
        assert "hello" in joined
        assert document["conversion-info"]["converter"] == "universal"

    def test_pdf_embedded_image_is_inline(self):
        import fitz
        from PIL import Image

        raster = io.BytesIO()
        Image.new("RGB", (320, 320), (20, 80, 180)).save(raster, format="PNG")
        document = fitz.open()
        page = document.new_page(width=400, height=600)
        page.insert_text((50, 40), "BEFORE FIGURE")
        page.insert_image(
            fitz.Rect(50, 80, 350, 380), stream=raster.getvalue()
        )
        page.insert_text((50, 430), "AFTER FIGURE")
        pdf = document.tobytes()
        document.close()
        markdown = extract_markdown(
            pdf,
            "figure.pdf",
            "pdf",
            ocr_config={"enabled": False, "analyze-images": True},
        )
        before = markdown.find("BEFORE FIGURE")
        image = markdown.find("Embedded image")
        after = markdown.find("AFTER FIGURE")
        assert before != -1 and image != -1 and after != -1
        assert before < image < after
