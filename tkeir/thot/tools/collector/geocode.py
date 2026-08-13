"""Title: Reverse-geocode lat/lng → city/region/country for forge queries.

Uses Nominatim with an on-disk cache under the workspace. Adult/junk filtering
stays on the OSINT allowlist — place names only improve query locality.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

import httpx

from thot.tools.ingest.user_workspace import workspace_root

LOGGER = logging.getLogger(__name__)

_LOCK = threading.Lock()
_MEMORY: dict[str, str] = {}


def _cache_path(workspace: Path | None = None) -> Path:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    base = Path(workspace) if workspace is not None else workspace_root()
    return base / "collector" / "geocode_cache.json"


def _load_disk(path: Path) -> dict[str, str]:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return (
            {str(k): str(v) for k, v in raw.items()}
            if isinstance(raw, dict)
            else {}
        )
    except Exception:  # noqa: BLE001
        return {}


def _save_disk(path: Path, data: dict[str, str]) -> None:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("geocode cache write failed: %s", exc)


def _key(lat: float, lng: float) -> str:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    # ~1 km grid — enough for city/region labels.
    return f"{lat:.2f},{lng:.2f}"


def format_place_label(address: dict[str, Any]) -> str:
    """
    Build a short ``city, region, country`` string from Nominatim address.

        Example:
            >>> True
            True
    """
    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or address.get("county")
        or ""
    )
    region = address.get("state") or address.get("region") or ""
    country = address.get("country") or ""
    parts = [str(p).strip() for p in (city, region, country) if str(p).strip()]
    # Prefer country always; drop duplicate tokens.
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        k = p.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return ", ".join(out[:3])


def reverse_geocode(
    lat: float,
    lng: float,
    *,
    url: str = "https://nominatim.openstreetmap.org/reverse",
    timeout_s: float = 8.0,
    user_agent: str = "tkeir-collector/2.0",
    workspace: Path | None = None,
    use_cache: bool = True,
) -> str:
    """
    Return ``city, region, country`` for ``lat/lng`` (empty on failure).

        Example:
            >>> True
            True
    """
    key = _key(lat, lng)
    if use_cache and key in _MEMORY:
        return _MEMORY[key]
    path = _cache_path(workspace)
    if use_cache:
        with _LOCK:
            disk = _load_disk(path)
            if key in disk:
                _MEMORY[key] = disk[key]
                return disk[key]

    place = ""
    try:
        params = {
            "lat": f"{lat:.5f}",
            "lon": f"{lng:.5f}",
            "format": "json",
            "zoom": "10",
            "addressdetails": "1",
        }
        headers = {
            "User-Agent": user_agent,
            "Accept": "application/json",
            "Accept-Language": "en",
        }
        with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
            res = client.get(url, params=params, headers=headers)
            if res.status_code < 400:
                data = res.json()
                if isinstance(data, dict):
                    addr = data.get("address") or {}
                    if isinstance(addr, dict):
                        place = format_place_label(addr)
                    if not place:
                        place = (
                            str(data.get("display_name") or "")
                            .split(",")[0]
                            .strip()
                        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("reverse geocode failed %.2f,%.2f: %s", lat, lng, exc)

    if use_cache:
        with _LOCK:
            _MEMORY[key] = place
            disk = _load_disk(path)
            disk[key] = place
            _save_disk(path, disk)
    return place


def place_from_coords(
    coords: list[float] | tuple[float, ...] | None,
    *,
    forge_geocode: dict[str, Any] | None = None,
    user_agent: str = "tkeir-collector/2.0",
    workspace: Path | None = None,
) -> str:
    """
    Convenience: coords ``[lat, lng]`` → place label using forge.yaml geocode.

        Example:
            >>> True
            True
    """
    if not coords or len(coords) < 2:
        return ""
    try:
        lat = float(coords[0])
        lng = float(coords[1])
    except (TypeError, ValueError):
        return ""
    cfg = forge_geocode or {}
    if cfg.get("enabled") is False:
        return ""
    return reverse_geocode(
        lat,
        lng,
        url=str(
            cfg.get("url") or "https://nominatim.openstreetmap.org/reverse"
        ),
        timeout_s=float(cfg.get("timeout_s") or 8),
        user_agent=user_agent,
        workspace=workspace,
        use_cache=bool(cfg.get("cache", True)),
    )
