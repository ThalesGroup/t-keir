"""Title: Universal Converter

Classify a source file and extract Markdown for the T-KEIR pipeline.

Adapted from the corpus converter (classify + document handlers) so ingest
and ``PipelineRunner`` can accept office, image, archive, HTML, XML, and
tabular files as one datatype path.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import csv
import io
import re
import tempfile
import zipfile
from pathlib import Path

from thot.tasks.converters.MarkdownSections import text_to_content

MAX_TEXT_CHARS = 400_000
MAX_TABLE_ROWS = 500
MAX_ARCHIVE_MEMBER_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 1024
MAX_PDF_IMAGES_PER_PAGE = 32
MAX_EMBEDDED_IMAGES = 1024
# Embedded figures in PDF/Office are often smaller than standalone photos.
EMBEDDED_MIN_SIDE = 64

IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".gif",
    ".png",
    ".bmp",
    ".webp",
}
TEXT_SUFFIXES = {
    ".txt",
    ".text",
    ".md",
    ".markdown",
    ".log",
    ".dat",
    ".ini",
    ".inf",
    ".me",
}
TABULAR_SUFFIXES = {".csv", ".tsv"}
ARCHIVE_SUFFIXES = {".zip"}
IMAGE_MAGIC = (
    (b"\xff\xd8\xff", "image"),
    (b"\x89PNG\r\n\x1a\n", "image"),
    (b"GIF87a", "image"),
    (b"GIF89a", "image"),
)

UNIVERSAL_TYPES = frozenset(
    {
        "auto",
        "unknown",
        "image",
        "zip",
        "md",
        "json",
        "doc",
        "svg",
        "tiff",
        "tif",
    }
)


def classify_kind(path: str, data: bytes) -> str:
    """Return a converter datatype for ``path`` and ``data``.

    Args:
        path: Source path or filename (extension is used).
        data: File bytes.

    Returns:
        Lowercase datatype such as ``pdf``, ``image``, or ``raw``.

    Example:
        >>> classify_kind("note.txt", b"Hello")
        'raw'
        >>> classify_kind("scan.jpg", bytes([0xFF, 0xD8, 0xFF, 0xE0]))
        'image'
    """
    suffix = Path(path or "").suffix.lower()
    lower = Path(path or "").name.lower()
    if not data:
        return "raw"
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.lstrip().startswith(b"{\\rtf"):
        return "rtf"
    head = data[:512].lstrip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        return "html"
    if head.startswith(b"<?xml") or suffix in {".xml", ".gml", ".rss"}:
        return "xml" if suffix != ".rss" else "rss"
    for magic, kind in IMAGE_MAGIC:
        if data.startswith(magic):
            return kind
    if suffix in IMAGE_SUFFIXES or suffix in {".tif", ".tiff"}:
        return "image"
    if suffix == ".svg":
        return "svg"
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".docx":
        return "docx"
    if suffix == ".doc":
        return "doc"
    if suffix == ".pptx":
        return "pptx"
    if suffix in {".ppt"}:
        return "ppt"
    if suffix == ".xlsx":
        return "xlsx"
    if suffix in {".xls"}:
        return "xls"
    if suffix in TABULAR_SUFFIXES:
        return "csv"
    if suffix in {".md", ".markdown"}:
        return "md"
    if suffix == ".json":
        return "json"
    if suffix in ARCHIVE_SUFFIXES:
        return "zip"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in TEXT_SUFFIXES or lower in {"readme", "version"}:
        return "raw"
    if data.startswith(b"PK\x03\x04"):
        if suffix == ".docx":
            return "docx"
        if suffix == ".pptx":
            return "pptx"
        if suffix == ".xlsx":
            return "xlsx"
        return "zip"
    sample = data[:8192]
    if b"\x00" not in sample:
        try:
            text = sample.decode("utf-8")
        except UnicodeDecodeError:
            text = ""
        if text and _mostly_printable(text):
            return "raw"
    return "unknown"


def _mostly_printable(text: str) -> bool:
    """Return True when a text sample is mostly printable.

    Example:
        >>> _mostly_printable("hello")
        True
    """
    if not text:
        return False
    printable = sum(
        1 for char in text if char.isprintable() or char in "\n\r\t"
    )
    return printable / len(text) >= 0.85


def _decode_text(data: bytes, limit: int = MAX_TEXT_CHARS) -> str:
    """Decode bytes with UTF-8 then Latin-1 fallback.

    Example:
        >>> _decode_text("café".encode())
        'café'
    """
    sample = data[:limit]
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return sample.decode(encoding)
        except UnicodeDecodeError:
            continue
    return sample.decode("latin-1", errors="replace")


def _truncate(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    """Trim extracted text to ``limit`` characters.

    Example:
        >>> "truncated at 3" in _truncate("abcd", 3)
        True
    """
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... truncated at {limit} characters.\n"


def extract_markdown(
    data: bytes,
    source: str,
    data_type: str,
    *,
    ocr_config: dict | None = None,
) -> str:
    """Extract Markdown (or plain text) from document bytes.

    Args:
        data: Raw file bytes.
        source: Path or URI used for classification / titles.
        data_type: Converter datatype (``auto`` re-classifies).
        ocr_config: Optional OCR settings (``enabled``, ``languages``).

    Returns:
        Extracted text. Empty string when nothing could be read.

    Example:
        >>> extract_markdown(b"Hello world", "file.txt", "raw").strip()
        'Hello world'
    """
    kind = (data_type or "auto").strip().lower()
    if kind in {"auto", ""}:
        kind = classify_kind(source, data)
    if kind in {"raw", "md", "text", "json"}:
        return _truncate(_decode_text(data))
    if kind in {"csv", "tsv"}:
        return _extract_csv(data, kind)
    if kind in {"html", "htm"}:
        return _extract_html(data)
    if kind in {"xml", "rss", "gml", "svg"}:
        return _extract_xml(data)
    if kind == "pdf":
        return _extract_pdf(data, ocr_config)
    if kind in {"docx", "doc"}:
        return _extract_docx(data, kind, ocr_config)
    if kind in {"pptx", "ppt"}:
        return _extract_pptx(data, ocr_config)
    if kind in {"xlsx", "xls"}:
        return _extract_xlsx(data, kind, ocr_config)
    if kind in {"image", "tiff", "tif"}:
        return _extract_image(data, source, ocr_config)
    if kind == "zip":
        return _extract_zip(data, source, ocr_config)
    return _extract_unknown(data, source)


def _extract_csv(data: bytes, kind: str) -> str:
    """Render a CSV/TSV sample as Markdown.

    Example:
        >>> "Name" in _extract_csv(b"Name,Age\\nAda,36\\n", "csv")
        True
    """
    text = _decode_text(data, limit=2_000_000)
    sep = "\t" if kind == "tsv" or text.count("\t") >= 2 else ","
    reader = csv.reader(io.StringIO(text), delimiter=sep)
    rows = []
    for index, row in enumerate(reader):
        if index > MAX_TABLE_ROWS:
            rows.append([f"... truncated after {MAX_TABLE_ROWS} rows"])
            break
        rows.append(row)
    if not rows:
        return text
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header = normalized[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in normalized[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def _extract_html(data: bytes) -> str:
    """Strip HTML to visible text.

    Example:
        >>> "Hi" in _extract_html(b"<html><body>Hi</body></html>")
        True
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_decode_text(data), "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    body = soup.get_text("\n", strip=True)
    if title and title not in body:
        return f"# {title}\n\n{body}"
    return body


