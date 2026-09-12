"""Title: Image analysis

Tests for raster → Markdown conversion.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image

from thot.tasks.converters.image_analysis import (
    ImageAnalysis,
    _compose_description,
    _format_gps,
    _kv_table,
    _open_image,
    _ratio,
    _scene_from_signals,
)
from thot.tasks.converters.image_analysis import _truncate as _ia_truncate
from thot.tasks.converters.image_analysis import (
    analysis_to_markdown,
    analyze_image,
    analyze_image_document,
    image_bytes_to_markdown,
    is_below_analysis_size,
    raster_is_below_analysis_size,
)


def _png_bytes(
    size: tuple[int, int] = (256, 256), color=(20, 40, 180)
) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


class TestImageAnalysis:
    def test_analyze_without_ocr_produces_markdown(self):
        analysis = analyze_image(_png_bytes(), heavy=False)
        assert analysis.width == 256
        assert analysis.height == 256
        markdown = analysis_to_markdown(analysis)
        assert "## Image analysis" in markdown
        assert "256x256" in markdown
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

    def test_skip_icon_sized_raster(self):
        assert is_below_analysis_size(64, 64)
        assert not is_below_analysis_size(256, 256)
        tiny = _png_bytes((32, 32))
        assert raster_is_below_analysis_size(tiny)
        assert raster_is_below_analysis_size(b"not-an-image") is False
        analysis = analyze_image(tiny, heavy=False)
        assert analysis.skipped == "below analysis size threshold"
        assert analysis_to_markdown(analysis) == ""
        markdown, skipped = analyze_image_document(tiny, heavy=False)
        assert markdown == ""
        assert skipped is not None

    def test_analysis_markdown_optional_fields(self):
        record = ImageAnalysis(
            width=12,
            height=8,
            mode="RGB",
            format="PNG",
            unique_colors=3,
            dominant_colors=["#112233"],
            gps="48.850000, 2.350000",
            exif={"Make": "TestCam"},
            ocr_text="HELLO OCR",
            ocr_confidence=91.0,
            ocr_engine="tesseract",
            caption="a caption",
            caption_engine="blip",
            description="desc",
            scene_type="photo",
            scene_reason="exif",
        )
        extra = record.to_extra()
        assert extra["scene_type"] == "photo"
        assert record.to_record()["gps"] == "48.850000, 2.350000"
        markdown = analysis_to_markdown(record)
        assert "HELLO OCR" in markdown
        assert "a caption" in markdown
        assert "TestCam" in markdown

    def test_format_gps_decimal(self):
        assert _format_gps({}) == ""
        gps = {
            "GPSLatitude": ((48, 1), (51, 1), (0, 1)),
            "GPSLatitudeRef": "N",
            "GPSLongitude": ((2, 1), (21, 1), (0, 1)),
            "GPSLongitudeRef": "W",
        }
        formatted = _format_gps(gps)
        assert formatted.startswith("48.")
        assert formatted.endswith(", -2.350000") or ", -" in formatted

    def test_palette_and_unreadable_document(self):
        palette = Image.new("P", (256, 256))
        buf = BytesIO()
        palette.save(buf, format="PNG")
        analysis = analyze_image(buf.getvalue(), heavy=False)
        assert analysis.width == 256
        markdown, failed = analyze_image_document(
            b"not-an-image", source_name="bad.png", heavy=False
        )
        assert failed is None
        assert "Unreadable" in markdown or markdown.startswith("# bad.png")

    def test_open_image_path_and_modes(self):
        rgb = Image.new("RGB", (256, 256), "navy")
        copied = _open_image(rgb)
        assert copied.size == (256, 256)
        cmyk = _open_image(Image.new("CMYK", (256, 256)))
        assert cmyk.mode == "RGB"
        with tempfile.NamedTemporaryFile(suffix=".png") as handle:
            rgb.save(handle.name)
            loaded = _open_image(Path(handle.name))
            assert loaded.size == (256, 256)
            analysis = analyze_image(Path(handle.name), heavy=False)
            assert analysis.width == 256
        assert raster_is_below_analysis_size(b"") is False
        assert _ratio(1, 0) == 0.0
        assert _ratio("x", 2) == 0.0
        assert "truncated" in _ia_truncate("abcdef", 3)
        long_row = _kv_table({"note": "n" * 200})
        assert "note" in long_row

    def test_exif_jpeg_and_scene_signals(self):
        image = Image.new("RGB", (256, 256), (20, 80, 180))
        exif = image.getexif()
        exif[0x010F] = "Canon"
        exif[0x0110] = "EOS"
        buf = BytesIO()
        image.save(buf, format="JPEG", exif=exif)
        analysis = analyze_image(buf.getvalue(), heavy=False)
        assert analysis.width == 256
        canvas = Image.new("RGB", (200, 200), "white")
        stats = {"saturation": 0.1, "edge_density": 0.1, "entropy": 1.0}
        kind, _why = _scene_from_signals(canvas, stats, 100, "", {"Make": "X"})
        assert kind == "photograph"
        kind, _why = _scene_from_signals(canvas, stats, 100, "t" * 300, {})
        assert kind == "text_page"
        kind, _why = _scene_from_signals(canvas, stats, 100, "t" * 100, {})
        assert kind == "text_page"
        kind, _why = _scene_from_signals(
            canvas,
            {"saturation": 0.1, "edge_density": 0.5, "entropy": 1.0},
            100,
            "",
            {},
        )
        assert kind == "line_drawing"
        kind, _why = _scene_from_signals(
            canvas,
            {"saturation": 0.5, "edge_density": 0.1, "entropy": 7.0},
            10_000,
            "",
            {},
        )
        assert kind == "photograph"
        tiny = Image.new("RGB", (16, 16), "black")
        kind, _why = _scene_from_signals(
            tiny, {"saturation": 0, "edge_density": 0, "entropy": 0}, 2, "", {}
        )
        assert kind == "icon"
        composed = _compose_description(
            ImageAnalysis(
                width=8,
                height=8,
                scene_type="photo",
                gps="1, 2",
                exif={"Make": "Canon", "Model": "EOS"},
                ocr_text="readable " * 80,
                dominant_colors=["#000000"],
            )
        )
        assert "EXIF GPS" in composed
        assert "Camera" in composed
        assert "Readable text" in composed
