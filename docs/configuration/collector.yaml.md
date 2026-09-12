# Collector YAML — field effects

The web collector (`tkeir-collector`, port **8096**) searches via SearXNG,
allowlists hosts, converts hits to Markdown, and optionally forges follow-up
queries. It does **not** run the NLP pipeline and does **not** write Vespa.

Resolve order for each file (first existing wins):

1. Absolute path in the matching env var  
2. `workspace/collector/<file>` (local override)  
3. `tkeir/configs/collector/<file>` (bundled default)

See [Web collector](../tools/collector.md).

---

## `osint_sources.yaml`

Env: `COLLECTOR_OSINT_SOURCES` (Osiris also honors `OSINT_SOURCES_PATH`).

| Field | Default | Effect |
|-------|---------|--------|
| `enabled` | `true` | `false` fetches **every** SearXNG hit (not recommended). `true` keeps only allowlisted hosts. |
| `hosts[]` | bundled OSINT list | Hostname **suffix** match: `nasa.gov` allows `firms.modaps.eosdis.nasa.gov`. Add a domain to collect it; remove one to drop it. No URL paths — host only. |

This file is the **reliability filter**. Do not put `-porn` style query
exclusions in `forge.yaml`; keep junk off the host list instead.

---

## `topics.yaml`

Maps the collector request field `topic` to a **business ontology dataset**
(and optional RDF paths) used when the operator later ingests collected
markdown.

| Field | Default | Effect |
|-------|---------|--------|
| `default_topic` | `osint` | Used when the API body omits `topic`. |
| `topics.<id>.description` | — | Documentation only. |
| `topics.<id>.business_ontology_dataset` | — | Folder name under `datasets/` (`osint`, `scifact`, …). Ingest/RAG `TKEIR_BUSINESS_ONTOLOGY_DATASET` should match for that corpus. |
| `topics.<id>.ontology_paths` | `[]` | Extra TTL/OWL paths for derive-from style enrichment of collected docs (when the ingest path consumes them). |
| `topics.<id>.by_language.<lang>.*` | optional | Overrides dataset/paths after page-language detection (`en`, `fr`, …). |

Workspace overlay (wins when present):

```text
workspace/collector/topics/<topic>/business_ontology.yaml
workspace/collector/topics/<topic>/ontologies/*.ttl
workspace/collector/topics/<topic>/<lang>/…
```

Adding a **new usecase** usually means a new `topics.<usecase>` row with
`business_ontology_dataset: <usecase>`. See [Create a usecase pack](../tools/usecase.md).

---

## `forge.yaml`

Env: `COLLECTOR_FORGE_CONFIG`.  
Turns Osiris / seed URLs and API families into diversified SearXNG queries.

| Field | Default | Effect |
|-------|---------|--------|
| `save_queries` | `true` | `true` writes forged strings under `workspace/collector/forged_queries/`. |
| `exclude` | `""` | Extra negative keywords appended to queries. Leave empty — spam exclusions hurt SearXNG ranking; use the host allowlist instead. |
| `default_boost` | `"news"` | Tokens added when the API family is unknown. |
| `topic_boost.<family>` | see file | Short cue per Osiris API family (`fires` → `wildfire`, …). Keep ≤ ~3 words. |
| `geocode.enabled` | `true` | Reverse-geocode seed coordinates to city/region tokens. `false` skips Nominatim (no place expansion). |
| `geocode.url` | OSM Nominatim | Reverse-geocode endpoint. Must send a descriptive User-Agent. |
| `geocode.timeout_s` | `8` | HTTP timeout per lookup. |
| `geocode.cache` | `true` | Persist results in `workspace/collector/geocode_cache.json`. |
| `nlp_forge.enabled` | `true` | Fetch seed URLs → markdown → NLP (SVO/keywords) → extra queries. `false` uses titles/snippets only. |
| `nlp_forge.max_seeds` | `40` | How many seed URLs to NLP. Higher → more API load. |
| `nlp_forge.max_queries_per_seed` | `3` | Cap forged queries from one seed. |
| `nlp_forge.max_queries_total` | `64` | Global cap per forge run. |
| `nlp_forge.fetch_timeout_s` | `12` | Per-seed fetch timeout. |
| `nlp_forge.max_chars` | `8000` | Truncate seed markdown before NLP. |
| `nlp_forge.use_svo` / `use_keywords` | `true` | Which NLP artefacts become query tokens. |
| `nlp_forge.require_title_or_snippet` | `true` | Always include seed title/snippet in forged queries when present. |

---

## Related

- Runtime: [Web collector](../tools/collector.md)  
- Ontology dataset ids: [Datasets](../tools/datasets.md) · [rag.yaml](rag.yaml.md)
