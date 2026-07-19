"""Extract text from images embedded in PDF documents."""

import base64
import os
from io import BytesIO

from thot.core.ThotLogger import ThotLogger

_OCR_PROMPT = (
    "Extract all readable text from this image. "
    "If it is a diagram or chart, describe labels, headings, and key visible text."
)


def _ocr_tesseract(image_bytes: bytes) -> str:
    """Run Tesseract OCR on image bytes.

    Args:
        image_bytes: PNG or other image payload.

    Returns:
        Stripped OCR text.

    Raises:
        RuntimeError: When pytesseract or pillow is not installed.

    Example:
        >>> isinstance(_ocr_tesseract, type(lambda: None))
        True
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError as error:
        raise RuntimeError(
            "pytesseract and pillow are required for tesseract OCR mode"
        ) from error

    image = Image.open(BytesIO(image_bytes))
    text = pytesseract.image_to_string(image)
    return text.strip()


def _ocr_llm(image_bytes: bytes, ocr_config: dict) -> str:
    """Run LLM vision OCR on image bytes.

    Args:
        image_bytes: PNG or other image payload.
        ocr_config: OCR settings with API key and model options.

    Returns:
        Stripped OCR text from the model response.

    Raises:
        RuntimeError: When the openai package or API key is missing.

    Example:
        >>> isinstance(_ocr_llm, type(lambda: None))
        True
    """
    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError(
            "openai package is required for llm OCR mode"
        ) from error

    api_key = ocr_config.get("llm-api-key") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY or converter ocr.llm-api-key is required"
        )

    client_kwargs = {"api_key": api_key}
    base_url = ocr_config.get("llm-base-url") or os.environ.get(
        "OPENAI_BASE_URL"
    )
    if base_url:
        client_kwargs["base_url"] = base_url

    model = ocr_config.get("llm-model") or os.environ.get(
        "TKEIR_OCR_LLM_MODEL", "gpt-4o"
    )
    client = OpenAI(**client_kwargs)
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": ocr_config.get("llm-prompt", _OCR_PROMPT),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64," + encoded
                        },
                    },
                ],
            }
        ],
    )
    return (response.choices[0].message.content or "").strip()


def _run_ocr(image_bytes: bytes, ocr_config: dict) -> str:
    """Dispatch OCR to the configured backend.

    Args:
        image_bytes: Image payload to recognize.
        ocr_config: OCR settings including ``mode``.

    Returns:
        OCR text from the selected backend.

    Example:
        >>> isinstance(_run_ocr, type(lambda: None))
        True
    """
    mode = (ocr_config.get("mode") or "tesseract").lower()
    if mode == "llm":
        return _ocr_llm(image_bytes, ocr_config)
    return _ocr_tesseract(image_bytes)


def _bbox_is_large_enough(bbox: tuple, ocr_config: dict) -> bool:
    """Return True when a bbox meets the minimum pixel threshold.

    Args:
        bbox: Bounding box as ``(x0, y0, x1, y1)``.
        ocr_config: OCR settings with ``min-image-pixels``.

    Returns:
        ``True`` when the bbox area is large enough to OCR.

    Example:
        >>> _bbox_is_large_enough((0, 0, 200, 200), {"min-image-pixels": 100})
        True
    """
    min_pixels = int(ocr_config.get("min-image-pixels", 10000))
    width = max(0.0, bbox[2] - bbox[0])
    height = max(0.0, bbox[3] - bbox[1])
    return width * height >= min_pixels


def _text_from_block(block: dict) -> str:
    """Flatten a PyMuPDF text block dict to plain text.

    Args:
        block: Text block dictionary from ``page.get_text("dict")``.

    Returns:
        Joined line text for the block.

    Example:
        >>> _text_from_block({"lines": [{"spans": [{"text": "Hi"}]}]})
        'Hi'
    """
    lines = []
    for line in block.get("lines", []):
        spans = []
        for span in line.get("spans", []):
            spans.append(span.get("text", ""))
        if spans:
            lines.append("".join(spans))
    return "\n".join(lines).strip()


def _ocr_image_region(
    page, bbox: tuple, ocr_config: dict, call_context=None
) -> str:
    """OCR a clipped PDF image region.

    Args:
        page: PyMuPDF page object.
        bbox: Region bounding box.
        ocr_config: OCR settings.
        call_context: Optional logger context.

    Returns:
        OCR text for the region, or an empty string on failure.

    Example:
        >>> isinstance(_ocr_image_region, type(lambda: None))
        True
    """
    try:
        import fitz
    except ImportError:
        return ""

    try:
        clip = fitz.Rect(bbox)
        render_dpi = int(ocr_config.get("render-dpi", 200))
        pixmap = page.get_pixmap(dpi=render_dpi, clip=clip)
        return _run_ocr(pixmap.tobytes("png"), ocr_config)
    except Exception as error:
        ThotLogger.warning(
            "PDF image OCR failed: " + str(error),
            context=call_context,
        )
        return ""


def _page_elements(
    page, page_number: int, ocr_config: dict, call_context=None, ocr_stats=None
) -> list:
    """Collect page text and OCR snippets in reading order.

    Args:
        page: PyMuPDF page object.
        page_number: One-based page index.
        ocr_config: OCR settings.
        call_context: Optional logger context.
        ocr_stats: Mutable OCR counters updated in place.

    Returns:
        Ordered text fragments for the page.

        Example:
            >>> "ocr_stats" in _page_elements.__code__.co_varnames
            True
    """
    elements = []
    min_page_text_chars = int(ocr_config.get("min-page-text-chars", 40))
    if ocr_stats is None:
        ocr_stats = {}

    for block in page.get_text("dict").get("blocks", []):
        bbox = block.get("bbox")
        if not bbox:
            continue
        y_pos = bbox[1]
        if block.get("type") == 0:
            text = _text_from_block(block)
            if text:
                elements.append((y_pos, text))
        elif block.get("type") == 1 and _bbox_is_large_enough(
            bbox, ocr_config
        ):
            ocr_text = _ocr_image_region(
                page, bbox, ocr_config, call_context=call_context
            )
            if ocr_text:
                ocr_stats["image-regions"] = (
                    ocr_stats.get("image-regions", 0) + 1
                )
                elements.append(
                    (
                        y_pos,
                        "[Image page " + str(page_number) + "]\n" + ocr_text,
                    )
                )

    elements.sort(key=lambda item: item[0])

    if not elements and len(page.get_text().strip()) < min_page_text_chars:
        try:
            render_dpi = int(ocr_config.get("render-dpi", 200))
            pixmap = page.get_pixmap(dpi=render_dpi)
            ocr_text = _run_ocr(pixmap.tobytes("png"), ocr_config)
        except Exception as error:
            ThotLogger.warning(
                "PDF page OCR failed on page "
                + str(page_number)
                + ": "
                + str(error),
                context=call_context,
            )
            ocr_text = ""
        if ocr_text:
            ocr_stats["scanned-pages"] = ocr_stats.get("scanned-pages", 0) + 1
            elements.append(
                (0, "[Scanned page " + str(page_number) + "]\n" + ocr_text)
            )

    return [text for _, text in elements]


def build_pdf_content_with_ocr(
    pdf_bytes: bytes, ocr_config: dict | None = None, call_context=None
) -> tuple[str, dict]:
    """Build PDF text with image OCR inserted in page reading order.

    Args:
        pdf_bytes: Raw PDF file bytes.
        ocr_config: OCR settings; disabled configs return empty content.
        call_context: Optional logger context.

    Returns:
        Tuple of joined page text and OCR statistics.

    Example:
        >>> content, stats = build_pdf_content_with_ocr(b"%PDF", {"enabled": False})
        >>> content
        ''
        >>> stats["enabled"]
        False
    """
    ocr_stats = {
        "enabled": bool(ocr_config and ocr_config.get("enabled")),
        "used": False,
        "mode": (ocr_config or {}).get("mode"),
        "image-regions": 0,
        "scanned-pages": 0,
    }
    if not ocr_config or not ocr_config.get("enabled"):
        return "", ocr_stats

    try:
        import fitz
    except ImportError:
        ThotLogger.warning(
            "PDF image OCR skipped: pymupdf is not installed",
            context=call_context,
        )
        return "", ocr_stats

    pages = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            parts = _page_elements(
                page,
                page_number,
                ocr_config,
                call_context=call_context,
                ocr_stats=ocr_stats,
            )
            if parts:
                pages.append("\n\n".join(parts))

    content = "\n\f\n".join(pages)
    ocr_stats["used"] = bool(
        ocr_stats["image-regions"] or ocr_stats["scanned-pages"]
    )
    return content, ocr_stats


def extract_pdf_image_text(
    pdf_bytes: bytes, ocr_config: dict | None = None, call_context=None
) -> list:
    """Return OCR snippets for embedded PDF images (legacy flat list).

    Args:
        pdf_bytes: Raw PDF file bytes.
        ocr_config: OCR settings; disabled configs return an empty list.
        call_context: Optional logger context.

    Returns:
        Flat list of image and scanned-page OCR snippets.

    Example:
        >>> extract_pdf_image_text(b"%PDF", {"enabled": False})
        []
    """
    if not ocr_config or not ocr_config.get("enabled"):
        return []

    try:
        import fitz
    except ImportError:
        ThotLogger.warning(
            "PDF image OCR skipped: pymupdf is not installed",
            context=call_context,
        )
        return []

    snippets = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        ocr_stats: dict[str, int | bool] = {}
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            for part in _page_elements(
                page,
                page_number,
                ocr_config,
                call_context=call_context,
                ocr_stats=ocr_stats,
            ):
                if part.startswith("[Image page") or part.startswith(
                    "[Scanned page"
                ):
                    snippets.append(part)

    return snippets
