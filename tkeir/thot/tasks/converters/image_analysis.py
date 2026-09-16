"""Title: Image analysis

Turn a raster into Markdown: visual stats, scene class, EXIF/GPS, Tesseract
OCR, and optional BLIP captions. Weights come from
``resources/modeling`` (tessdata + BLIP), never the Hugging Face hub.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat
from PIL.ExifTags import GPSTAGS, TAGS

Image.MAX_IMAGE_PIXELS = None

SCENE_ICON = "icon"
SCENE_PHOTO = "photograph"
SCENE_TEXT = "text_page"
SCENE_LINE = "line_drawing"
SCENE_GRAPHIC = "graphic"
# Both sides strictly under this box → icon; no OCR, BLIP, or analysis.
MIN_ANALYSIS_SIDE = 256


def is_below_analysis_size(
    width: int,
    height: int,
    min_side: int = MIN_ANALYSIS_SIDE,
) -> bool:
    """Return True when the raster fits under ``min_side``×``min_side``.

    Args:
        width: Pixel width.
        height: Pixel height.
        min_side: Exclusive upper bound on each side (default 256).

    Example:
        >>> is_below_analysis_size(64, 64)
        True
        >>> is_below_analysis_size(256, 256)
        False
        >>> is_below_analysis_size(200, 400)
        False
    """
    return int(width) < int(min_side) and int(height) < int(min_side)


def raster_is_below_analysis_size(
    data: bytes,
    min_side: int = MIN_ANALYSIS_SIDE,
) -> bool:
    """Return True when image bytes decode to an icon-sized raster.

    Unreadable or non-image bytes return False.

    Example:
        >>> from io import BytesIO
        >>> from PIL import Image
        >>> from thot.tasks.converters.image_analysis import (
        ...     raster_is_below_analysis_size,
        ... )
        >>> buf = BytesIO()
        >>> Image.new("RGB", (32, 32), "red").save(buf, format="PNG")
        >>> raster_is_below_analysis_size(buf.getvalue())
        True
    """
    if not data:
        return False
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            return is_below_analysis_size(
                image.width, image.height, min_side=min_side
            )
    except Exception:
        return False


@dataclass
class ImageAnalysis:
    """Measured properties of one raster (no filename taxonomy).

    Example:
        >>> from thot.tasks.converters.image_analysis import ImageAnalysis
        >>> ImageAnalysis(width=10, height=10).to_extra()["ocr_chars"]
        0
    """

    width: int = 0
    height: int = 0
    mode: str = ""
    format: str = ""
    skipped: str = ""
    brightness: float = 0.0
    contrast: float = 0.0
    saturation: float = 0.0
    edge_density: float = 0.0
    entropy: float = 0.0
    unique_colors: int = 0
    dominant_colors: list[str] = field(default_factory=list)
    exif: dict[str, str] = field(default_factory=dict)
    gps: str = ""
    scene_type: str = ""
    scene_reason: str = ""
    ocr_text: str = ""
    ocr_confidence: float | None = None
    ocr_engine: str = ""
    caption: str = ""
    caption_engine: str = ""
    description: str = ""

    def to_extra(self) -> dict[str, Any]:
        """Compact metadata for conversion-info.

        Example:
            >>> ImageAnalysis(scene_type="graphic").to_extra()["scene_type"]
            'graphic'
        """
        return {
            "scene_type": self.scene_type,
            "ocr_chars": len(self.ocr_text.strip()),
            "caption_engine": self.caption_engine or self.ocr_engine,
        }

    def to_record(self) -> dict[str, Any]:
        """Structured fields for corpus JSON / ``## Information``.

        Includes pixel size, colour mode, unique-colour count, and the
        adaptive colour map when analysis produced one.

        Example:
            >>> ImageAnalysis(
            ...     width=8, height=4, mode="RGB", format="PNG",
            ...     unique_colors=3, dominant_colors=["#112233"],
            ... ).to_record()["size"]
            '8x4'
        """
        record: dict[str, Any] = {}
        if self.width or self.height:
            record["width"] = int(self.width)
            record["height"] = int(self.height)
            record["size"] = f"{self.width}x{self.height}"
        if self.mode:
            record["mode"] = self.mode
        if self.format:
            record["format"] = self.format
        if self.unique_colors:
            record["unique_colors"] = int(self.unique_colors)
        if self.dominant_colors:
            record["color_map"] = list(self.dominant_colors)
        if self.scene_type:
            record["scene_type"] = self.scene_type
        if self.gps:
            record["gps"] = self.gps
        return record


def _heading(title: str, level: int = 2) -> str:
    """ATX heading line.

    Example:
        >>> _heading("OCR text", 3)
        '### OCR text\\n'
    """
    hashes = "#" * max(1, min(level, 6))
    return hashes + " " + title.strip() + "\n"


def _kv_table(rows: dict[str, object]) -> str:
    """Markdown key/value table.

    Example:
        >>> "| size |" in _kv_table({"size": "8x8"})
        True
    """
    lines = ["| Field | Value |", "|---|---|"]
    for key, value in rows.items():
        val = str(value).replace("|", "\\|").replace("\n", " ")
        if len(val) < 120:
            lines.append("| " + key + " | `" + val + "` |")
        else:
            lines.append("| " + key + " | " + val[:500] + " |")
    return "\n".join(lines) + "\n"


def _fenced(code: str, lang: str = "") -> str:
    """Fenced code block.

    Example:
        >>> "```" in _fenced("hello")
        True
    """
    body = (code or "").rstrip() + "\n"
    fence = "````" if "```" in body else "```"
    return fence + lang + "\n" + body + fence + "\n"


def _truncate(text: str, limit: int) -> str:
    """Trim text to ``limit`` characters.

    Example:
        >>> "truncated" in _truncate("abcdef", 3)
        True
    """
    if len(text) <= limit:
        return text
    return (
        text[:limit] + "\n\n... truncated at " + str(limit) + " characters.\n"
    )


def _open_image(source: Path | Image.Image | bytes) -> Image.Image:
    """Load a raster from a path, PIL image, or file bytes.

    Example:
        >>> from io import BytesIO
        >>> from PIL import Image
        >>> from thot.tasks.converters.image_analysis import _open_image
        >>> buf = BytesIO()
        >>> Image.new("RGB", (8, 8), "red").save(buf, format="PNG")
        >>> _open_image(buf.getvalue()).size
        (8, 8)
    """
    if isinstance(source, Image.Image):
        if source.mode not in {"RGB", "L", "RGBA"}:
            return source.convert("RGB")
        return source.copy()
    if isinstance(source, (bytes, bytearray)):
        with Image.open(io.BytesIO(source)) as image:
            image.load()
            return image.copy()
    with Image.open(source) as image:
        image.load()
        return image.copy()


def _ratio(num, den) -> float:
    """Safe numerator/denominator.

    Example:
        >>> _ratio(1, 2)
        0.5
    """
    try:
        return float(num) / float(den) if den else 0.0
    except Exception:
        return 0.0


def _format_gps(gps: dict) -> str:
    """Format EXIF GPS as ``lat, lon``.

    Example:
        >>> _format_gps({})
        ''
    """

    def _coord(values, ref) -> float | None:
        if not values or len(values) < 3:
            return None
        first = values[0]
        second = values[1]
        third = values[2]
        deg = _ratio(*first) if isinstance(first, tuple) else float(first)
        minutes = (
            _ratio(*second) if isinstance(second, tuple) else float(second)
        )
        seconds = _ratio(*third) if isinstance(third, tuple) else float(third)
        dec = deg + minutes / 60.0 + seconds / 3600.0
        if str(ref).upper() in {"S", "W"}:
            dec = -dec
        return dec

    lat = _coord(gps.get("GPSLatitude"), gps.get("GPSLatitudeRef"))
    lon = _coord(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef"))
    if lat is None or lon is None:
        return ""
    return f"{lat:.6f}, {lon:.6f}"


def _exif_and_gps(im: Image.Image) -> tuple[dict[str, str], str]:
    """Extract a small EXIF subset and GPS string.

    Example:
        >>> from PIL import Image
        >>> _exif_and_gps(Image.new("RGB", (8, 8)))
        ({}, '')
    """
    exif_out: dict[str, str] = {}
    gps_txt = ""
    try:
        raw = im.getexif()
    except Exception:
        return exif_out, gps_txt
    if not raw:
        return exif_out, gps_txt
    for tag_id, value in raw.items():
        name = TAGS.get(tag_id, str(tag_id))
        if name == "GPSInfo" and isinstance(value, dict):
            gps = {GPSTAGS.get(k, str(k)): value[k] for k in value}
            gps_txt = _format_gps(gps)
            continue
        if name in {
            "Make",
            "Model",
            "DateTime",
            "DateTimeOriginal",
            "Software",
            "Orientation",
            "LensModel",
        }:
            exif_out[name] = str(value)[:120]
    return exif_out, gps_txt


def _dominant_colors(im: Image.Image, n: int = 5) -> list[str]:
    """Adaptive palette hex colours.

    Example:
        >>> from PIL import Image
        >>> colours = _dominant_colors(Image.new("RGB", (16, 16), (10, 20, 30)))
        >>> colours[0].startswith("#")
        True
    """
    small = im.convert("RGB").copy()
    small.thumbnail((80, 80))
    pal = small.convert("P", palette=Image.Palette.ADAPTIVE, colors=n)
    palette = pal.getpalette()
    if not palette:
        return []
    colors = palette[: n * 3]
    out: list[str] = []
    for index in range(0, len(colors), 3):
        out.append(
            f"#{colors[index]:02x}{colors[index + 1]:02x}"
            f"{colors[index + 2]:02x}"
        )
    return out


def _unique_color_count(im: Image.Image) -> int:
    """Unique RGB colours on a 48px thumbnail.

    Example:
        >>> from PIL import Image
        >>> _unique_color_count(Image.new("RGB", (32, 32), "white"))
        1
    """
    small = im.convert("RGB").copy()
    small.thumbnail((48, 48))
    pixels = list(small.getdata())
    return len(set(pixels))


def _visual_stats(im: Image.Image) -> dict[str, float]:
    """Brightness, contrast, saturation, edges, entropy.

    Example:
        >>> from PIL import Image
        >>> stats = _visual_stats(Image.new("RGB", (16, 16), "white"))
        >>> stats["brightness"] > 0.9
        True
    """
    rgb = im.convert("RGB")
    gray = rgb.convert("L")
    stat = ImageStat.Stat(gray)
    brightness = stat.mean[0] / 255.0
    contrast = (stat.stddev[0] / 255.0) if stat.stddev else 0.0
    hsv = rgb.convert("HSV")
    sat = ImageStat.Stat(hsv).mean[1] / 255.0
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_pixels = list(edges.getdata())
    edge_density = sum(1 for pixel in edge_pixels if pixel > 40) / max(
        len(edge_pixels), 1
    )
    hist = gray.histogram()
    total = sum(hist) or 1
    entropy = 0.0
    for count in hist:
        if count:
            prob = count / total
            entropy -= prob * math.log2(prob)
    return {
        "brightness": round(brightness, 3),
        "contrast": round(contrast, 3),
        "saturation": round(sat, 3),
        "edge_density": round(edge_density, 3),
        "entropy": round(entropy, 3),
    }


def _scene_from_signals(
    im: Image.Image,
    stats: dict[str, float],
    unique_colors: int,
    ocr_text: str,
    exif: dict[str, str],
) -> tuple[str, str]:
    """Classify from measurable properties only.

    Example:
        >>> from PIL import Image
        >>> im = Image.new("RGB", (16, 16), "black")
        >>> kind, _why = _scene_from_signals(
        ...     im, {"saturation": 0, "edge_density": 0, "entropy": 0}, 2, "", {}
        ... )
        >>> kind
        'icon'
    """
    width, height = im.size
    pixels = max(width * height, 1)
    ocr_len = len(ocr_text.strip())
    ocr_density = ocr_len / pixels
    if min(width, height) < 48 or (
        pixels < 80 * 80 and unique_colors <= 24 and stats["entropy"] < 3.5
    ):
        return SCENE_ICON, "small raster with a tiny palette (icon-like)"
    if exif.get("Make") or exif.get("Model"):
        return SCENE_PHOTO, "camera EXIF present"
    if ocr_len > 250 and stats["saturation"] < 0.25:
        return SCENE_TEXT, "high OCR volume on a low-saturation page"
    if ocr_density > 0.002 and stats["saturation"] < 0.3:
        return SCENE_TEXT, "text density relative to pixel count"
    if (
        stats["edge_density"] > 0.2
        and stats["saturation"] < 0.35
        and ocr_len < 80
    ):
        return SCENE_LINE, "high edge density, little colour, little text"
    if stats["entropy"] > 6.5 and stats["saturation"] > 0.2:
        return (
            SCENE_PHOTO,
            "high luminance entropy and colour typical of a photo",
        )
    return SCENE_GRAPHIC, "mixed or unclassified raster"


def _ocr(im: Image.Image, lang: str) -> tuple[str, float | None, str]:
    """Tesseract OCR with bundled tessdata when present.

    Example:
        >>> from PIL import Image
        >>> text, _conf, engine = _ocr(Image.new("RGB", (8, 8), "white"), "eng")
        >>> isinstance(text, str) and isinstance(engine, str)
        True
    """
    try:
        import pytesseract

        from thot.tasks.converters.PdfImageOcr import tessdata_tesseract_config
    except Exception:
        return "", None, ""
    work = im.convert("RGB")
    work.thumbnail((2200, 2200))
    kwargs: dict[str, Any] = {"lang": lang}
    tessdata = tessdata_tesseract_config()
    if tessdata:
        kwargs["config"] = tessdata
    try:
        data = pytesseract.image_to_data(
            work, output_type=pytesseract.Output.DICT, **kwargs
        )
    except pytesseract.TesseractError:
        try:
            fallback = dict(kwargs)
            fallback["lang"] = "eng"
            data = pytesseract.image_to_data(
                work, output_type=pytesseract.Output.DICT, **fallback
            )
            lang = "eng"
        except Exception:
            return "", None, ""
    except Exception:
        return "", None, ""
    words: list[str] = []
    confs: list[float] = []
    for text, conf in zip(data.get("text", []), data.get("conf", [])):
        token = (text or "").strip()
        try:
            score = float(conf)
        except (TypeError, ValueError):
            score = -1
        if token and score >= 40:
            words.append(token)
            confs.append(score)
    mean = sum(confs) / len(confs) if confs else None
    engine = "tesseract:" + lang if words else ""
    return " ".join(words), mean, engine


def _compose_description(analysis: ImageAnalysis) -> str:
    """One-paragraph summary for the Markdown body.

    Example:
        >>> a = ImageAnalysis(width=8, height=8, scene_type="icon")
        >>> "8x8" in _compose_description(a)
        True
    """
    bits = [
        "This is a "
        + str(analysis.width)
        + "x"
        + str(analysis.height)
        + " "
        + (analysis.scene_type.replace("_", " ") or "raster")
        + ((" (" + analysis.format + ")") if analysis.format else "")
        + "."
    ]
    if analysis.caption:
        bits.append(analysis.caption.rstrip(".") + ".")
    bits.append(
        "Visual stats: brightness "
        + f"{analysis.brightness:.2f}"
        + ", contrast "
        + f"{analysis.contrast:.2f}"
        + ", saturation "
        + f"{analysis.saturation:.2f}"
        + ", edge density "
        + f"{analysis.edge_density:.2f}"
        + ", entropy "
        + f"{analysis.entropy:.2f}"
        + ", unique colours (48px sample) "
        + str(analysis.unique_colors)
        + "."
    )
    if analysis.dominant_colors:
        bits.append(
            "Dominant colours: " + ", ".join(analysis.dominant_colors) + "."
        )
    if analysis.gps:
        bits.append("EXIF GPS: " + analysis.gps + ".")
    if analysis.exif.get("Make") or analysis.exif.get("Model"):
        bits.append(
            "Camera: "
            + " ".join(
                filter(
                    None,
                    [analysis.exif.get("Make"), analysis.exif.get("Model")],
                )
            )
            + "."
        )
    if analysis.ocr_text.strip():
        snippet = analysis.ocr_text.strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "..."
        bits.append("Readable text in the image: " + snippet)
    return " ".join(bits)


def analyze_image(
    source: Path | Image.Image | bytes,
    *,
    ocr_lang: str = "eng+fra+deu+spa+ita+nld+por+pol+ara",
    min_side: int = MIN_ANALYSIS_SIDE,
    source_path: Path | None = None,
    heavy: bool = True,
    captions: bool = True,
) -> ImageAnalysis:
    """Analyse a raster and fill :class:`ImageAnalysis`.

    Args:
        source: Path, PIL image, or image file bytes.
        ocr_lang: Tesseract ``-l`` value.
        min_side: Skip all analysis when both sides are below this (icons).
        source_path: Optional path used only in the skip description.
        heavy: When False, skip OCR (stats still run for large rasters).
        captions: When False, skip BLIP (default True with ``heavy``).

    Returns:
        Filled analysis (never raises on OCR/BLIP failure). Icon-sized
        rasters set ``skipped`` and do not run stats, OCR, or BLIP.

    Example:
        >>> from io import BytesIO
        >>> from PIL import Image
        >>> from thot.tasks.converters.image_analysis import analyze_image
        >>> buf = BytesIO()
        >>> Image.new("RGB", (64, 64), (20, 40, 200)).save(buf, format="PNG")
        >>> a = analyze_image(buf.getvalue(), heavy=False)
        >>> a.width, a.height
        (64, 64)
        >>> a.skipped
        'below analysis size threshold'
    """
    path = source if isinstance(source, Path) else source_path
    im = _open_image(source)
    analysis = ImageAnalysis(
        width=im.width,
        height=im.height,
        mode=im.mode,
        format=getattr(im, "format", "") or "",
    )
    if is_below_analysis_size(im.width, im.height, min_side=min_side):
        analysis.skipped = "below analysis size threshold"
        analysis.scene_type = SCENE_ICON
        analysis.scene_reason = (
            f"under {min_side}x{min_side} icon; not analysed"
        )
        name = path.name if isinstance(path, Path) else "in-memory"
        analysis.description = (
            "Icon-sized raster ("
            + str(im.width)
            + "x"
            + str(im.height)
            + "); skipped. Source: "
            + name
            + "."
        )
        return analysis

    stats_im = im.copy()
    stats_im.thumbnail((800, 800))
    stats = _visual_stats(stats_im)
    analysis.brightness = stats["brightness"]
    analysis.contrast = stats["contrast"]
    analysis.saturation = stats["saturation"]
    analysis.edge_density = stats["edge_density"]
    analysis.entropy = stats["entropy"]
    analysis.unique_colors = _unique_color_count(im)
    analysis.dominant_colors = _dominant_colors(im)
    analysis.exif, analysis.gps = _exif_and_gps(im)

    if heavy:
        analysis.ocr_text, analysis.ocr_confidence, analysis.ocr_engine = _ocr(
            im, ocr_lang
        )
    if captions and heavy:
        try:
            from thot.tasks.converters.image_captions import caption_pil_image

            analysis.caption, analysis.caption_engine = caption_pil_image(im)
        except Exception:
            pass

    analysis.scene_type, analysis.scene_reason = _scene_from_signals(
        im, stats, analysis.unique_colors, analysis.ocr_text, analysis.exif
    )
    analysis.description = _compose_description(analysis)
    return analysis


def analysis_to_markdown(
    analysis: ImageAnalysis, title: str = "Image analysis"
) -> str:
    """Render an analysis as Markdown (heading, description, table, OCR).

    Args:
        analysis: Result of :func:`analyze_image`.
        title: Section heading.

    Returns:
        Markdown string.

    Example:
        >>> from thot.tasks.converters.image_analysis import (
        ...     ImageAnalysis, analysis_to_markdown,
        ... )
        >>> md = analysis_to_markdown(ImageAnalysis(width=8, height=8, scene_type="icon", description="tiny"))
        >>> "## Image analysis" in md and "tiny" in md
        True
    """
    if analysis.skipped == "below analysis size threshold":
        return ""
    rows: dict[str, object] = {
        "scene": analysis.scene_type,
        "why": analysis.scene_reason,
        "size": f"{analysis.width}x{analysis.height} {analysis.mode}",
        "brightness/contrast/sat": (
            f"{analysis.brightness:.2f} / {analysis.contrast:.2f} / "
            f"{analysis.saturation:.2f}"
        ),
        "edges / entropy": (
            f"{analysis.edge_density:.2f} / {analysis.entropy:.2f}"
        ),
        "unique colours": analysis.unique_colors,
        "colours": ", ".join(analysis.dominant_colors),
    }
    if analysis.gps:
        rows["gps"] = analysis.gps
    if analysis.exif:
        rows["exif"] = "; ".join(
            f"{key}={value}" for key, value in analysis.exif.items()
        )
    if analysis.ocr_engine:
        extra = ""
        if analysis.ocr_confidence is not None:
            extra = f" (conf {analysis.ocr_confidence:.0f})"
        rows["ocr"] = analysis.ocr_engine + extra
    if analysis.caption_engine:
        rows["caption_engine"] = analysis.caption_engine
    chunks = [
        _heading(title, 2),
        analysis.description + "\n",
        _kv_table(rows),
    ]
    if analysis.caption:
        chunks.append(_heading("Caption", 3) + analysis.caption + "\n")
    if analysis.ocr_text.strip():
        chunks.append(
            _heading("OCR text", 3)
            + _fenced(_truncate(analysis.ocr_text.strip(), 8000))
        )
    return "\n".join(chunks)


def analyze_image_document(
    data: bytes,
    *,
    title: str = "Image analysis",
    ocr_lang: str = "eng+fra+deu+spa+ita+nld+por+pol+ara",
    source_name: str = "",
    heavy: bool = True,
    captions: bool = True,
    min_side: int = MIN_ANALYSIS_SIDE,
) -> tuple[str, ImageAnalysis | None]:
    """Analyse image bytes and return Markdown plus the analysis object.

    Args:
        data: Image file bytes.
        title: Analysis section title.
        ocr_lang: Tesseract languages.
        source_name: Optional filename used as ``#`` heading.
        heavy: Run OCR when True.
        captions: Run BLIP when True (also requires ``heavy``).
        min_side: Skip analysis when both sides are below this.

    Returns:
        ``(markdown, analysis)``. Empty markdown when the raster is
        icon-sized or cannot be opened.

    Example:
        >>> from io import BytesIO
        >>> from PIL import Image
        >>> from thot.tasks.converters.image_analysis import (
        ...     analyze_image_document,
        ... )
        >>> buf = BytesIO()
        >>> Image.new("RGB", (256, 256), "navy").save(buf, format="PNG")
        >>> md, analysis = analyze_image_document(
        ...     buf.getvalue(), source_name="navy.png", heavy=False
        ... )
        >>> md.startswith("# navy.png")
        True
        >>> analysis.width
        256
    """
    try:
        analysis = analyze_image(
            data,
            ocr_lang=ocr_lang,
            heavy=heavy,
            captions=captions,
            min_side=min_side,
        )
    except Exception as exc:
        name = Path(source_name).name if source_name else "image"
        return (
            "# " + name + "\n\nUnreadable raster: " + str(exc) + "\n",
            None,
        )
    body = analysis_to_markdown(analysis, title)
    if not body.strip():
        return "", analysis
    chunks: list[str] = []
    if source_name:
        chunks.append("# " + Path(source_name).name + "\n")
    chunks.append(body)
    return "\n".join(chunks), analysis


def image_bytes_to_markdown(
    data: bytes,
    *,
    title: str = "Image analysis",
    ocr_lang: str = "eng+fra+deu+spa+ita+nld+por+pol+ara",
    source_name: str = "",
    heavy: bool = True,
    captions: bool = True,
    min_side: int = MIN_ANALYSIS_SIDE,
) -> str:
    """Analyse image bytes and return Markdown (optional H1 from filename).

    Icon-sized rasters (both sides under ``min_side``) return an empty
    string. Standalone photos use 256; embedded PDF/Office figures use a
    lower floor so diagrams still get scene / OCR / caption Markdown.

    Args:
        data: Image file bytes.
        title: Analysis section title.
        ocr_lang: Tesseract languages.
        source_name: Optional filename used as ``#`` heading.
        heavy: Run OCR when True.
        captions: Run BLIP when True (also requires ``heavy``).
        min_side: Skip analysis when both sides are below this.

    Returns:
        Markdown document fragment, or ``""`` for icons.

    Example:
        >>> from io import BytesIO
        >>> from PIL import Image
        >>> from thot.tasks.converters.image_analysis import image_bytes_to_markdown
        >>> buf = BytesIO()
        >>> Image.new("RGB", (256, 256), "navy").save(buf, format="PNG")
        >>> md = image_bytes_to_markdown(
        ...     buf.getvalue(), source_name="navy.png", heavy=False
        ... )
        >>> md.startswith("# navy.png")
        True
        >>> "## Image analysis" in md
        True
    """
    markdown, _analysis = analyze_image_document(
        data,
        title=title,
        ocr_lang=ocr_lang,
        source_name=source_name,
        heavy=heavy,
        captions=captions,
        min_side=min_side,
    )
    return markdown
