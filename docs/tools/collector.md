# Web collector (SearXNG → markdown documents)

The collector searches the open web via [SearXNG](https://docs.searxng.org/),
fetches each hit, converts the page to **well-formatted Markdown** (MarkItDown +
HTML noise stripping + YAML front matter), and **returns documents in the API
response**. It does **not** persist markdown to disk, does **not** run the NLP
pipeline, and does **not** attach ontologies.

Package: `tkeir/thot/tools/collector/` (`tkeir-collector` CLI).

## Prerequisites

```bash
make setup                 # includes: make pull-searxng
make searxng-up            # docker on :8888, volumes under workspace/searxng/
make collector             # API on :8096
make collector-query       # sample POST /collect (COLLECTOR_QUERY=…)
```

Or use `./start_services.sh` (starts `[SEARXNG]` then `[COLLECTOR]` after SPIRE).

## SearXNG volumes

```text
$(WORKSPACE)/searxng/config/   → /etc/searxng/     (settings.yml, JSON enabled)
$(WORKSPACE)/searxng/data/     → /var/cache/searxng/
```

Default settings are copied from `tkeir/resources/searxng/settings.yml` on first
pull/up (JSON search format must stay enabled for the collector). The template
keeps a curated `engines:` list (`duckduckgo`, `brave`, `bing`, `wikipedia`, …) via
`use_default_settings.engines.keep_only` (**wikidata** is excluded: its SPARQL
bootstrap often gets HTTP 403 from Docker IPs and fails engine init). To refresh
an existing workspace copy after editing the template:

```bash
cp tkeir/resources/searxng/settings.yml workspace/searxng/config/settings.yml
make searxng-up
```

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Liveness |
| `GET` | `/ready` | Dedupe loaded + SearXNG `/healthz` |
| `GET` | `/metrics` | Prometheus exposition (OTel / `ThotMetrics`) |
| `GET` | `/dedupe` | SimHash / URL index size |
| `POST` | `/collect` | Search → fetch → return markdown docs (deduped) |
| `POST` | `/collect/batch` | Multiple queries in parallel (shared dedupe) |

```bash
make collector-query COLLECTOR_QUERY="maritime AIS anomaly"

# or:
curl -sS http://127.0.0.1:8096/collect \
  -H 'Content-Type: application/json' \
  -d '{"query":"maritime AIS anomaly","topic":"osint","max_results":3}'
```

Multi-query (concurrent, shared SimHash index):

```bash
curl -sS http://127.0.0.1:8096/collect/batch \
  -H 'Content-Type: application/json' \
  -d '{
    "concurrency": 4,
    "queries": [
      {"query":"maritime AIS anomaly","topic":"osint","max_results":3},
      {"query":"anomalie AIS maritime","topic":"osint","language":"fr","max_results":3}
    ]
  }'
```

Response shape (both `/collect` and `/collect/batch`):

```json
{
  "results": [
    {
      "correlation_id": "...",
      "query": "...",
      "topic": "...",
      "language_hint": "...",
      "searxng_hits": 3,
      "documents": [ { "markdown": "...", "title": "...", "url": "...", ... } ],
      "duplicates": [],
      "errors": [],
      "dedupe": { "index_size": 0, "max_hamming": 3, "path": "..." },
      "started_at": "...",
      "ended_at": "..."
    }
  ]
}
```

- `/collect` → `results` has **one** element (all documents for that query)
- `/collect/batch` → `results` has **one element per query**
- Each `documents[]` entry carries full markdown (YAML front matter + body)
- Markdown is **not** written under the workspace

## Deduplication (SimHash)

All collect traffic (`/collect` and `/collect/batch`) shares one persistent
fingerprint index (URLs + SimHashes only — not document bodies):

```text
workspace/collector/dedupe/simhashes.jsonl
```

For each page:

1. Skip if the **URL** was already collected
2. Else convert to markdown and compute a **language-agnostic** 64-bit SimHash
   (accent fold + lowercase + character 3-grams)
3. Skip as near-duplicate when Hamming distance ≤ `COLLECTOR_SIMHASH_MAX_HAMMING`
   (default `3`) against any prior fingerprint
4. Otherwise register the fingerprint and include the document in the response

Accent folding makes French/English (and other Latin-script) near-copies collide
even when diacritics or casing differ.

## Logging, metrics, and audit

The collector follows the same OAM baseline as ingest / search / OKF:

| Concern | Mechanism |
|---------|-----------|
| Structured logs | `configure_json_logging` → JSON lines with `correlation_id` / `action_id` |
| Correlation | `ActionCorrelationMiddleware` (`X-Correlation-Id`, W3C `traceparent`) |
| Audit | ActionRecords → `default_action_sink` (`AUDIT_SINK_MODE` / hot store) |
| Governor | `wire_governor_middleware` when `GOVERNOR_MODE` ≠ `off` |
| Metrics | `GET /metrics` — `tkeir_collector_http_requests_total`, `_documents_total`, `_duplicates_total`, `_errors_total` |

Declared intents: `collect` (`POST /collect`, `/collect/batch`), `collect.read`
(`GET /dedupe`). Keycloak scope: `intent:collect`.

`make collector` exports `AUDIT_HOST_ENV` and `TKEIR_SERVICE=tkeir-collector`.

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `SEARXNG_URL` | `http://127.0.0.1:8888` | SearXNG origin |
| `COLLECTOR_PORT` | `8096` | API port |
| `COLLECTOR_MAX_RESULTS` | `5` | Default hit cap |
| `COLLECTOR_FETCH_TIMEOUT_S` | `30` | HTTP timeout |
| `COLLECTOR_SIMHASH_MAX_HAMMING` | `3` | Near-duplicate Hamming threshold |
| `COLLECTOR_BATCH_CONCURRENCY` | `4` | Max parallel queries in `/collect/batch` |
| `COLLECTOR_CORS_ORIGINS` | `http://localhost:3000,…` | CORS allow-list |
| `TKEIR_SERVICE` | `tkeir-collector` | Service name on logs / ActionRecords |
| `AUDIT_SINK_MODE` / `AUDIT_HOT_STORE_URL` | dual / workspace audit DB | ActionRecord sink (via `make collector`) |
| `TKEIR_WORKSPACE` / `WORKSPACE` | `./workspace` | Dedupe index only |

## Make targets

| Target | Action |
|--------|--------|
| `pull-searxng` | `docker pull` + seed settings |
| `searxng-up` | `docker run` with workspace mounts |
| `searxng-down` | Stop/remove container (keeps `workspace/searxng/`) |
| `collector` / `collector-up` | Start FastAPI service |
