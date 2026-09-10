"""Title: Image analysis

Tests for raster → Markdown conversion.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from thot.tasks.converters.image_analysis import (
    analysis_to_markdown,
    analyze_image,
    image_bytes_to_markdown,
)


def _png_bytes(size: tuple[int, int] = (64, 64), color=(20, 40, 180)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


class TestImageAnalysis:
    def test_analyze_without_ocr_produces_markdown(self):
        analysis = analyze_image(_png_bytes(), heavy=False)
        assert analysis.width == 64
        assert analysis.height == 64
        markdown = analysis_to_markdown(analysis)
        assert "## Image analysis" in markdown
        assert "64x64" in markdown
        assert analysis.scene_type

    def test_image_bytes_to_markdown_heading(self):
        markdown = image_bytes_to_markdown(
            _png_bytes(),
            source_name="map.png",
            heavy=False,
        )
        assert markdown.startswith("# map.png")
        assert "## Image analysis" in markdown
        assert "| Field | Value |" in markdown
