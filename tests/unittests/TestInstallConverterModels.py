"""Title: Install converter models

Tests for tessdata / BLIP install helpers (no network).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from thot.tasks.converters.image_captions import (
    caption_image_bytes,
    local_blip_available,
)
from thot.tasks.converters.PdfImageOcr import tessdata_tesseract_config
from thot.tools.install_converter_models import (
    install_tessdata,
    local_blip_ready,
    main,
    tessdata_ready,
)


class TestInstallConverterModels:
    def test_tessdata_ready_false_when_missing(self, tmp_path: Path):
        assert tessdata_ready(tmp_path, ("eng",)) is False

    def test_install_tessdata_skips_existing(self, tmp_path: Path):
        dest = tmp_path / "eng.traineddata"
        dest.write_bytes(b"stub")
        with patch(
            "thot.tools.install_converter_models._download_file"
        ) as download:
            root = install_tessdata(
                dest_root=tmp_path, languages=("eng",), force=False
            )
        assert root == tmp_path
        download.assert_not_called()
        assert tessdata_ready(tmp_path, ("eng",)) is True

    def test_install_tessdata_force_redownloads(self, tmp_path: Path):
        (tmp_path / "eng.traineddata").write_bytes(b"old")

        def _write(_url: str, dest: Path) -> None:
            dest.write_bytes(b"new")

        with patch(
            "thot.tools.install_converter_models._download_file",
            side_effect=_write,
        ):
            install_tessdata(
                dest_root=tmp_path, languages=("eng",), force=True
            )
        assert (tmp_path / "eng.traineddata").read_bytes() == b"new"

    def test_local_blip_ready_false(self, tmp_path: Path):
        assert local_blip_ready(tmp_path) is False
        assert local_blip_available(tmp_path) is False

    def test_caption_without_model_is_empty(self):
        assert caption_image_bytes(b"not-an-image") == ""

    def test_tessdata_config_empty_without_files(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TKEIR_TESSDATA_DIR", str(tmp_path))
        assert tessdata_tesseract_config() == ""
        (tmp_path / "eng.traineddata").write_bytes(b"x")
        config = tessdata_tesseract_config()
        assert "--tessdata-dir" in config
        assert str(tmp_path) in config

    def test_cli_callable(self):
        assert callable(main)
