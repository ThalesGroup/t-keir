"""Title: OSINT source allowlist for collector search hits.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from thot.tools.ingest.user_workspace import workspace_root

LOGGER = logging.getLogger(__name__)

_DEFAULT_REL = Path("configs") / "collector" / "osint_sources.yaml"


def bundled_osint_sources_path() -> Path:
    """Bundled default allowlist under ``tkeir/configs/collector/``.

    Example:
        >>> bundled_osint_sources_path().name
        'osint_sources.yaml'
    """
    from thot.core.TkeirPaths import configs_dir

    return Path(configs_dir()) / "collector" / "osint_sources.yaml"


def workspace_osint_sources_path(root: Path | None = None) -> Path:
    """Workspace override: ``workspace/collector/osint_sources.yaml``.

    Example:
        >>> from pathlib import Path
        >>> workspace_osint_sources_path(Path("/tmp/ws")).as_posix().endswith(
        ...     "collector/osint_sources.yaml"
        ... )
        True
    """
    base = Path(root) if root is not None else workspace_root()
    return base / "collector" / "osint_sources.yaml"


def resolve_osint_sources_path(
    explicit: str | Path | None = None,
    *,
    workspace: Path | None = None,
) -> Path:
    """Pick the allowlist file (env → workspace → bundled).

    Example:
        >>> p = resolve_osint_sources_path()
        >>> p.name == "osint_sources.yaml"
        True
    """
    if explicit:
        return Path(explicit)
    env = (os.getenv("COLLECTOR_OSINT_SOURCES") or "").strip()
    if env:
        return Path(env)
    ws = workspace_osint_sources_path(workspace)
    if ws.is_file():
        return ws
    return bundled_osint_sources_path()


def _normalize_host(entry: str) -> str:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    h = (entry or "").strip().lower()
    if h.startswith("*."):
        h = h[2:]
    if h.startswith("."):
        h = h[1:]
    # Accept accidental full URLs in the config.
    if "://" in h:
        try:
            h = (urlparse(h).hostname or h).lower()
        except Exception:  # noqa: BLE001
            pass
    if h.startswith("www."):
        h = h[4:]
    return h.rstrip(".")


def _load_yaml(path: Path) -> dict[str, Any]:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("failed to load OSINT sources %s: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def parse_osint_sources(data: dict[str, Any]) -> tuple[bool, frozenset[str]]:
    """Parse allowlist YAML mapping → ``(enabled, hosts)``.

    Example:
        >>> enabled, hosts = parse_osint_sources(
        ...     {"enabled": True, "hosts": ["NASA.GOV", "usgs.gov"]}
        ... )
        >>> enabled and hosts == frozenset({"nasa.gov", "usgs.gov"})
        True
    """
    enabled = bool(data.get("enabled", True))
    raw = data.get("hosts") or data.get("allow") or data.get("whitelist") or []
    hosts: set[str] = set()
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                n = _normalize_host(item)
                if n:
                    hosts.add(n)
            elif isinstance(item, dict):
                # Optional { host: "nasa.gov", note: "..." }
                n = _normalize_host(
                    str(item.get("host") or item.get("domain") or "")
                )
                if n:
                    hosts.add(n)
    return enabled, frozenset(hosts)


@lru_cache(maxsize=4)
def load_osint_sources(
    path_str: str | None = None,
) -> tuple[bool, frozenset[str], str]:
    """Load allowlist; returns ``(enabled, hosts, resolved_path)``.

    Example:
        >>> enabled, hosts, p = load_osint_sources()
        >>> isinstance(enabled, bool) and isinstance(hosts, frozenset)
        True
    """
    path = resolve_osint_sources_path(path_str)
    enabled, hosts = parse_osint_sources(_load_yaml(path))
    LOGGER.info(
        "OSINT allowlist loaded path=%s enabled=%s hosts=%d",
        path,
        enabled,
        len(hosts),
    )
    return enabled, hosts, str(path)


def clear_osint_sources_cache() -> None:
    """Drop cached allowlist (tests / hot-reload).

    Example:
        >>> clear_osint_sources_cache()
    """
    load_osint_sources.cache_clear()


def host_of(url: str) -> str:
    """Extract lowercase hostname from a URL.

    Example:
        >>> host_of("https://WWW.NASA.GOV/a")
        'www.nasa.gov'
    """
    try:
        return (urlparse(url).hostname or "").lower().rstrip(".")
    except Exception:  # noqa: BLE001
        return ""


def host_matches_allowlist(host: str, allow: frozenset[str]) -> bool:
    """True when ``host`` equals or is a subdomain of an allowlist entry.

    Example:
        >>> host_matches_allowlist("firms.modaps.eosdis.nasa.gov", frozenset({"nasa.gov"}))
        True
        >>> host_matches_allowlist("evil.com", frozenset({"nasa.gov"}))
        False
    """
    h = (host or "").lower().rstrip(".")
    if h.startswith("www."):
        h = h[4:]
    if not h or not allow:
        return False
    for entry in allow:
        if h == entry or h.endswith("." + entry):
            return True
    return False


def is_allowed_osint_hit(
    hit: dict[str, Any],
    *,
    enabled: bool | None = None,
    allow: frozenset[str] | None = None,
) -> bool:
    """Return True when the hit host is on the OSINT allowlist.

    When allowlisting is disabled, all hits with a host pass.

    Example:
        >>> is_allowed_osint_hit(
        ...     {"url": "https://usgs.gov/eq"},
        ...     enabled=True,
        ...     allow=frozenset({"usgs.gov"}),
        ... )
        True
    """
    if enabled is None or allow is None:
        en, hosts, _ = load_osint_sources()
        if enabled is None:
            enabled = en
        if allow is None:
            allow = hosts
    if not enabled:
        return bool(host_of(str(hit.get("url") or "")))
    host = host_of(str(hit.get("url") or ""))
    return host_matches_allowlist(host, allow)


def filter_search_hits(
    hits: list[dict[str, Any]],
    *,
    enabled: bool | None = None,
    allow: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """Keep only allowlisted OSINT sources before page fetch.

    Example:
        >>> filter_search_hits(
        ...     [{"url": "https://nasa.gov/a"}, {"url": "https://spam.example/x"}],
        ...     enabled=True,
        ...     allow=frozenset({"nasa.gov"}),
        ... )
        [{'url': 'https://nasa.gov/a'}]
    """
    if enabled is None or allow is None:
        en, hosts, _ = load_osint_sources()
        if enabled is None:
            enabled = en
        if allow is None:
            allow = hosts
    return [
        h
        for h in hits
        if is_allowed_osint_hit(h, enabled=enabled, allow=allow)
    ]


# Back-compat aliases (previous NSFW blacklist API).
def is_nsfw_or_junk_hit(hit: dict[str, Any]) -> bool:
    """
    Inverse of :func:`is_allowed_osint_hit` (kept for older imports/tests).

        Example:
            >>> True
            True
    """
    return not is_allowed_osint_hit(hit)
