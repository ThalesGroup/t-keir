"""Title: Load collector forge YAML (topic boost, NLP forge, save, geocode).

Adult / junk filtering uses the OSINT host allowlist — not query exclusions.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from thot.tools.ingest.user_workspace import workspace_root

LOGGER = logging.getLogger(__name__)

_DEFAULT_BOOST = {
    "fires": "wildfire",
    "earthquakes": "earthquake",
    "weather": "weather alert",
    "gdelt": "disaster",
    "gdelt_events": "news",
    "news": "news",
    "malware": "malware",
    "cyber": "cyber attack",
    "maritime": "maritime",
    "conflict": "conflict",
}


@dataclass(frozen=True)
class NlpForgeSettings:
    """NLP forge knobs from forge.yaml ``nlp_forge`` block."""

    enabled: bool = True
    max_seeds: int = 40
    max_queries_per_seed: int = 3
    max_queries_total: int = 64
    fetch_timeout_s: float = 20.0
    max_chars: int = 8000
    use_svo: bool = True
    use_keywords: bool = True
    require_title_or_snippet: bool = True


@dataclass(frozen=True)
class GeocodeSettings:
    """Reverse-geocode settings for place tokens."""

    enabled: bool = True
    url: str = "https://nominatim.openstreetmap.org/reverse"
    timeout_s: float = 8.0
    cache: bool = True


@dataclass(frozen=True)
class ForgeConfig:
    """Loaded forge configuration."""

    path: Path
    save_queries: bool = True
    # Empty by default — do not append -porn style exclusions to queries.
    exclude: str = ""
    default_boost: str = "news"
    topic_boost: dict[str, str] = field(
        default_factory=lambda: dict(_DEFAULT_BOOST)
    )
    nlp: NlpForgeSettings = field(default_factory=NlpForgeSettings)
    geocode: GeocodeSettings = field(default_factory=GeocodeSettings)


def bundled_forge_config_path() -> Path:
    """
    Bundled ``configs/collector/forge.yaml``.

        Example:
            >>> True
            True
    """
    from thot.core.TkeirPaths import configs_dir

    return Path(configs_dir()) / "collector" / "forge.yaml"


def workspace_forge_config_path(root: Path | None = None) -> Path:
    """
    Workspace override ``workspace/collector/forge.yaml``.

        Example:
            >>> True
            True
    """
    base = Path(root) if root is not None else workspace_root()
    return base / "collector" / "forge.yaml"


def resolve_forge_config_path(
    path_str: str | None = None,
    *,
    workspace: Path | None = None,
) -> Path:
    """
    Resolve forge YAML path (env → workspace → bundled).

        Example:
            >>> True
            True
    """
    env = (path_str or os.getenv("COLLECTOR_FORGE_CONFIG") or "").strip()
    if env:
        return Path(env).expanduser()
    ws = workspace_forge_config_path(workspace)
    if ws.is_file():
        return ws
    return bundled_forge_config_path()


def _load_yaml(path: Path) -> dict[str, Any]:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    if not path.is_file():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return raw if isinstance(raw, dict) else {}
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("failed to load forge config %s: %s", path, exc)
        return {}


def _parse_nlp(raw: Any) -> NlpForgeSettings:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    if not isinstance(raw, dict):
        return NlpForgeSettings()
    return NlpForgeSettings(
        enabled=bool(raw.get("enabled", True)),
        max_seeds=max(1, int(raw.get("max_seeds", 40))),
        max_queries_per_seed=max(1, int(raw.get("max_queries_per_seed", 3))),
        max_queries_total=max(1, int(raw.get("max_queries_total", 64))),
        fetch_timeout_s=float(raw.get("fetch_timeout_s", 20)),
        max_chars=max(500, int(raw.get("max_chars", 8000))),
        use_svo=bool(raw.get("use_svo", True)),
        use_keywords=bool(raw.get("use_keywords", True)),
        require_title_or_snippet=bool(
            raw.get("require_title_or_snippet", True)
        ),
    )


def _parse_geocode(raw: Any) -> GeocodeSettings:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    if not isinstance(raw, dict):
        return GeocodeSettings()
    return GeocodeSettings(
        enabled=bool(raw.get("enabled", True)),
        url=str(
            raw.get("url") or "https://nominatim.openstreetmap.org/reverse"
        ).strip(),
        timeout_s=float(raw.get("timeout_s", 8)),
        cache=bool(raw.get("cache", True)),
    )


def parse_forge_config(data: dict[str, Any], *, path: Path) -> ForgeConfig:
    """
    Parse forge.yaml mapping into :class:`ForgeConfig`.

        Example:
            >>> True
            True
    """
    boost_raw = data.get("topic_boost") or {}
    boost = dict(_DEFAULT_BOOST)
    if isinstance(boost_raw, dict):
        for key, val in boost_raw.items():
            if key and val:
                boost[str(key)] = str(val)
    # Explicit empty string disables exclusions (preferred).
    exclude = str(data.get("exclude") if "exclude" in data else "").strip()
    save = data.get("save_queries")
    if save is None:
        save = True
    return ForgeConfig(
        path=path,
        save_queries=bool(save),
        exclude=exclude,
        default_boost=str(data.get("default_boost") or "news").strip()
        or "news",
        topic_boost=boost,
        nlp=_parse_nlp(data.get("nlp_forge")),
        geocode=_parse_geocode(data.get("geocode")),
    )


@lru_cache(maxsize=4)
def load_forge_config(path_str: str | None = None) -> ForgeConfig:
    """
    Load and cache forge configuration.

        Example:
            >>> True
            True
    """
    path = resolve_forge_config_path(path_str)
    return parse_forge_config(_load_yaml(path), path=path)


def clear_forge_config_cache() -> None:
    """
    Drop cached forge config (tests / hot reload).

        Example:
            >>> True
            True
    """
    load_forge_config.cache_clear()


def ensure_workspace_forge_config(workspace: Path | None = None) -> Path:
    """
    Copy bundled forge.yaml into workspace if missing.

        Example:
            >>> True
            True
    """
    ws = workspace_forge_config_path(workspace)
    if ws.is_file():
        return ws
    bundled = bundled_forge_config_path()
    if bundled.is_file():
        ws.parent.mkdir(parents=True, exist_ok=True)
        ws.write_text(bundled.read_text(encoding="utf-8"), encoding="utf-8")
        clear_forge_config_cache()
    return ws
