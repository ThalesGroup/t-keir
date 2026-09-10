"""Title: Install converter models

Download Tesseract traineddata and the BLIP captioning checkpoint into
``tkeir/resources/modeling/`` (same layout as spaCy and BGE-M3).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import urllib.request
from pathlib import Path

from thot.core.TkeirPaths import blip_model_dir, net_models_dir, tessdata_dir

LOGGER = logging.getLogger(__name__)

TESSDATA_FAST_BASE = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/"
OCR_TESSDATA_LANGS = (
    "eng",
    "fra",
    "deu",
    "spa",
    "ita",
    "nld",
    "por",
    "pol",
    "ara",
    "osd",
)
BLIP_HF_ID = "Salesforce/blip-image-captioning-base"


def tessdata_ready(
    dest_root: str | Path | None = None,
    languages: tuple[str, ...] = OCR_TESSDATA_LANGS,
) -> bool:
    """Return True when every requested ``*.traineddata`` file exists.

    Args:
        dest_root: Tessdata directory (default ``tessdata_dir()``).
        languages: ISO Tesseract language codes.

    Returns:
        True when all language files are present.

    Example:
        >>> from pathlib import Path
        >>> from thot.tools.install_converter_models import tessdata_ready
        >>> tessdata_ready(Path("/tmp/missing-tessdata-xyz"), ("eng",))
        False
    """
    root = Path(dest_root or tessdata_dir())
    return all(
        (root / (lang + ".traineddata")).is_file() for lang in languages
    )


def local_blip_ready(dest: str | Path | None = None) -> bool:
    """Return True when a local BLIP checkpoint can be loaded.

    Args:
        dest: Model directory (default ``blip_model_dir()``).

    Returns:
        True when ``config.json`` exists under ``dest``.

    Example:
        >>> from pathlib import Path
        >>> from thot.tools.install_converter_models import local_blip_ready
        >>> local_blip_ready(Path("/tmp/missing-blip-xyz"))
        False
    """
    return (Path(dest or blip_model_dir()) / "config.json").is_file()


def _download_file(url: str, dest: Path) -> None:
    """Fetch ``url`` into ``dest`` (parent directories created).

    Example:
        >>> callable(_download_file)
        True
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(dest)


def install_tessdata(
    *,
    dest_root: str | Path | None = None,
    languages: tuple[str, ...] = OCR_TESSDATA_LANGS,
    force: bool = False,
) -> Path:
    """Download tessdata_fast language packs into ``resources/modeling/tesseract``.

    Args:
        dest_root: Destination directory.
        languages: Tesseract language codes to fetch.
        force: Re-download files that already exist.

    Returns:
        Destination directory.

    Example:
        >>> from thot.tools.install_converter_models import install_tessdata
        >>> callable(install_tessdata)
        True
    """
    root = Path(dest_root or tessdata_dir())
    root.mkdir(parents=True, exist_ok=True)
    for lang in languages:
        dest = root / (lang + ".traineddata")
        if dest.is_file() and not force:
            LOGGER.info("tessdata %s already present — skip", dest.name)
            continue
        url = TESSDATA_FAST_BASE + lang + ".traineddata"
        LOGGER.info("Downloading %s → %s", url, dest)
        _download_file(url, dest)
    if not tessdata_ready(root, languages):
        missing = [
            lang
            for lang in languages
            if not (root / (lang + ".traineddata")).is_file()
        ]
        raise RuntimeError(
            "tessdata download incomplete: " + ", ".join(missing)
        )
    return root


def install_blip(*, force: bool = False) -> str:
    """Download BLIP-base into ``resources/modeling/net/blip-image-captioning-base``.

    Args:
        force: Re-download even when ``config.json`` is present.

    Returns:
        Absolute path to the local model directory.

    Example:
        >>> from thot.core.TkeirPaths import blip_model_dir
        >>> from thot.tools.install_converter_models import install_blip
        >>> callable(install_blip)
        True
    """
    dest = Path(blip_model_dir())
    if not force and local_blip_ready(dest):
        LOGGER.info("BLIP already present at %s — skip", dest)
        return str(dest)
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "huggingface_hub is required to download BLIP. "
            "Install project deps with: make install"
        ) from exc
    Path(net_models_dir()).mkdir(parents=True, exist_ok=True)
    download_cache = Path(net_models_dir()) / ".download_cache"
    download_cache.mkdir(parents=True, exist_ok=True)
    if force and dest.exists():
        LOGGER.info("Removing existing BLIP at %s …", dest)
        shutil.rmtree(dest)
    LOGGER.info("Downloading %s → %s …", BLIP_HF_ID, dest)
    snapshot_download(
        repo_id=BLIP_HF_ID,
        local_dir=str(dest),
        cache_dir=str(download_cache),
    )
    if download_cache.exists():
        shutil.rmtree(download_cache, ignore_errors=True)
    if not local_blip_ready(dest):
        raise RuntimeError(
            "Download finished but config.json missing under " + str(dest)
        )
    LOGGER.info("BLIP ready at %s", dest)
    return str(dest)


def install_converter_models(
    *,
    tessdata: bool = True,
    blip: bool = True,
    force: bool = False,
) -> None:
    """Install converter OCR + caption models into ``resources/modeling``.

    Args:
        tessdata: Download Tesseract language packs.
        blip: Download the BLIP captioning checkpoint.
        force: Re-download even when artifacts exist.

    Example:
        >>> from thot.tools.install_converter_models import install_converter_models
        >>> callable(install_converter_models)
        True
    """
    if tessdata:
        install_tessdata(force=force)
    if blip:
        install_blip(force=force)


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m thot.tools.install_converter_models``.

    Example:
        >>> from thot.tools.install_converter_models import main
        >>> callable(main)
        True
    """
    parser = argparse.ArgumentParser(
        description=(
            "Download Tesseract tessdata and BLIP into "
            "tkeir/resources/modeling (not the Hugging Face hub cache)."
        )
    )
    parser.add_argument(
        "--tessdata-only",
        action="store_true",
        help="Only download *.traineddata language packs",
    )
    parser.add_argument(
        "--blip-only",
        action="store_true",
        help="Only download BLIP-base captions",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when files are already present",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging",
    )
    args = parser.parse_args(argv)
    from thot.core.StructuredLogging import configure_text_logging

    configure_text_logging(
        level=logging.DEBUG if args.verbose else logging.INFO,
        force=True,
    )
    force = args.force or os.environ.get("FORCE_CONVERTER_MODELS") == "1"
    want_tessdata = not args.blip_only
    want_blip = not args.tessdata_only
    if args.tessdata_only and args.blip_only:
        want_tessdata = True
        want_blip = True
    install_converter_models(
        tessdata=want_tessdata,
        blip=want_blip,
        force=force,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
