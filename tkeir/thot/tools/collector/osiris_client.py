"""Title: Osiris HTTP client — pull live buckets for collector /feed.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from typing import Any

import httpx


async def fetch_json(
    base_url: str,
    path: str,
    *,
    timeout_s: float = 12.0,
) -> dict[str, Any] | list[Any] | None:
    """
    GET JSON from Osiris; return ``None`` on failure.

        Example:
            >>> True
            True
    """
    url = f"{base_url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(
            timeout=timeout_s, follow_redirects=True
        ) as client:
            res = await client.get(url, headers={"Accept": "application/json"})
            if res.status_code >= 400:
                return None
            data = res.json()
            return data if isinstance(data, (dict, list)) else None
    except Exception:  # noqa: BLE001
        return None


async def collect_osiris_buckets(
    osiris_base_url: str,
    *,
    timeout_s: float = 12.0,
) -> dict[str, Any]:
    """
    Pull forge-able Osiris API buckets into one mapping (worldwide coverage).

        Example:
            >>> True
            True
    """
    base = osiris_base_url.rstrip("/")
    paths = {
        "news": "/api/news",
        "gdelt": "/api/gdelt",
        "fires": "/api/fires",
        "weather": "/api/weather",
        "malware": "/api/malware",
        "cyber": "/api/cyber-attacks",
        "maritime": "/api/maritime",
        "earthquakes": "/api/earthquakes",
        "gdelt_events": "/api/gdelt-events?limit=400",
        "conflicts": "/api/conflicts",
    }
    out: dict[str, Any] = {}
    import asyncio

    async def one(key: str, path: str) -> tuple[str, Any]:
        return key, await fetch_json(base, path, timeout_s=timeout_s)

    rows = await asyncio.gather(*[one(k, p) for k, p in paths.items()])
    by_key = dict(rows)

    news = by_key.get("news")
    if isinstance(news, dict) and news.get("news"):
        out["news"] = news["news"]
    gdelt = by_key.get("gdelt")
    if isinstance(gdelt, dict) and gdelt.get("events"):
        out["gdelt"] = gdelt["events"]
    ge = by_key.get("gdelt_events")
    if isinstance(ge, dict) and ge.get("events"):
        out["gdelt_events"] = ge["events"]
    fires = by_key.get("fires")
    if isinstance(fires, dict) and fires.get("fires"):
        out["fires"] = fires["fires"]
    weather = by_key.get("weather")
    if isinstance(weather, dict) and weather.get("events"):
        out["weather_events"] = weather["events"]
    malware = by_key.get("malware")
    if isinstance(malware, dict) and malware.get("threats"):
        out["malware_threats"] = malware["threats"]
    cyber = by_key.get("cyber")
    if isinstance(cyber, dict) and cyber.get("attacks"):
        out["cyber_attacks"] = cyber["attacks"]
    maritime = by_key.get("maritime")
    if isinstance(maritime, dict) and maritime.get("chokepoints"):
        out["maritime_chokepoints"] = maritime["chokepoints"]
    eq = by_key.get("earthquakes")
    if isinstance(eq, dict) and eq.get("earthquakes"):
        out["earthquakes"] = eq["earthquakes"]
    elif isinstance(eq, list):
        out["earthquakes"] = eq

    # Optional conflict feed (ignore 404s via None).
    conflicts = by_key.get("conflicts")
    if isinstance(conflicts, dict):
        for field in ("zones", "conflicts", "events"):
            rows_list = conflicts.get(field)
            if isinstance(rows_list, list) and rows_list:
                out.setdefault("conflict_zones", [])
                if isinstance(out["conflict_zones"], list):
                    out["conflict_zones"].extend(
                        [x for x in rows_list if isinstance(x, dict)]
                    )
                break
    return out
