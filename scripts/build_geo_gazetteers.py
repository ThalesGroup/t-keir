#!/usr/bin/env python3
"""Expand tokenizer/any lakes, rivers, mountains, and regions gazetteers.

Merges the curated multilingual lists already in the repo with:

* Natural Earth 10m physical + geographic layers (public domain)
* GeoNames ``admin1CodesASCII`` first-order divisions (CC-BY 4.0)
* optional Wikidata labels for notable hydro / relief / regions (CC0)

Usage:
    python3 scripts/build_geo_gazetteers.py
    python3 scripts/build_geo_gazetteers.py --skip-wikidata --refresh
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANY_DIR = ROOT / "tkeir" / "resources" / "modeling" / "tokenizer" / "any"
CACHE_DIR = ROOT / "workspace" / "tmp" / "geo-gazetteer-cache"

USER_AGENT = (
    "T-KEIR-geo-gazetteers/1.0 "
    "(+https://github.com/ThalesGroup/t-keir)"
)
NE_BASES = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/",
    "https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@master/"
    "geojson/",
)
GEONAMES_ADMIN1 = (
    "https://download.geonames.org/export/dump/admin1CodesASCII.txt"
)
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

MIN_LEN = 3
MAX_LEN = 80
SHORT_ALLOW = {
    "ob",
    "po",
    "k2",
}

GENERIC = {
    "area",
    "bay",
    "berg",
    "canal",
    "cape",
    "channel",
    "creek",
    "desert",
    "fleuve",
    "gulf",
    "hill",
    "hills",
    "island",
    "islands",
    "lac",
    "lacs",
    "lake",
    "lakes",
    "meer",
    "mont",
    "monte",
    "mount",
    "mountain",
    "mountains",
    "n/a",
    "none",
    "null",
    "ocean",
    "oceans",
    "peak",
    "peaks",
    "plateau",
    "point",
    "province",
    "provinces",
    "range",
    "ranges",
    "region",
    "regions",
    "rio",
    "river",
    "rivers",
    "rivière",
    "riviere",
    "sea",
    "seas",
    "see",
    "state",
    "states",
    "strait",
    "unnamed",
    "valley",
    "valleys",
}

NAME_KEY_RE = re.compile(
    r"^name(_|$)|^namealt$|^nameascii$|^woe_name$|^wikiname$"
)
UNNAMED_RE = re.compile(r"(?i)^(unnamed|n/?a|none|null)(\b|$)")
CODE_RE = re.compile(r"^[A-Z0-9]{2,5}$")
LEADING_JUNK_RE = re.compile(r"^[\d\"“”«»(]")
EXPANDED_MARK = "# --- expanded from Natural Earth / GeoNames / Wikidata ---"
JUNK_SUBSTR = (
    "arrondissement",
    "special ward",
    "special wards",
    "tiefdruck",
    "dark side",
    "far side",
    "túlsó oldala",
    "sötét oldala",
    "távolabbi oldala",
)

NE_LAYERS = {
    "lakes": (
        "ne_10m_lakes.geojson",
        "ne_10m_lakes_europe.geojson",
        "ne_10m_lakes_north_america.geojson",
        "ne_10m_lakes_australia.geojson",
        "ne_10m_lakes_historic.geojson",
        "ne_10m_playas.geojson",
        "ne_10m_geography_marine_polys.geojson",
    ),
    "rivers": (
        "ne_10m_rivers_lake_centerlines.geojson",
        "ne_10m_rivers_europe.geojson",
        "ne_10m_rivers_north_america.geojson",
    ),
    "mountains": (
        "ne_10m_geography_regions_elevation_points.geojson",
        "ne_10m_geography_regions_polys.geojson",
    ),
    "regions": (
        "ne_10m_geography_regions_polys.geojson",
        "ne_10m_geography_regions_points.geojson",
        "ne_10m_geography_marine_polys.geojson",
    ),
}

# Physical-region feature classes from NE geography_regions_polys.
MOUNTAIN_REGION_HINTS = (
    "range",
    "mount",
    "mont",
    "alps",
    "andes",
    "himal",
    "sierra",
    "cordillera",
    "massif",
    "peak",
    "berg",
    "gebirge",
    "hills",
    "upland",
    "plateau",
    "highland",
    "volcano",
)

WIKIDATA_QUERIES = {
    "lakes": """
SELECT DISTINCT ?label WHERE {
  ?item wdt:P31/wdt:P279* wd:Q23397 ;
        wdt:P2046 ?area .
  FILTER(xsd:decimal(?area) > 80)
  ?sitelink schema:about ?item ;
            schema:isPartOf <https://en.wikipedia.org/> .
  { ?item rdfs:label ?label } UNION { ?item skos:altLabel ?label }
  FILTER(LANG(?label) IN (
    "en","fr","es","de","it","pt","nl","pl","ar","ru","zh","ja","tr",
    "sv","uk","el","hu","ro","cs","id","vi","ko","he","fa","hi"
  ))
}
LIMIT 12000
""",
    "rivers": """
