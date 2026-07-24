# OKF (Open Knowledge Format) — tkeir-okf

> Phase F — export the enriched T-KEIR index as OKF v0.1 bundles; curate and
> compose with the new `okf_wiki_brief` workflow.

## What OKF is

OKF v0.1 ([spec](https://okf.md/spec)) represents knowledge as a **directory of
UTF-8 Markdown files with YAML frontmatter**. The only required field in every
concept file is `type`. T-KEIR adds producer extensions (`tkeir_*`) that
conformant consumers ignore (§9).

```text
bundle/
├── index.md
├── log.md
├── query_context.md # scoped exports only
├── concepts/<doc>.md
└── chunks/<id>.md
```

## Who uses it

| Actor | Path |
|-------|------|
| Operators / CLI | `tkeir-okf-export`, `make okf-export` |
| HTTP clients / HMI | `tkeir-okf` `:8094`, `/okf` in the HMI |
| Agents | `okf_bundle_list` / `okf_bundle_get` via in-process `McpHandlers` |
| Workflows | `okf_wiki_brief` (builtin scoped export → curator → compose) |

## Static export (`tkeir-okf-export`)

```bash
make okf-export USER_SPACE=dev@tkeir OKF_MAX_DOCS=50
# or:
tkeir-okf-export --user-space dev@tkeir --max-docs 50
```

Walks parent documents in the Vespa streaming group, writes concept + chunk
stubs, `index.md`, and `log.md`. Bundle body text is limited to the first
sentence (description); full content stays in Vespa.

## Dynamic scoped export (query → bundle)

```bash
make okf-export QUERY="What is the status of Project ATLAS?" USER_SPACE=dev@tkeir
```

Runs RAG for the query, restricts the export to returned document ids, and
writes `query_context.md` with the query, answer summary, and concept links.

## New MCP tools: `okf_bundle_list` / `okf_bundle_get`

| Tool | Intent | Arguments |
|------|--------|-----------|
| `okf_bundle_list` | `intent:search` | _(none — `user_space` from auth)_ |
| `okf_bundle_get` | `intent:search` | `bundle_id` (required), `concept_id` (optional) |

```bash
make mcp-tools MCP_QUERY="okf"
# /mcp/tools lists okf_bundle_list and okf_bundle_get
```

## New agent: `okf_curator`

YAML: `configs/agents/okf_curator.yaml`. Tools: `search`, `rag_query`,
`ontology_query`, `okf_bundle_get`. Output contract `okf_enrichment_v1`
(enrichments recovered from `notes` JSON; `claim` + `chunk_ids` keep the
AgentLoop provenance filter).

## New workflow: `okf_wiki_brief`

```text
scope_bundle (builtin: okf_scoped_export)
 → curate (okf_curator + OkfEnrichmentApplicator)
 → deliverable (compose: synthesis_note)
```

```bash
make okf-workflow \
 GOAL="Produce an OKF knowledge brief on Objective ALPHA" \
 TOPIC="Objective ALPHA"
```

## HTTP API (`/okf/...`)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/okf/export` | Export (auth `user_space`; body may include `query`) |
| `GET` | `/okf/bundles` | List caller's bundles |
| `GET` | `/okf/bundles/{id}` | Metadata + index (+ optional `?concept_id=`) |
| `GET` | `/okf/bundles/{id}/download` | `.tar.gz` |
| `DELETE` | `/okf/bundles/{id}` | DSR forget (ActionRecord + atomic remove) |
| `GET` | `/health` `/ready` `/metrics` | Ops |

## Run via Makefile

```bash
make okf # tkeir-okf on :8094
make okf-export # CLI export
make okf-bundle-ls # list via HTTP
make okf-workflow # okf_wiki_brief via tkeir-agent
```

## Compose profile: `okf`

```bash
make compose-up PROFILES=core,okf
```

Service `tkeir-okf` publishes host port **8094**. Do not enable the `governor`
profile on the same host at the same time (governor also uses 8094).

## HMI `/okf` bundle browser

Browse bundles, render `index.md` / concepts, download archives, and POST a
query-scoped export. Nav link sits between RAG and Agents.

## T-KEIR producer extensions (`tkeir_*` frontmatter)

```yaml
tkeir_doc_id: <vespa parent doc id>
tkeir_user_space: <vespa streaming group>
tkeir_chunk_ids: [<id>, ...]
tkeir_pipeline_sha: <sha256> # optional
tkeir_okf_version: "0.1"
```

## Authz & audit

- `user_space` from Bearer / `VESPA_USER_SPACE` / `dev@tkeir` — never from body
 for access control.
- Governor intent `intent:okf.export` on `POST /okf/export`.
- ActionRecords: `ext.action_kind=okf.export.batch|full|scoped|delete`.

## Layout (`thot/okf/`)

```text
tkeir/thot/okf/
 models.py # OkfConcept*, OkfBundle, OkfExport*, enrichment
 exporter.py # export_full / export_scoped / CLI
 applicator.py # apply curator enrichments
 store.py # tenant-scoped list/get/delete
 server.py # tkeir-okf FastAPI
```

See [Agents](agents.md), [MCP](mcp.md).

**Checkpoint:** `.tkeir-okf/<bundle_id>/index.md` exists after `make okf-export`.