def _extract_xml(data: bytes) -> str:
    """Collect text nodes from XML / SVG.

    Example:
        >>> "hello" in _extract_xml(b"<root>hello</root>")
        True
    """
    try:
        from lxml import etree

        parser = etree.XMLParser(recover=True, huge_tree=True)
        root = etree.fromstring(data, parser)
        texts = [t.strip() for t in root.itertext() if t and t.strip()]
        return _truncate("\n".join(texts))
    except Exception:
        return _truncate(_decode_text(data))


_DOCX_IMG_ALT = "TKEIRIMG"


def _extract_docx(
    data: bytes, kind: str, ocr_config: dict | None = None
) -> str:
    """Convert Word documents via mammoth (and macOS textutil for ``.doc``).

    Embedded rasters are analysed and spliced into the markdown at the
    picture's original position (not dumped after the body).

    Example:
        >>> callable(_extract_docx)
        True
    """
    if kind == "doc":
        text = _legacy_doc_text(data)
        if text:
            return _truncate(text)
    store: list[bytes] = []
    body = ""
    try:
        import mammoth

        def convert_image(image):
            try:
                with image.open() as handle:
                    payload = handle.read()
            except Exception:
                payload = b""
            store.append(payload)
            idx = len(store) - 1
            return {
                "src": f"tkeir-img://{idx}",
                "alt": f"{_DOCX_IMG_ALT}{idx}",
            }

        result = mammoth.convert_to_markdown(
            io.BytesIO(data),
            convert_image=mammoth.images.img_element(convert_image),
        )
        body = (result.value or "").strip()
    except Exception:
        body = ""
        store = []

    def _replace(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        if idx < 0 or idx >= len(store):
            return ""
        extra = _image_analysis_markdown(
            store[idx],
            title=f"Embedded image {idx + 1}",
            ocr_config=ocr_config,
            min_side=EMBEDDED_MIN_SIDE,
        )
        return ("\n\n" + extra.strip() + "\n\n") if extra.strip() else ""

    if body and store:
        body = re.sub(
            rf"!\[{_DOCX_IMG_ALT}(\d+)\]\(tkeir-img://\d+\)",
            _replace,
            body,
        )
    used = {_payload_key(payload) for payload in store if payload}
    leftover = [
        item
        for item in _zip_media_payloads(data, ("word/media/",))
        if _payload_key(item[1]) not in used
    ]
    if leftover and not store:
        extra = _media_analysis_markdown(
            leftover,
            title_prefix="Embedded image",
            ocr_config=ocr_config,
        )
        if extra:
            body = (body + "\n\n" + extra).strip() if body else extra
    return _truncate(body)


def _legacy_doc_text(data: bytes) -> str:
    """Best-effort ``.doc`` extraction.

    Example:
        >>> _legacy_doc_text(b"") == ""
        True
    """
    import subprocess
    import sys

    with tempfile.NamedTemporaryFile(suffix=".doc") as handle:
        handle.write(data)
        handle.flush()
        if sys.platform == "darwin":
            proc = subprocess.run(
                ["textutil", "-convert", "txt", "-stdout", handle.name],
                capture_output=True,
                check=False,
            )
            if proc.returncode == 0:
                return proc.stdout.decode("utf-8", errors="replace").strip()
        try:
            import mammoth

            result = mammoth.extract_raw_text(handle.name)
            return (result.value or "").strip()
        except Exception:
            return ""


def _extract_pptx(data: bytes, ocr_config: dict | None = None) -> str:
    """Collect slide text and analyse embedded pictures as Markdown.

    Slide ``PICTURE`` shapes are analysed first. Remaining rasters under
    ``ppt/media/`` (backgrounds, unused media) get the same treatment.

    Example:
        >>> callable(_extract_pptx)
        True
    """
    chunks: list[str] = []
    seen: set[tuple[int, bytes]] = set()
    try:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE
    except ImportError:
        Presentation = None  # type: ignore[assignment]
        MSO_SHAPE_TYPE = None  # type: ignore[assignment]
    if Presentation is not None:
        try:
            with tempfile.NamedTemporaryFile(suffix=".pptx") as handle:
                handle.write(data)
                handle.flush()
                presentation = Presentation(handle.name)
            pictures = 0
            limit = _embedded_image_limit(ocr_config)
            for index, slide in enumerate(presentation.slides, start=1):
                lines = [f"## Slide {index}"]
                shapes = sorted(
                    list(slide.shapes),
                    key=lambda shape: (
                        int(getattr(shape, "top", 0) or 0),
                        int(getattr(shape, "left", 0) or 0),
                    ),
                )
                for shape in shapes:
                    if getattr(shape, "has_text_frame", False):
                        text = "\n".join(
                            paragraph.text
                            for paragraph in shape.text_frame.paragraphs
                            if paragraph.text
                        ).strip()
                        if text:
                            lines.append(text)
                    if (
                        _analyze_images_enabled(ocr_config)
                        and pictures < limit
                        and getattr(shape, "shape_type", None)
                        == MSO_SHAPE_TYPE.PICTURE
                    ):
                        try:
                            blob = shape.image.blob
                        except Exception:
                            continue
                        seen.add(_payload_key(blob))
                        extra = _image_analysis_markdown(
                            blob,
                            title=f"Slide {index} picture",
                            ocr_config=ocr_config,
                            min_side=EMBEDDED_MIN_SIDE,
                        )
                        if not extra.strip():
                            continue
                        pictures += 1
                        lines.append(extra)
                if len(lines) > 1:
                    chunks.append("\n".join(lines))
        except Exception:
            chunks = []
    leftover = [
        item
        for item in _zip_media_payloads(data, ("ppt/media/",))
        if _payload_key(item[1]) not in seen
    ]
    extra = ""
    if leftover and not seen:
        extra = _media_analysis_markdown(
            leftover,
            title_prefix="Deck media",
            ocr_config=ocr_config,
        )
    joined = "\n\n".join(chunks)
    if extra:
        joined = (joined + "\n\n" + extra).strip() if joined else extra
    return _truncate(joined)


def _extract_xlsx(
    data: bytes, kind: str, ocr_config: dict | None = None
) -> str:
    """Render spreadsheet sheets as Markdown tables.

    ``.xlsx`` packages also analyse rasters under ``xl/media/``.

    Example:
        >>> callable(_extract_xlsx)
        True
    """
    chunks: list[str] = []
    placed_images = False
    try:
        import pandas as pd
    except ImportError:
        pd = None  # type: ignore[assignment]
    if pd is not None:
        engine = "openpyxl" if kind == "xlsx" else "xlrd"
        suffix = ".xlsx" if kind == "xlsx" else ".xls"
        with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
            handle.write(data)
            handle.flush()
            try:
                xl = pd.ExcelFile(handle.name, engine=engine)
            except Exception:
                xl = None
            if xl is not None:
                for sheet in xl.sheet_names:
                    frame = xl.parse(sheet, dtype=str)
                    chunks.append(f"## {sheet}")
                    if frame.empty:
                        chunks.append("_empty sheet_")
                    else:
                        view = frame.head(MAX_TABLE_ROWS)
                        try:
                            chunks.append(view.to_markdown(index=False))
                        except Exception:
                            chunks.append(view.to_string(index=False))
                    sheet_images = _xlsx_sheet_images(data, sheet, ocr_config)
                    if sheet_images:
                        chunks.append(sheet_images)
                        placed_images = True
    extra = ""
    if kind == "xlsx" and not placed_images:
        extra = _media_analysis_markdown(
            _zip_media_payloads(data, ("xl/media/",)),
            title_prefix="Sheet media",
            ocr_config=ocr_config,
        )
    joined = "\n\n".join(chunks)
    if extra:
        joined = (joined + "\n\n" + extra).strip() if joined else extra
    return _truncate(joined)


def _xlsx_sheet_images(
    data: bytes, sheet: str, ocr_config: dict | None
) -> str:
    """Analyse pictures anchored on one Excel sheet.

    Example:
        >>> _xlsx_sheet_images(b"not-zip", "Sheet1", None)
        ''
    """
    if not _analyze_images_enabled(ocr_config):
        return ""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return ""
    try:
        workbook = load_workbook(io.BytesIO(data), data_only=True)
        worksheet = workbook[sheet]
    except Exception:
        return ""
    payloads: list[tuple[str, bytes]] = []
    for index, image in enumerate(getattr(worksheet, "_images", []) or []):
        try:
            payload = image._data()
        except Exception:
            continue
        if payload:
            payloads.append((f"{sheet}-{index + 1}.png", payload))
    if not payloads:
        return ""
    return _media_analysis_markdown(
        payloads,
        title_prefix=f"{sheet} image",
        ocr_config=ocr_config,
    )


def _payload_key(payload: bytes) -> tuple[int, bytes]:
    """Cheap identity for embedded image bytes.

    Example:
        >>> _payload_key(b"abc") == (3, b"abc")
        True
    """
    return (len(payload), payload[:64])


def _ocr_languages(ocr_config: dict | None) -> str:
    """Tesseract ``-l`` value (European languages + Arabic).

    Example:
        >>> "ara" in _ocr_languages(None)
        True
    """
    if ocr_config and ocr_config.get("languages"):
        return str(ocr_config["languages"])
    return "eng+fra+deu+spa+ita+nld+por+pol+ara"


def _analyze_images_enabled(ocr_config: dict | None) -> bool:
    """Return True when image analysis Markdown should be produced.

    Default is on (standalone images and PDF/Office pictures). Disable with
    ``ocr.analyze-images: false``.

    Example:
        >>> _analyze_images_enabled(None)
        True
        >>> _analyze_images_enabled({"analyze-images": False})
        False
    """
    if ocr_config is None:
        return True
    return bool(
        ocr_config.get(
            "analyze-images", ocr_config.get("analyze_images", True)
        )
    )


def _ocr_heavy(ocr_config: dict | None) -> bool:
    """Return True when OCR should run during image analysis.

    Default is on. Pass ``{"enabled": False}`` to skip Tesseract.

    Example:
        >>> _ocr_heavy(None)
        True
        >>> _ocr_heavy({"enabled": False})
        False
        >>> _ocr_heavy({})
        True
    """
    if ocr_config is None:
        return True
    return bool(ocr_config.get("enabled", True))


def _captions_enabled(ocr_config: dict | None) -> bool:
    """Return True when BLIP captions should run (default on).

    Follows ``captions`` / ``blip`` when set; otherwise follows OCR
    ``enabled`` (so ``--no-ocr`` also skips BLIP).

    Example:
        >>> _captions_enabled(None)
        True
        >>> _captions_enabled({"enabled": False})
        False
        >>> _captions_enabled({"enabled": True, "captions": False})
        False
    """
    if ocr_config is None:
        return True
    if "captions" in ocr_config:
        return bool(ocr_config["captions"])
    if "blip" in ocr_config:
        return bool(ocr_config["blip"])
    return bool(ocr_config.get("enabled", True))


def _image_analysis_markdown(
    data: bytes,
    *,
    title: str,
    source_name: str = "",
    ocr_config: dict | None = None,
    min_side: int | None = None,
) -> str:
    """Analyse one raster and return Markdown.

    Example:
        >>> from io import BytesIO
        >>> from PIL import Image
        >>> buf = BytesIO()
        >>> Image.new("RGB", (256, 256), "navy").save(buf, format="PNG")
        >>> md = _image_analysis_markdown(
        ...     buf.getvalue(), title="Image analysis", source_name="n.png",
        ...     ocr_config={"enabled": False},
        ... )
        >>> "## Image analysis" in md
        True
    """
    from thot.tasks.converters.image_analysis import (
        MIN_ANALYSIS_SIDE,
        image_bytes_to_markdown,
        raster_is_below_analysis_size,
    )

    side = MIN_ANALYSIS_SIDE if min_side is None else int(min_side)
    if raster_is_below_analysis_size(data, min_side=side):
        return ""
    return image_bytes_to_markdown(
        data,
        title=title,
        ocr_lang=_ocr_languages(ocr_config),
        source_name=source_name,
        heavy=_ocr_heavy(ocr_config),
        captions=_captions_enabled(ocr_config),
        min_side=side,
    )


def _embedded_image_limit(ocr_config: dict | None) -> int:
    """Max rasters to analyse inside one PDF/Office file.

    Example:
        >>> _embedded_image_limit(None)
        1024
        >>> _embedded_image_limit({"max-embedded-images": 8})
        8
    """
    if ocr_config and ocr_config.get("max-embedded-images") is not None:
        return max(1, int(ocr_config["max-embedded-images"]))
    return MAX_EMBEDDED_IMAGES


def _pdf_images_per_page(ocr_config: dict | None) -> int:
    """Max Image XObjects to analyse on one PDF page.

    Example:
        >>> _pdf_images_per_page(None)
        32
    """
    if ocr_config and ocr_config.get("max-pdf-images-per-page") is not None:
        return max(1, int(ocr_config["max-pdf-images-per-page"]))
    return MAX_PDF_IMAGES_PER_PAGE


def _pixmap_png_bytes(pix) -> bytes:
    """Encode a PyMuPDF pixmap as PNG bytes.

    Example:
        >>> callable(_pixmap_png_bytes)
        True
    """
    import fitz
    from PIL import Image as PILImage

    if pix.n - pix.alpha > 3:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    mode = "RGBA" if pix.alpha else "RGB"
    image = PILImage.frombytes(mode, (pix.width, pix.height), pix.samples)
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def _pdf_xref_image_bytes(document, xref: int) -> bytes | None:
    """Return original or RGB bytes for a PDF Image XObject.

    ``extract_image`` keeps JPEG/PNG (EXIF, OCR quality). Pixmap is the
    fallback when the stream cannot be decoded as a still image.

    Example:
        >>> callable(_pdf_xref_image_bytes)
        True
    """
    try:
        info = document.extract_image(xref)
        payload = info.get("image") if info else None
        if payload:
            return payload
    except Exception:
        pass
    try:
        import fitz

        pix = fitz.Pixmap(document, xref)
        if pix.width < 2 or pix.height < 2:
            return None
        return _pixmap_png_bytes(pix)
    except Exception:
        return None


def _payload_is_analysable_raster(
    data: bytes, *, min_side: int = EMBEDDED_MIN_SIDE
) -> bool:
    """Return True when bytes decode to a raster large enough to analyse.

    Example:
        >>> from io import BytesIO
        >>> from PIL import Image
        >>> buf = BytesIO()
        >>> Image.new("RGB", (80, 80), "navy").save(buf, format="PNG")
        >>> _payload_is_analysable_raster(buf.getvalue())
        True
        >>> buf = BytesIO()
        >>> Image.new("RGB", (16, 16), "red").save(buf, format="PNG")
        >>> _payload_is_analysable_raster(buf.getvalue())
        False
    """
    from thot.tasks.converters.image_analysis import is_below_analysis_size

    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if is_below_analysis_size(
                image.width, image.height, min_side=min_side
            ):
                return False
            return True
    except Exception:
        return False


def _zip_media_payloads(
    data: bytes, prefixes: tuple[str, ...]
) -> list[tuple[str, bytes]]:
    """Return ``(name, bytes)`` for media members under ``prefixes``.

    Example:
        >>> import io, zipfile
        >>> buf = io.BytesIO()
        >>> with zipfile.ZipFile(buf, "w") as zf:
        ...     zf.writestr("word/media/a.png", b"x")
        >>> _zip_media_payloads(buf.getvalue(), ("word/media/",))[0][0]
        'word/media/a.png'
    """
    out: list[tuple[str, bytes]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [
                name
                for name in archive.namelist()
                if not name.endswith("/")
                and any(name.startswith(prefix) for prefix in prefixes)
            ]
            for name in names:
                try:
                    out.append((name, archive.read(name)))
                except Exception:
                    continue
    except zipfile.BadZipFile:
        return []
    return out


def _media_analysis_markdown(
    payloads: list[tuple[str, bytes]],
    *,
    title_prefix: str,
    ocr_config: dict | None,
) -> str:
    """Analyse zip/Office media members into Markdown sections.

    Example:
        >>> _media_analysis_markdown([], title_prefix="x", ocr_config=None)
        ''
    """
    if not _analyze_images_enabled(ocr_config):
        return ""
    limit = _embedded_image_limit(ocr_config)
    sections: list[str] = []
    seen: set[int] = set()
    for index, (name, payload) in enumerate(payloads, start=1):
        if len(sections) >= limit:
            break
        digest = hash((len(payload), payload[:64]))
        if digest in seen:
            continue
        if not _payload_is_analysable_raster(payload):
            continue
        seen.add(digest)
        extra = _image_analysis_markdown(
            payload,
            title=f"{title_prefix} {index}: {Path(name).name}",
            ocr_config=ocr_config,
            min_side=EMBEDDED_MIN_SIDE,
        )
        if extra.strip():
            sections.append(extra)
    return "\n\n".join(sections)


def _extract_image(data: bytes, source: str, ocr_config: dict | None) -> str:
    """Analyse an image and emit Markdown (scene, EXIF, OCR, caption).

    Example:
        >>> from io import BytesIO
        >>> from PIL import Image
        >>> from thot.tasks.converters.UniversalConverter import _extract_image
        >>> buf = BytesIO()
        >>> Image.new("RGB", (256, 256), "navy").save(buf, format="PNG")
        >>> md = _extract_image(
        ...     buf.getvalue(), "navy.png", {"enabled": False}
        ... )
        >>> md.startswith("# navy.png")
        True
        >>> "## Image analysis" in md
        True
    """
    from thot.tasks.converters.image_analysis import (
        raster_is_below_analysis_size,
    )

    if raster_is_below_analysis_size(data):
        return ""
    if not _analyze_images_enabled(ocr_config):
        try:
            from PIL import Image

            image = Image.open(io.BytesIO(data))
            return (
                f"# {Path(source).name}\n\n"
                f"format: {image.format}  size: {image.width}x{image.height}\n"
            )
        except Exception:
            return _extract_unknown(data, source)
    return _image_analysis_markdown(
        data,
        title="Image analysis",
        source_name=Path(source).name or "image",
        ocr_config=ocr_config,
    )


def _pdf_block_text(block: dict) -> str:
    """Flatten a PyMuPDF text block to plain text.

    Example:
        >>> _pdf_block_text({"lines": [{"spans": [{"text": "Hi"}]}]})
        'Hi'
    """
    lines: list[str] = []
    for line in block.get("lines") or []:
        spans = [
            str(span.get("text") or "") for span in line.get("spans") or []
        ]
        joined = "".join(spans).strip()
        if joined:
            lines.append(joined)
    return "\n".join(lines).strip()


def _pdf_image_sections(data: bytes, ocr_config: dict | None) -> str:
    """Markdown for a PDF with figures spliced in reading order.

    Each page's text blocks and Image XObjects are sorted by position
    so analysis sits next to the surrounding prose, not at the end of
    the file.

    Example:
        >>> callable(_pdf_image_sections)
        True
    """
    try:
        import fitz
    except ImportError:
        return ""
    analyze = _analyze_images_enabled(ocr_config)
    max_per_page = _pdf_images_per_page(ocr_config)
    limit = _embedded_image_limit(ocr_config)
    render_budget = 0
    if ocr_config:
        render_budget = int(ocr_config.get("max-pdf-render-pages", 0) or 0)
    min_page_chars = 40
    if ocr_config:
        min_page_chars = int(
            ocr_config.get("min-page-text-chars", min_page_chars)
        )
    pages: list[str] = []
    analysed = 0
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return ""
    try:
        title = (document.metadata or {}).get("title") or ""
        if title:
            pages.append(f"# {title}")
        page_cap = document.page_count if render_budget <= 0 else render_budget
        for index, page in enumerate(document, start=1):
            items: list[tuple[float, float, int, str]] = []
            seq = 0
            page_images = 0
            seen_xrefs: set[int] = set()
            seen_payloads: set[tuple[int, bytes]] = set()
            for block in page.get_text("dict").get("blocks") or []:
                bbox = block.get("bbox")
                if not bbox:
                    continue
                y0, x0 = float(bbox[1]), float(bbox[0])
                if block.get("type") == 0:
                    text = _pdf_block_text(block)
                    if text:
                        items.append((y0, x0, seq, text))
                        seq += 1
                    continue
                if (
                    not analyze
                    or block.get("type") != 1
                    or analysed >= limit
                    or page_images >= max_per_page
                ):
                    continue
                xref = block.get("xref")
                payload = None
                if isinstance(block.get("image"), (bytes, bytearray)):
                    payload = bytes(block["image"])
                if xref is not None:
                    seen_xrefs.add(int(xref))
                    payload = payload or _pdf_xref_image_bytes(
                        document, int(xref)
                    )
                if not payload or not _payload_is_analysable_raster(payload):
                    continue
                extra = _image_analysis_markdown(
                    payload,
                    title=(
                        f"Embedded image {page_images + 1} " f"on page {index}"
                    ),
                    ocr_config=ocr_config,
                    min_side=EMBEDDED_MIN_SIDE,
                )
                if not extra.strip():
                    continue
                items.append((y0, x0, seq, extra.strip()))
                seq += 1
                page_images += 1
                analysed += 1
                seen_payloads.add(_payload_key(payload))
            if analyze and analysed < limit:
                for img in page.get_images(full=True):
                    if page_images >= max_per_page or analysed >= limit:
                        break
                    xref = int(img[0])
                    if xref in seen_xrefs:
                        continue
                    payload = _pdf_xref_image_bytes(document, xref)
                    if not payload or not _payload_is_analysable_raster(
                        payload
                    ):
                        continue
                    if _payload_key(payload) in seen_payloads:
                        continue
                    try:
                        rects = list(page.get_image_rects(xref) or [])
                    except Exception:
                        rects = []
                    if not rects:
                        rects = [fitz.Rect(0, 1e9, 1, 1e9 + 1)]
                    extra = _image_analysis_markdown(
                        payload,
                        title=(
                            f"Embedded image {page_images + 1} "
                            f"on page {index}"
                        ),
                        ocr_config=ocr_config,
                        min_side=EMBEDDED_MIN_SIDE,
                    )
                    if not extra.strip():
                        continue
                    seen_xrefs.add(xref)
                    seen_payloads.add(_payload_key(payload))
                    rect = rects[0]
                    items.append(
                        (
                            float(rect.y0),
                            float(rect.x0),
                            seq,
                            extra.strip(),
                        )
                    )
                    seq += 1
                    page_images += 1
                    analysed += 1
            items.sort(key=lambda row: (row[0], row[1], row[2]))
            body = "\n\n".join(part for _, _, _, part in items).strip()
            text_len = len((page.get_text("text") or "").strip())
            need_scan = (
                analyze
                and page_images == 0
                and text_len < min_page_chars
                and index <= page_cap
                and analysed < limit
            )
            if need_scan:
                try:
                    dpi = 200
                    if ocr_config:
                        dpi = int(ocr_config.get("render-dpi", 200) or 200)
                    pix = page.get_pixmap(dpi=min(max(dpi, 72), 300))
                    payload = _pixmap_png_bytes(pix)
                    extra = _image_analysis_markdown(
                        payload,
                        title=f"Full-page analysis (page {index})",
                        ocr_config=ocr_config,
                        min_side=EMBEDDED_MIN_SIDE,
                    )
                    if extra.strip():
                        body = (
                            (body + "\n\n" + extra.strip()).strip()
                            if body
                            else extra.strip()
                        )
                        analysed += 1
                except Exception:
                    pass
            if body:
                pages.append(body)
    finally:
        document.close()
    return "\n\n".join(pages)


def pdf_images_analysis_markdown(
    data: bytes, ocr_config: dict | None = None
) -> str:
    """Public wrapper: PDF markdown with figures in reading order.

    Used by MarkItDown so PDF pictures become searchable Markdown next
    to the surrounding page text.

    Example:
        >>> from thot.tasks.converters.UniversalConverter import (
        ...     pdf_images_analysis_markdown,
        ... )
        >>> pdf_images_analysis_markdown(b"%PDF", {"analyze-images": False})
        ''
    """
    if not _analyze_images_enabled(ocr_config):
        return ""
    return _pdf_image_sections(data, ocr_config)


def _extract_pdf(data: bytes, ocr_config: dict | None) -> str:
    """Extract PDF text with embedded / scanned images in reading order.

    Example:
        >>> callable(_extract_pdf)
        True
    """
    joined = _pdf_image_sections(data, ocr_config).strip()
    if not joined and _ocr_heavy(ocr_config):
        try:
            from thot.tasks.converters.PdfImageOcr import (
                build_pdf_content_with_ocr,
            )

            content, _info = build_pdf_content_with_ocr(
                data, ocr_config=ocr_config
            )
            joined = content or ""
        except Exception:
            joined = ""
    return _truncate(joined)


def _extract_zip(
    data: bytes,
    source: str,
    ocr_config: dict | None,
) -> str:
    """Unpack a ZIP and convert nested members (bounded).

    Example:
        >>> import io, zipfile
        >>> buf = io.BytesIO()
        >>> with zipfile.ZipFile(buf, "w") as zf:
        ...     zf.writestr("a.txt", "nested")
        >>> "nested" in _extract_zip(buf.getvalue(), "a.zip", None)
        True
    """
    chunks: list[str] = [f"# Archive {Path(source).name}"]
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [
                name
                for name in archive.namelist()
                if not name.endswith("/")
                and "__MACOSX" not in name.split("/")
                and not Path(name).name.startswith("._")
            ][:MAX_ARCHIVE_MEMBERS]
            for name in names:
                info = archive.getinfo(name)
                if info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
                    continue
                payload = archive.read(name)
                kind = classify_kind(name, payload)
                inner = extract_markdown(
                    payload, name, kind, ocr_config=ocr_config
                )
                if inner.strip():
                    chunks.append(f"## {name}\n\n{inner.strip()}")
    except zipfile.BadZipFile:
        return _extract_unknown(data, source)
    return _truncate("\n\n".join(chunks))


def _extract_unknown(data: bytes, source: str) -> str:
    """Fallback: printable preview of unrecognized bytes.

    Example:
        >>> "preview" in _extract_unknown(b"ABC", "x.bin").lower() or "ABC" in _extract_unknown(b"ABC", "x.bin")
        True
    """
    preview = "".join(
        chr(byte) if 32 <= byte < 127 else "." for byte in data[:400]
    )
    name = Path(source).name or "document"
    return f"# {name}\n\nUnrecognized binary. Preview:\n\n`{preview}`\n"


class UniversalConverter:
    """Convert arbitrary bytes to a T-KEIR document.

    Example:
        >>> from thot.tasks.converters.UniversalConverter import UniversalConverter
        >>> doc = UniversalConverter.convert(b"Hello", "file.txt", "raw")
        >>> doc["content"]
        ['Hello']
    """

    @staticmethod
    def managed_types() -> list[str]:
        """Return extra datatypes handled besides MarkItDown.

        Example:
            >>> "image" in UniversalConverter.managed_types()
            True
        """
        return sorted(UNIVERSAL_TYPES)

    @staticmethod
    def convert(
        data: bytes,
        source_doc_id: str,
        data_type: str,
        call_context=None,
        ocr_config=None,
    ) -> dict:
        """Convert bytes to T-KEIR JSON via universal extraction.

        Args:
            data: Raw document bytes.
            source_doc_id: Source identifier.
            data_type: Converter datatype or ``auto``.
            call_context: Unused logger context (API compatibility).
            ocr_config: Optional OCR settings.

        Returns:
            T-KEIR document dictionary (includes ``markdown`` extract).

        Example:
            >>> doc = UniversalConverter.convert(b"# T\\n\\nHi.", "a.md", "md")
            >>> doc["title"]
            'T'
            >>> "# T" in doc["markdown"]
            True
        """
        del call_context
        kind = (data_type or "auto").strip().lower()
        if kind in {"auto", ""}:
            kind = classify_kind(source_doc_id, data)
        markdown = extract_markdown(
            data, source_doc_id, kind, ocr_config=ocr_config
        )
        title, blocks, text_fmt = text_to_content(markdown or "")
        if not blocks and (markdown or "").strip():
            blocks = [markdown.strip()]
        return {
            "data_source": "converter-service",
            "source_doc_id": source_doc_id,
            "title": title,
            "content": blocks,
            "markdown": markdown or "",
            "kg": [],
            "error": False,
            "conversion-info": {
                "datatype": kind,
                "source-size-bytes": len(data),
                "converter": "universal",
                "text-format": text_fmt,
                "content-blocks": len(blocks),
            },
        }
