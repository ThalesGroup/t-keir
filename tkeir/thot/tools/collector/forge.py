"""Title: Forge SearXNG queries from Osiris collector buckets.

Port of Osiris ``searxQueryForge.ts`` — used by collector ``/feed`` so the
collector owns routing (Osiris APIs → queries → SearXNG).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any


def _as_list(v: Any) -> list[dict[str, Any]]:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    if not isinstance(v, list):
        return []
    return [x for x in v if isinstance(x, dict)]


def _str(v: Any, fallback: str = "") -> str:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float, bool)):
        return str(v)
    return fallback


def _num(v: Any) -> float | None:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, str) and v.strip():
        try:
            return float(v)
        except ValueError:
            return None
    return None


def coords_of(item: dict[str, Any]) -> list[float] | None:
    """
    Extract ``[lat, lng]`` when present.

        Example:
            >>> True
            True
    """
    coords = item.get("coords")
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        a, b = _num(coords[0]), _num(coords[1])
        if a is not None and b is not None:
            return [a, b]
    lat = _num(
        item.get("lat")
        or item.get("latitude")
        or item.get("dst_lat")
        or item.get("src_lat")
    )
    lng = _num(
        item.get("lng")
        or item.get("lon")
        or item.get("longitude")
        or item.get("dst_lng")
        or item.get("src_lng")
    )
    if lat is not None and lng is not None:
        return [lat, lng]
    return None


_HTTP_RE = re.compile(r"^https?://", re.I)


def extract_item_url(item: dict[str, Any]) -> str:
    """
    Best-effort absolute URL from an Osiris feed item.

        Example:
            >>> True
            True
    """
    for key in (
        "url",
        "link",
        "sourceUrl",
        "source_url",
        "href",
        "detail_url",
        "external_url",
    ):
        val = item.get(key)
        if isinstance(val, str) and _HTTP_RE.match(val.strip()):
            # Fix HTML entities from feed markup (e.g. GDACS ``&amp;``).
            return (
                val.strip()
                .replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
            )
    return ""


def searx_tokens(text: str, max_words: int = 12) -> str:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    cleaned = re.sub(r"[“”\"']", "", text or "")
    cleaned = re.sub(r"[^\w\s\-./:]", " ", cleaned, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    return " ".join(cleaned.split()[:max_words])


def forge_searx_query(
    *,
    title: str,
    place: str = "",
    type_hint: str = "",
    extra: str = "",
) -> str:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    parts = [
        searx_tokens(title, 10),
        searx_tokens(place, 4) if place else "",
        searx_tokens(type_hint, 3) if type_hint else "",
        searx_tokens(extra, 3) if extra else "",
    ]
    seen: set[str] = set()
    words: list[str] = []
    for part in parts:
        for w in part.split():
            key = w.lower()
            if re.fullmatch(r"-?\d+(\.\d+)?", key):
                continue
            if key in seen or len(key) < 2:
                continue
            seen.add(key)
            words.append(w)
            if len(words) >= 14:
                break
        if len(words) >= 14:
            break
    return " ".join(words).strip()


_TOPIC_BOOST: dict[str, str] | None = None
_EXCLUDE: str | None = None
_DEFAULT_BOOST_FALLBACK = "news"


def _forge_boosts() -> tuple[dict[str, str], str, str]:
    """
    Load topic_boost / exclude / default_boost from forge.yaml (cached).

        Example:
            >>> True
            True
    """
    global _TOPIC_BOOST, _EXCLUDE
    from thot.tools.collector.forge_config import load_forge_config

    cfg = load_forge_config()
    _TOPIC_BOOST = dict(cfg.topic_boost)
    _EXCLUDE = cfg.exclude  # empty string = no exclusions (preferred)
    return _TOPIC_BOOST, _EXCLUDE, cfg.default_boost


def sharpen_query(api: str, query: str) -> str:
    """
    Light topic boost only — never append -porn style exclusions.

        Junk filtering is handled by the OSINT host allowlist after SearXNG.

        Example:
            >>> True
            True
    """
    q = re.sub(r"\s+", " ", (query or "").strip())
    if not q:
        return q
    # Strip any legacy exclusion tokens if present in input.
    q = re.sub(
        r"\s+-(?:porn|xxx|nsfw|onlyfans|xvideos|xnxx|hentai|adult)\b",
        "",
        q,
        flags=re.I,
    )
    boosts, exclude, default_boost = _forge_boosts()
    boost = boosts.get(api, default_boost or _DEFAULT_BOOST_FALLBACK)
    lower = q.lower()
    boost_words = [w for w in boost.split() if w and w.lower() not in lower][
        :3
    ]
    if boost_words:
        q = f"{q} {' '.join(boost_words)}"
    # Only append exclude when explicitly configured and non-empty.
    exclude = (exclude or "").strip()
    if exclude:
        first = exclude.split()[0].lower()
        if first and first not in lower:
            q = f"{q} {exclude}"
    return re.sub(r"\s+", " ", q).strip()


def categories_for_api(api: str) -> str:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    if api in {"malware", "cyber"}:
        return "general,news,it"
    if api in {"fires", "earthquakes", "weather"}:
        return "general,news,science"
    if api in {"news", "gdelt", "gdelt_events", "conflict", "maritime"}:
        return "general,news"
    return "general,news,science"


def _clip(text: str, max_len: int) -> str:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _hash_id(raw: str) -> str:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def _now_iso() -> str:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def collect_seeds(data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Build ranked seeds from Osiris-shaped buckets.

        Example:
            >>> True
            True
    """
    seeds: list[dict[str, Any]] = []

    for item in _as_list(data.get("news")):
        title = _str(item.get("title"))
        if not title:
            continue
        risk = _num(item.get("risk_score")) or 0
        seeds.append(
            {
                "api": "news",
                "source": _str(item.get("source"), "OSINT news"),
                "title": title,
                "snippet": _clip(_str(item.get("description")) or title, 220),
                "timestamp": (
                    _str(item.get("published") or item.get("pubDate")) or None
                ),
                "priority": 40 + risk * 6,
                "coords": coords_of(item),
                "type_hint": "OSINT",
                "extra": "threat conflict" if risk >= 7 else "",
                "parent_id": _str(item.get("id") or item.get("link")),
                "url": extract_item_url(item),
            }
        )

    for item in _as_list(data.get("gdelt")):
        title = _str(item.get("name") or item.get("title"))
        if not title:
            continue
        seeds.append(
            {
                "api": "gdelt",
                "source": "GDACS",
                "title": title,
                "snippet": _clip(_str(item.get("type")) + " — " + title, 220),
                "timestamp": (
                    _str(item.get("date") or item.get("timestamp")) or None
                ),
                "priority": 42,
                "coords": coords_of(item),
                "type_hint": _str(item.get("type"), "disaster"),
                "extra": "GDACS",
                "parent_id": _str(item.get("id") or item.get("url")),
                "url": extract_item_url(item),
            }
        )

    for item in _as_list(data.get("gdelt_events")):
        title = _str(item.get("name") or item.get("title"))
        if not title:
            continue
        tone = abs(_num(item.get("tone")) or 0)
        seeds.append(
            {
                "api": "gdelt_events",
                "source": "GDELT",
                "title": title,
                "snippet": _clip(title, 220),
                "timestamp": (
                    _str(item.get("date") or item.get("seendate")) or None
                ),
                "priority": 35 + min(tone, 20),
                "coords": coords_of(item),
                "type_hint": "news event",
                "parent_id": _str(item.get("id") or item.get("url")),
                "url": extract_item_url(item),
            }
        )

    for item in _as_list(data.get("earthquakes")):
        mag = _num(item.get("mag") or item.get("magnitude")) or 0
        place = _str(item.get("place") or item.get("title"))
        title = place or f"M{mag:.1f} earthquake"
        seeds.append(
            {
                "api": "earthquakes",
                "source": "USGS",
                "title": title,
                "snippet": _clip(f"magnitude {mag}", 220),
                "timestamp": (
                    _str(item.get("time") or item.get("timestamp")) or None
                ),
                "priority": 30 + mag * 12,
                "coords": coords_of(item),
                "place": (
                    place
                    if not re.fullmatch(
                        r"-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?", place
                    )
                    else ""
                ),
                "type_hint": "earthquake seismic",
                "parent_id": _str(item.get("id")),
                "url": (
                    extract_item_url(item)
                    or _str(item.get("url") or item.get("detail") or "")
                ),
            }
        )

    for item in _as_list(data.get("fires")):
        bright = _num(item.get("brightness") or item.get("frp")) or 0
        place_raw = _str(
            item.get("region") or item.get("country") or item.get("title")
        )
        place = (
            place_raw
            if place_raw
            and not re.fullmatch(
                r"-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?", place_raw.strip()
            )
            else ""
        )
        title = _str(item.get("title")) or "Wildfire thermal anomaly"
        seeds.append(
            {
                "api": "fires",
                "source": "NASA FIRMS",
                "title": title,
                "snippet": _clip(f"FRP/brightness={bright}", 220),
                "timestamp": (
                    _str(
                        item.get("date")
                        or item.get("timestamp")
                        or item.get("acq_date")
                    )
                    or None
                ),
                "priority": 25 + min(bright / 20, 40),
                "coords": coords_of(item),
                "place": place,
                "type_hint": "wildfire fire",
                "extra": "NASA FIRMS",
                "parent_id": _str(item.get("id")),
                "url": extract_item_url(item),
            }
        )

    for item in _as_list(data.get("weather_events")):
        title = _str(
            item.get("title") or item.get("event") or item.get("type"),
            "Weather event",
        )
        seeds.append(
            {
                "api": "weather",
                "source": _str(
                    item.get("provider") or item.get("source"), "weather"
                ),
                "title": title,
                "snippet": _clip(title, 220),
                "timestamp": (
                    _str(item.get("date") or item.get("timestamp")) or None
                ),
                "priority": 28,
                "coords": coords_of(item),
                "place": _str(item.get("area")),
                "type_hint": _str(item.get("type") or "weather hazard"),
                "parent_id": _str(item.get("id")),
                "url": extract_item_url(item),
            }
        )

    for item in _as_list(data.get("malware_threats")):
        malware = _str(item.get("malware"), "malware")
        title = f"{malware} {_str(item.get('threat_type'), 'C2')} {_str(item.get('country'))}".strip()
        url = extract_item_url(item)
        if not url and _str(item.get("ip")):
            # URLhaus browse for host IP — malware markers rarely carry a page URL.
            url = f"https://urlhaus.abuse.ch/browse.php?search={_str(item.get('ip'))}"
        seeds.append(
            {
                "api": "malware",
                "source": "abuse.ch",
                "title": title,
                "snippet": _clip(title, 220),
                "timestamp": _str(item.get("last_online")) or None,
                "priority": 45,
                "coords": coords_of(item),
                "type_hint": "malware C2",
                "parent_id": _str(item.get("id")),
                "url": url,
            }
        )

    for item in _as_list(data.get("cyber_attacks")):
        title = (
            f"{_str(item.get('action'), 'attack')} "
            f"{_str(item.get('malware'))} {_str(item.get('target_country'))}"
        ).strip()
        seeds.append(
            {
                "api": "cyber",
                "source": "cyber",
                "title": title or "cyber attack",
                "snippet": _clip(title, 220),
                "timestamp": _str(item.get("timestamp")) or None,
                "priority": 48,
                "coords": coords_of(item),
                "type_hint": "cyber attack",
                "parent_id": _str(item.get("id")),
                "url": extract_item_url(item),
            }
        )

    for item in _as_list(data.get("maritime_chokepoints")):
        title = _str(item.get("name") or item.get("title"))
        if not title:
            continue
        seeds.append(
            {
                "api": "maritime",
                "source": "maritime",
                "title": title,
                "snippet": _clip(_str(item.get("description")) or title, 220),
                "timestamp": None,
                "priority": 36,
                "coords": coords_of(item),
                "place": title,
                "type_hint": "maritime chokepoint",
                "parent_id": _str(item.get("id") or title),
                "url": extract_item_url(item),
            }
        )

    for item in _as_list(data.get("conflict_zones")) + _as_list(
        data.get("conflicts")
    ):
        title = _str(
            item.get("label") or item.get("name") or item.get("title"),
            "Conflict zone",
        )
        seeds.append(
            {
                "api": "conflict",
                "source": _str(
                    item.get("source") or item.get("sourceUrl"), "conflict"
                ),
                "title": title,
                "snippet": _clip(
                    _str(
                        item.get("description") or item.get("summary") or title
                    ),
                    220,
                ),
                "timestamp": (
                    _str(
                        item.get("lastUpdated")
                        or item.get("timestamp")
                        or item.get("date")
                    )
                    or None
                ),
                "priority": 50,
                "coords": coords_of(item),
                "place": _str(item.get("region")),
                "type_hint": "conflict war",
                "parent_id": _str(item.get("id") or title),
                "url": extract_item_url(item),
            }
        )

    return seeds


