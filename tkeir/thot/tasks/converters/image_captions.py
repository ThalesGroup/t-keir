"""Title: Image captions

Optional BLIP captions for converter image / scan analysis. Loads weights
from ``resources/modeling/net/blip-image-captioning-base`` (setup/install),
never from the Hugging Face hub at runtime.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import io
import threading
from pathlib import Path
from typing import Any

from thot.core.TkeirPaths import blip_model_dir

_blip_bundle: tuple[Any, Any, Any] | None = None
_blip_failed = False
_blip_lock = threading.Lock()


def local_blip_available(dest: str | Path | None = None) -> bool:
    """Return True when the bundled BLIP checkpoint is on disk.

    Args:
        dest: Optional model directory override.

    Returns:
        True when ``config.json`` exists.

    Example:
        >>> from pathlib import Path
        >>> from thot.tasks.converters.image_captions import local_blip_available
        >>> local_blip_available(Path("/tmp/missing-blip-xyz"))
        False
    """
    return (Path(dest or blip_model_dir()) / "config.json").is_file()


def _ensure_blip():
    """Load BLIP from ``resources/modeling/net`` once per process.

    Example:
        >>> from thot.tasks.converters.image_captions import _ensure_blip
        >>> callable(_ensure_blip)
        True
    """
    global _blip_bundle, _blip_failed
    if _blip_failed:
        return None
    if _blip_bundle is not None:
        return _blip_bundle
    with _blip_lock:
        if _blip_failed:
            return None
        if _blip_bundle is not None:
            return _blip_bundle
        dest = Path(blip_model_dir())
        if not (dest / "config.json").is_file():
            _blip_failed = True
            return None
        try:
            import torch
            from transformers import (
                BlipForConditionalGeneration,
                BlipProcessor,
            )
        except Exception:
            _blip_failed = True
            return None
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        try:
            processor = BlipProcessor.from_pretrained(
                str(dest), local_files_only=True
            )
            model = BlipForConditionalGeneration.from_pretrained(
                str(dest), local_files_only=True
            )
            model.to(device)
            model.eval()
            _blip_bundle = (model, processor, device)
            return _blip_bundle
        except Exception:
            _blip_failed = True
            return None


def caption_pil_image(image) -> tuple[str, str]:
    """Caption a PIL image with local BLIP.

    Args:
        image: ``PIL.Image.Image``.

    Returns:
        ``(caption, engine)`` or ``("", "")`` when BLIP is unavailable.

    Example:
        >>> from thot.tasks.converters.image_captions import caption_pil_image
        >>> callable(caption_pil_image)
        True
    """
    bundle = _ensure_blip()
    if bundle is None:
        return "", ""
    try:
        rgb = image.convert("RGB")
    except Exception:
        return "", ""
    rgb.thumbnail((512, 512))
    model, processor, device = bundle
    import torch

    with _blip_lock:
        inputs = processor(rgb, return_tensors="pt").to(device)
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=40)
        text = processor.decode(out[0], skip_special_tokens=True).strip()
    return text, "blip-base"


def caption_image_bytes(data: bytes) -> str:
    """Return a short BLIP caption, or empty when the model is unavailable.

    Args:
        data: Image file bytes.

    Returns:
        Caption text, or ``""``.

    Example:
        >>> from thot.tasks.converters.image_captions import caption_image_bytes
        >>> caption_image_bytes(b"not-an-image") == ""
        True
    """
    if not data:
        return ""
    try:
        from PIL import Image
    except ImportError:
        return ""
    try:
        image = Image.open(io.BytesIO(data))
    except Exception:
        return ""
    text, _engine = caption_pil_image(image)
    return text
