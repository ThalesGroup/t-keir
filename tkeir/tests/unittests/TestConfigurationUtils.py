"""Title: Configuration Utils

Tests for YAML/JSON configuration loading helpers.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from thot.core.ConfigurationUtils import (
    _parse_configuration_text,
    load_configuration,
    load_json_configuration,
    resolve_config_path,
)
from thot.core.TkeirPaths import configs_dir


def test_load_configuration_parses_yaml():
    cfg = load_configuration(StringIO("logger:\n  logging-level: info\n"))
    assert cfg["logger"]["logging-level"] == "info"


def test_load_configuration_parses_json_compat():
    cfg = load_json_configuration(
        StringIO('{"logger": {"logging-level": "debug"}}')
    )
    assert cfg["logger"]["logging-level"] == "debug"


def test_parse_json_by_source_name():
    data = _parse_configuration_text(
        '{"logger": {"logging-level": "warn"}}',
        source_name="logger.json",
    )
    assert data["logger"]["logging-level"] == "warn"


def test_parse_json_extension_uses_json_loader():
    data = _parse_configuration_text(
        '{"fallback": 1}', source_name="broken.json"
    )
    assert data == {"fallback": 1}


def test_parse_yaml_error_falls_back_to_json(monkeypatch):
    import yaml as yaml_mod

    def _boom(_text):
        raise yaml_mod.YAMLError("boom")

    monkeypatch.setattr("thot.core.ConfigurationUtils.yaml.safe_load", _boom)
    data = _parse_configuration_text('{"ok": true}', source_name="x.yaml")
    assert data == {"ok": True}


def test_parse_empty_yaml_becomes_empty_dict():
    assert _parse_configuration_text("") == {}
    assert _parse_configuration_text("null") == {}


def test_parse_non_mapping_raises():
    with pytest.raises(ValueError, match="mapping"):
        _parse_configuration_text("- item\n")


def test_resolve_config_path_prefers_yaml():
    path = resolve_config_path("pipeline.yaml", search_dir=configs_dir())
    assert path.endswith("pipeline.yaml")


def test_resolve_config_path_absolute(tmp_path: Path):
    cfg = tmp_path / "local.yaml"
    cfg.write_text("logger: {}\n", encoding="utf-8")
    assert resolve_config_path(str(cfg)) == str(cfg)


def test_resolve_config_path_without_extension(tmp_path: Path):
    cfg = tmp_path / "svc.yaml"
    cfg.write_text("logger: {}\n", encoding="utf-8")
    assert resolve_config_path("svc", search_dir=str(tmp_path)).endswith(
        "svc.yaml"
    )


def test_resolve_config_path_basename_in_search_dir(tmp_path: Path):
    nested = tmp_path / "nested"
    nested.mkdir()
    cfg = nested / "svc.yaml"
    cfg.write_text("logger: {}\n", encoding="utf-8")
    # path with directory prefix → also try basename under search_dir
    found = resolve_config_path("other/svc.yaml", search_dir=str(nested))
    assert found.endswith("svc.yaml")


def test_resolve_config_path_relative_without_search_dir(
    tmp_path: Path, monkeypatch
):
    cfg = tmp_path / "cwd.yaml"
    cfg.write_text("logger: {}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert resolve_config_path("cwd.yaml").endswith("cwd.yaml")


def test_resolve_config_path_missing_raises():
    with pytest.raises(FileNotFoundError):
        resolve_config_path(
            "does-not-exist-xyz.yaml", search_dir=configs_dir()
        )


def test_resolve_json_when_yaml_absent(tmp_path: Path):
    cfg = tmp_path / "legacy.json"
    cfg.write_text(json.dumps({"logger": {}}), encoding="utf-8")
    found = resolve_config_path("legacy.yaml", search_dir=str(tmp_path))
    assert found.endswith("legacy.json")