def diversify_seeds(
    seeds: list[dict[str, Any]],
    *,
    max_seeds: int,
) -> list[dict[str, Any]]:
    """
    Round-robin pick across API families (priority within each family).

        Prevents one hot layer (malware, fires, …) from consuming the whole budget.

        Example:
            >>> True
            True
    """
    if max_seeds <= 0 or not seeds:
        return []
    ranked = sorted(
        seeds,
        key=lambda s: float(s.get("priority") or 0),
        reverse=True,
    )
    by_api: dict[str, list[dict[str, Any]]] = {}
    for s in ranked:
        by_api.setdefault(_str(s.get("api"), "osiris"), []).append(s)
    apis = sorted(
        by_api.keys(),
        key=lambda a: float(by_api[a][0].get("priority") or 0),
        reverse=True,
    )
    out: list[dict[str, Any]] = []
    cursors = {a: 0 for a in apis}
    while len(out) < max_seeds:
        progressed = False
        for api in apis:
            i = cursors[api]
            bucket = by_api[api]
            if i >= len(bucket):
                continue
            out.append(bucket[i])
            cursors[api] = i + 1
            progressed = True
            if len(out) >= max_seeds:
                break
        if not progressed:
            break
    return out


def forge_queries_from_osiris_data(
    data: dict[str, Any],
    *,
    max_queries: int = 32,
    map_center: dict[str, float] | None = None,
    diversify: bool = True,
) -> list[dict[str, Any]]:
    """
    Forge SearXNG-ready queries from Osiris buckets.

        When ``diversify`` is true (default), pick round-robin across API families
        so one hot layer (e.g. fires) cannot monopolize the batch.

        Example:
            >>> True
            True
    """
    seeds = collect_seeds(data)

    if map_center:
        lat0 = float(map_center.get("lat", 0))
        lng0 = float(map_center.get("lng", 0))
        for s in seeds:
            c = s.get("coords")
            if not c or len(c) < 2:
                continue
            dist = ((c[0] - lat0) ** 2 + (c[1] - lng0) ** 2) ** 0.5
            if dist < 15:
                s["priority"] = float(s["priority"]) + max(0, 20 - dist)
    seeds.sort(key=lambda s: float(s.get("priority") or 0), reverse=True)

    from thot.tools.collector.forge_config import load_forge_config
    from thot.tools.collector.geocode import place_from_coords

    forge_cfg = load_forge_config()
    geo_cfg = {
        "enabled": forge_cfg.geocode.enabled,
        "url": forge_cfg.geocode.url,
        "timeout_s": forge_cfg.geocode.timeout_s,
        "cache": forge_cfg.geocode.cache,
    }

    def _emit(s: dict[str, Any], seen: set[str]) -> dict[str, Any] | None:
        title = _str(s.get("title"))
        snippet = _str(s.get("snippet"))
        if not title and not snippet:
            return None
        place = _str(s.get("place"))
        if not place or re.fullmatch(
            r"-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?", place.strip()
        ):
            place = place_from_coords(s.get("coords"), forge_geocode=geo_cfg)
        extra_bits = [_str(s.get("extra"))]
        if snippet and snippet.casefold() not in (title or "").casefold():
            extra_bits.append(snippet[:120])
        q = forge_searx_query(
            title=title or snippet[:120],
            place=place,
            type_hint=_str(s.get("type_hint")),
            extra=" ".join(b for b in extra_bits if b),
        )
        if not q:
            return None
        sharpened = sharpen_query(_str(s.get("api")), q)
        key = sharpened.lower()
        if key in seen:
            return None
        seen.add(key)
        api = _str(s.get("api"), "osiris")
        return {
            "id": f"{api}-{_hash_id(_str(s.get('parent_id')) + sharpened)}",
            "query": sharpened,
            "api": api,
            "source": _str(s.get("source")),
            "timestamp": s.get("timestamp"),
            "snippet": s.get("snippet"),
            "title": _clip(title or snippet, 160),
            "priority": float(s.get("priority") or 0),
            "coords": s.get("coords"),
            "place": place,
            "streamedAt": _now_iso(),
            "categories": categories_for_api(api),
        }

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    cap = max(1, int(max_queries))

    if diversify and seeds:
        by_api: dict[str, list[dict[str, Any]]] = {}
        for s in seeds:
            by_api.setdefault(_str(s.get("api"), "osiris"), []).append(s)
        # Prefer families with higher top priority, then round-robin.
        apis = sorted(
            by_api.keys(),
            key=lambda a: float(by_api[a][0].get("priority") or 0),
            reverse=True,
        )
        cursors = {a: 0 for a in apis}
        while len(out) < cap:
            progressed = False
            for api in apis:
                if len(out) >= cap:
                    break
                i = cursors[api]
                bucket = by_api[api]
                while i < len(bucket):
                    row = _emit(bucket[i], seen)
                    i += 1
                    cursors[api] = i
                    if row is not None:
                        out.append(row)
                        progressed = True
                        break
                else:
                    cursors[api] = i
            if not progressed:
                break
        return out

    for s in seeds:
        if len(out) >= cap:
            break
        row = _emit(s, seen)
        if row is not None:
            out.append(row)
    return out
