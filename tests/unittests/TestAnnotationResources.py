"""Title: Test Annotation Resources

Automated tests for T-KEIR (unit / functional).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import thot.tools.annotation.AnnotationResources as annotation_resources_mod
from thot.tools.annotation.AnnotationResources import AnnotationResources


def test_download_skips_when_local_file_exists(tmp_path, monkeypatch):
    dest = tmp_path / "cities5000.txt"
    dest.write_text("keep-me\n", encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise AssertionError("existing gazetteer must not be re-downloaded")

    monkeypatch.setattr(annotation_resources_mod.requests, "get", _boom)
    AnnotationResources._download_list_resource(
        {
            "path": "cities5000.txt",
            "download": {"url": "http://127.0.0.1:9/missing.zip"},
        },
        str(tmp_path),
    )
    assert dest.read_text(encoding="utf-8") == "keep-me\n"


def test_download_noop_without_download_block(tmp_path):
    AnnotationResources._download_list_resource({}, str(tmp_path))
    assert list(tmp_path.iterdir()) == []