SELECT DISTINCT ?label WHERE {
  ?item wdt:P31 wd:Q4022 ;
        wdt:P2043 ?length .
  FILTER(xsd:decimal(?length) > 120)
  { ?item rdfs:label ?label } UNION { ?item skos:altLabel ?label }
  FILTER(LANG(?label) IN (
    "en","fr","es","de","it","pt","nl","pl","ar","ru","zh","ja","tr",
    "sv","uk","el","hu","ro","cs","id","vi","ko","he","fa","hi"
  ))
}
LIMIT 12000
""",
    "mountains": """
SELECT DISTINCT ?label WHERE {
  {
    ?item wdt:P31 wd:Q46831 .
    ?sitelink schema:about ?item ;
              schema:isPartOf <https://en.wikipedia.org/> .
  } UNION {
    ?item wdt:P31 wd:Q8502 ;
          wdt:P2044 ?elev .
    FILTER(xsd:decimal(?elev) > 2500)
  }
  { ?item rdfs:label ?label } UNION { ?item skos:altLabel ?label }
  FILTER(LANG(?label) IN (
    "en","fr","es","de","it","pt","nl","pl","ar","ru","zh","ja","tr",
    "sv","uk","el","hu","ro","cs","id","vi","ko","he","fa","hi"
  ))
}
LIMIT 12000
""",
}

SEED_REGIONS = """
Maghreb
Levant
Mashriq
Sahel
Horn of Africa
West Africa
East Africa
Central Africa
Southern Africa
North Africa
Sub-Saharan Africa
Middle East
Near East
Far East
Central Asia
South Asia
Southeast Asia
East Asia
North Asia
Siberia
Anatolia
Asia Minor
Mesopotamia
Levantine
Caucasus
Transcaucasia
South Caucasus
North Caucasus
Balkans
Balkan Peninsula
Scandinavia
Nordic countries
Benelux
Iberia
Iberian Peninsula
British Isles
Low Countries
Baltic states
Baltics
Eastern Europe
Western Europe
Central Europe
Southern Europe
Northern Europe
Occitania
Occitanie
Brittany
Bretagne
Normandy
Normandie
Flanders
Vlaanderen
Flandre
Wallonia
Wallonie
Catalonia
Catalunya
Catalogne
Basque Country
Euskadi
Pays Basque
Galicia
Galiza
Andalusia
Andalucía
Andalousie
Castile
Castilla
Aragon
Aragón
Provence
Côte d'Azur
Cote d'Azur
Riviera
French Riviera
Côte d'Azur
Alsace
Lorraine
Burgundy
Bourgogne
Franche-Comté
Franche-Comte
Savoy
Savoie
Corsica
Corse
Sicily
Sicilia
Sicile
Sardinia
Sardegna
Sardaigne
Crete
Krētē
Crimea
Crimea Peninsula
Patagonia
Amazonia
Amazon Basin
Pampas
Altiplano
Gran Chaco
Pantanal
Cerrado
Caatinga
Guianas
The Guianas
Caribbean
West Indies
Antilles
Greater Antilles
Lesser Antilles
Mesoamerica
Central America
Andean
Andean region
New England
Mid-Atlantic
Midwest
American Midwest
Deep South
Pacific Northwest
Cascadia
Great Plains
Great Basin
Four Corners
Appalachia
Acadia
Acadie
Maritime provinces
Canadian Prairies
Canadian Shield
Nunavik
Nunatsiavut
Yukon
Outback
Top End
Nullarbor
Highveld
Karoo
Namib
Kalahari
Sahara
Sahelian
Sudan region
Maghreb
Fertile Crescent
Hejaz
Najd
Hadhramaut
Dhofar
Baluchistan
Balochistan
Punjab
Sindh
Kashmir
Jammu and Kashmir
Ladakh
Tibet
Xinjiang
Inner Mongolia
Manchuria
Dongbei
Jiangnan
Lingnan
Sichuan Basin
Yunnan
Indochina
Mainland Southeast Asia
Nusantara
Malay Archipelago
Melanesia
Micronesia
Polynesia
Oceania
Australasia
Transylvania
Wallachia
Moldavia
Dobruja
Thrace
Macedonia
Epirus
Peloponnese
Thessaly
Attica
Bohemia
Moravia
Silesia
Pomerania
Prussia
Saxony
Bavaria
Swabia
Franconia
Rhineland
Ruhr
Westphalia
Holstein
Jutland
Lapland
Karelia
Ingria
Tatarstan
Bashkortostan
Dagestan
Chechnya
Abkhazia
Ossetia
Adjara
Gilan
Mazandaran
Fars
Khuzestan
Kurdistan
Iraqi Kurdistan
Rojava
Upper Egypt
Lower Egypt
Nubia
Darfur
Kordofan
Ogaden
Tigray
Amhara
Oromia
Cabo Verde
Canary Islands
Azores
Madeira
Balearic Islands
Channel Islands
Faroe Islands
Svalbard
Greenland
""".strip()


def _norm_key(text: str) -> str:
    return " ".join(text.split()).casefold()


def usable_name(text: str | None, *, strict: bool = False) -> str | None:
    """Return a gazetteer surface form, or None when it should be skipped.

    ``strict`` applies to imported Natural Earth / GeoNames / Wikidata
    rows: drop 2–3 letter English tokens, ISO codes, and sentence-like
    labels. Curated seed lines stay on the looser path.
    """
    if not text or not isinstance(text, str):
        return None
    value = " ".join(text.split())
    if not value or value.startswith("#"):
        return None
    if UNNAMED_RE.match(value):
        return None
    folded = value.casefold()
    if folded in GENERIC:
        return None
    if len(value) < MIN_LEN and folded not in SHORT_ALLOW:
        return None
    if len(value) > MAX_LEN:
        return None
    if value.isdigit():
        return None
    if any(chunk in folded for chunk in JUNK_SUBSTR):
        return None
    if strict:
        if CODE_RE.match(value):
            return None
        if LEADING_JUNK_RE.match(value):
            return None
        if value.startswith(("'", "‘")) and not folded.startswith(
            ("'t ", "'s ", "‘t ", "‘s ")
        ):
            return None
        if len(value.split()) > 7:
            return None
        ascii_alpha = sum(ch.isascii() and ch.isalpha() for ch in value)
        if ascii_alpha and len(value) < 4 and folded not in SHORT_ALLOW:
            return None
        if value[:1].islower() and not value.startswith(("'", "‘")):
            return None
    return value


def load_existing(path: Path) -> list[str]:
    """Load curated names only (lines above the expanded-data marker)."""
    if not path.is_file():
        return []
    names: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip() == EXPANDED_MARK:
            break
        name = usable_name(raw, strict=False)
        if name:
            names.append(name)
    return names


class NameSet:
    """Insertion-ordered unique names keyed by casefold."""

    def __init__(self, initial: list[str] | None = None):
        self._order: list[str] = []
        self._keys: set[str] = set()
        if initial:
            self.extend(initial, strict=False)

    def add(self, text: str | None, *, strict: bool = False) -> bool:
        name = usable_name(text, strict=strict)
        if not name:
            return False
        key = _norm_key(name)
        if key in self._keys:
            return False
        self._keys.add(key)
        self._order.append(name)
        return True

    def extend(self, values, *, strict: bool = False) -> int:
        added = 0
        for value in values:
            if self.add(value, strict=strict):
                added += 1
        return added

    def __len__(self) -> int:
        return len(self._order)

    def existing_then_sorted_new(self, seed_count: int) -> list[str]:
        head = self._order[:seed_count]
        tail = sorted(self._order[seed_count:], key=lambda s: s.casefold())
        return head + tail


def http_get(url: str, timeout: int = 90) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def cached_bytes(url: str, cache_name: str, refresh: bool) -> bytes:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / cache_name
    if cache_path.is_file() and not refresh:
        return cache_path.read_bytes()
    payload = http_get(url)
    cache_path.write_bytes(payload)
    return payload


def fetch_ne_geojson(filename: str, refresh: bool) -> dict | None:
    last_error = None
    for base in NE_BASES:
        url = base + filename
        try:
            payload = cached_bytes(url, filename, refresh)
            return json.loads(payload.decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            continue
    print(f"  skip {filename}: {last_error}", file=sys.stderr)
    return None


def iter_property_names(props: dict):
    for key, value in props.items():
        if not NAME_KEY_RE.search(str(key).lower()):
            continue
        if isinstance(value, str):
            yield value
            if "|" in value:
                for part in value.split("|"):
                    yield part
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    yield item


def names_from_geojson(data: dict, *, mountain_filter: bool = False) -> list[str]:
    found: list[str] = []
    for feature in data.get("features") or []:
        props = feature.get("properties") or {}
        if not isinstance(props, dict):
            continue
        if mountain_filter:
            blob = " ".join(
                str(props.get(k) or "")
                for k in ("featurecla", "name", "name_en", "region", "comment")
            ).casefold()
            if not any(hint in blob for hint in MOUNTAIN_REGION_HINTS):
                # Keep elevation points even without a hint.
                if str(props.get("featurecla") or "").casefold() not in {
                    "mountain",
                    "range",
                    "peak",
                    "volcano",
                    "depression",
                    "geoarea",
                }:
                    continue
        found.extend(iter_property_names(props))
    return found


def fetch_geonames_admin1(refresh: bool) -> list[str]:
    payload = cached_bytes(GEONAMES_ADMIN1, "admin1CodesASCII.txt", refresh)
    names: list[str] = []
    reader = csv.reader(io.StringIO(payload.decode("utf-8")), delimiter="\t")
    for row in reader:
        if len(row) < 3:
            continue
        names.append(row[1])
        names.append(row[2])
    return names


def fetch_wikidata(kind: str) -> list[str]:
    query = WIKIDATA_QUERIES[kind]
    url = WIKIDATA_SPARQL + "?" + urllib.parse.urlencode(
        {"query": query, "format": "json"}
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/sparql-results+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=75) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"  wikidata {kind} skipped: {exc}", file=sys.stderr)
        return []
    labels: list[str] = []
    for row in payload.get("results", {}).get("bindings", []):
        value = (row.get("label") or {}).get("value")
        if value:
            labels.append(value)
    return labels


def write_list(path: Path, header: str, names: list[str], seed_count: int) -> None:
    lines = [line.rstrip() for line in header.strip().splitlines()]
    lines.append("")
    head = names[:seed_count]
    tail = names[seed_count:]
    lines.extend(head)
    if tail:
        lines.append("")
        lines.append(EXPANDED_MARK)
        lines.extend(tail)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"wrote {path.relative_to(ROOT)} "
        f"({len(head)} curated + {len(tail)} imported)"
    )


def build_kind(
    kind: str,
    existing_path: Path,
    header: str,
    extra_seeds: list[str],
    refresh: bool,
    skip_wikidata: bool,
) -> None:
    existing = load_existing(existing_path)
    names = NameSet(existing)
    names.extend(extra_seeds, strict=False)
    seed_count = len(names)
    print(f"{kind}: {seed_count} curated, fetching Natural Earth …")
    mountain_filter = kind == "mountains"
    for filename in NE_LAYERS.get(kind, ()):
        data = fetch_ne_geojson(filename, refresh)
        if not data:
            continue
        added = names.extend(
            names_from_geojson(data, mountain_filter=mountain_filter),
            strict=True,
        )
        print(f"  {filename}: +{added}")
    if kind == "regions":
        added = names.extend(fetch_geonames_admin1(refresh), strict=True)
        print(f"  geonames admin1: +{added}")
    if kind != "regions" and not skip_wikidata:
        print(f"  wikidata {kind} …")
        added = names.extend(fetch_wikidata(kind), strict=True)
        print(f"  wikidata {kind}: +{added}")
        time.sleep(1)
    write_list(
        existing_path,
        header,
        names.existing_then_sorted_new(seed_count),
        seed_count,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Expand tokenizer/any geo gazetteers from public map data."
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-download cached Natural Earth / GeoNames files.",
    )
    parser.add_argument(
        "--skip-wikidata",
        action="store_true",
        help="Do not query Wikidata (faster, English-heavy Natural Earth only).",
    )
    args = parser.parse_args()
    ANY_DIR.mkdir(parents=True, exist_ok=True)

    rebuild = "Rebuild: python3 scripts/build_geo_gazetteers.py"

    build_kind(
        "lakes",
        ANY_DIR / "lakes.txt",
        f"""# Lakes, inland seas, reservoirs, and oceans — language-agnostic MWE gazetteer.
# Curated native names + exonyms, then Natural Earth 10m and Wikidata notables.
# {rebuild}""",
        [],
        args.refresh,
        args.skip_wikidata,
    )
    build_kind(
        "rivers",
        ANY_DIR / "rivers.txt",
        f"""# World rivers — language-agnostic MWE gazetteer.
# Curated native names + exonyms, then Natural Earth 10m and Wikidata notables.
# {rebuild}""",
        [],
        args.refresh,
        args.skip_wikidata,
    )
    build_kind(
        "mountains",
        ANY_DIR / "mountains.txt",
        f"""# Peaks, ranges, and highlands — language-agnostic MWE gazetteer.
# Curated native names + exonyms, then Natural Earth 10m and Wikidata notables.
# {rebuild}""",
        [],
        args.refresh,
        args.skip_wikidata,
    )
    build_kind(
        "regions",
        ANY_DIR / "regions.txt",
        f"""# Geographic and first-order administrative regions — language-agnostic MWE gazetteer.
# Cultural regions, Natural Earth geography layers, and GeoNames admin1.
# {rebuild}""",
        SEED_REGIONS.splitlines(),
        args.refresh,
        args.skip_wikidata,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
