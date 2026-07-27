# Datasets & Ontologies

Versioned Zero-to-Hero demo data: NATO C4ISR OSINT and AcmeSystems enterprise
docs, with per-user (`user_space`) and per-folder (`topic_id`) segregation.

**Zero-to-Hero:** datasets are already in the repo — skip `make datasets` and
go straight to ingest (`make datasets-ingest`). Use `make datasets` only to
regenerate or re-download.

## Overview

| Dataset | Directory | Default Keycloak user | Docs |
|--------|-----------|----------------------|------|
| OSINT / NATO C4ISR | `datasets/osint/` | `demo-user` | 1 500 (+ versioned `corpus.jsonl`) |
| Enterprise (AcmeSystems) | `datasets/enterprise/` | `demo-admin` | 500 gen + up to 500 downloaded |

P0 (auth off) indexes both into `dev@tkeir`. P1 Compose routes each dataset
to its Keycloak principal so cross-user RAG returns zero hits.

```bash
make bootstrap && make ingest  # P0: Vespa + host ingest (:8091)
make datasets-ingest           # ingest versioned datasets/
make datasets-ingest-user      # P1 OSINT → demo-user
make datasets-ingest-admin     # P1 Enterprise → demo-admin
make datasets-ingest-web       # HMI + curl guide

# Optional (maintainers): regenerate / re-download
make datasets
make datasets DATASETS_DOWNLOAD=0
make datasets-clean
```


## Versioned business ontologies (passage retrieval)

Each Zero-to-Hero dataset ships a committed `VERSION`, `CHECKSUMS.sha256`,
`business_ontology.yaml`, and `corpus.jsonl` under `datasets/osint/` and
`datasets/enterprise/`. Pass the business YAML contents as `business_ontology`
on `/search` or `/rag/query` (query expansion is per-request; the RAG server
does not load these from disk). Index-time concepts use
`dual_hybrid.business_ontology.index_enabled` when present on disk under
`datasets/<name>/`.

```bash
# Example: expand an OSINT query with the versioned ontology
python3 -c "import yaml,json; print(json.dumps(yaml.safe_load(open('datasets/osint/business_ontology.yaml'))))"
```

OWL/TTL C2SIM graphs live in `datasets/osint/ontologies/` (also versioned).
Optional `make datasets` (with download) refreshes `corpus.jsonl` /
`manifest.json` / checksums for maintainers.

## Dataset A — NATO OSINT

Formats (seed=42, 1 500 docs): txt, md, html, json, pdf, docx, csv under
`raw/`, `markdown/`, `html/`, `json/`, `pdf/`, `docx/`, `csv/`.

| `topic_id` | Document types |
|------------|----------------|
| `situational_awareness` | SITREP, SALUTE, AIS, ADSB |
| `intelligence` | INTSUM, ENTITY |
| `operations` | OPORD, AAR, LOGSIT |
| `publications` | NATOPUB |

### Ontologies (`datasets/osint/ontologies/`)

| File | Format | Standard |
|------|--------|----------|
| `c2sim_core.owl` | RDF/XML | SISO-STD-019 Core |
| `c2sim_lox.owl` | RDF/XML | Land Ops Extension |
| `c2sim_smx.owl` | RDF/XML | SMX / APP-6 |
| `c2sim_cwix2023.owl` | RDF/XML | CWIX 2023 profile |
| `c2sim_c4isr.ttl` | Turtle | NATO C4ISR |
| `c2sim_combined.ttl` | Turtle | Merged + CWIX instances |

Namespaces:

```text
c2sim:  http://www.sisostds.org/ontologies/C2SIM#
lox:    http://www.sisostds.org/ontologies/lox#
smx:    http://www.sisostds.org/ontologies/smx#
cwix:   http://www.sisostds.org/ontologies/C2SIM/cwix2023#
c4isr:  http://www.nato.int/ontologies/c4isr#
```

Official downloads (when network is available) land in
`ontologies/official/` and never overwrite the generated files.

Point the document-ontology pipeline at these files **at ingest time** by
uploading ontology **bytes** with each document (`ontology_file` multipart or
JSON `content_base64`). The ingest server does not read client paths. Client
helper: `ingest_dataset.py --ontology-dir`. Details:
[Document ontology](document_ontology.md).

## Dataset B — Enterprise

Fictional company **AcmeSystems** (B2B software, Paris / Berlin / Montreal).
Offline generators cover meetings, specs, ISO procedures, HR, email, invoices,
and KB articles. Prefer EnterpriseRAG-Bench when online:

- HuggingFace: `https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench`
- GitHub: `https://github.com/onyx-dot-app/EnterpriseRAG-Bench`

| `topic_id` | Sources / generators |
|------------|----------------------|
| `projects` | meeting minutes, project reports, confluence/gdoc/jira/transcript |
| `engineering` | technical specs, API docs, KB articles |
| `quality` | procedures, audit reports |
| `hr` | HR policies, email / slack |
| `finance` | invoices, CRM |

## CLI reference

### `tools/datasets/generate_tkeir_datasets.py`

| Flag | Default | Meaning |
|------|---------|---------|
| `--output` / `-o` | `./datasets` | Output root |
| `--count-osint` | 1500 | OSINT document count |
| `--count-enterprise` | 500 | Enterprise document count |
| `--seed` / `-s` | 42 | Deterministic RNG |
| `--dataset` | `all` | `osint` \| `enterprise` \| `all` |
| `--only-ontologies` | off | Skip documents |
| `--download` | off | Best-effort official artifacts |
| `--quiet` / `-q` | off | Quiet mode |

`TKEIR_DATASETS_OFFLINE=1` forces download to no-op.

### `tools/datasets/ingest_dataset.py`

| Flag | Meaning |
|------|---------|
| `--datasets-dir` | Root with `osint/` / `enterprise/` |
| `--api-url` | Ingest base (default `:8091`) |
| `--dataset` | `osint` \| `enterprise` \| `all` |
| `--ontologies` | Local OWL/TTL/RDF files; client uploads bytes as `ontology_file` |
| `--ontology-dir` | Local dir; client uploads each file's bytes with every document |
| `--stop-on-failed` | Abort client + stop ingest server on first failure |
| `--topics` / `--formats` | Filters |
| `--user-space` | Override for all docs |
| `--token` / `--token-url` + `--username` / `--password` | Auth |
| `--dry-run` | Report only |
| `--wait` / `--no-wait` | Wait for each job to finish (default on) so progress/ETA track indexing |
| `--poll-timeout` | Max seconds to wait per doc when `--wait` (default 3600) |
| `--progress-every` | Log progress every N docs (default 1) |
| `--fallback-index` | Allow local pipeline+index if ingest API is down (capped; see `--force-fallback`) |
| `--force-fallback` | Permit local fallback for large corpora (very slow) |
| `--fallback-max-docs` | Max docs for unforced fallback (default 50) |
| `--print-web-guide` | HMI + curl guide with real filenames |
| `--print-token` | Print Keycloak access token |

`user_space` resolution: CLI → manifest → `VESPA_USER_SPACE` → `dev@tkeir`.

## SPARQL examples

```sparql
PREFIX c2sim: <http://www.sisostds.org/ontologies/C2SIM#>
PREFIX lox:   <http://www.sisostds.org/ontologies/lox#>

# Units and tasks
SELECT ?unit ?taskName ?obj WHERE {
  ?task c2sim:taskAssignedTo ?unit ;
        c2sim:taskName ?taskName ;
        c2sim:hasObjective ?obj .
} LIMIT 10

# Ground units
SELECT ?u ?label WHERE {
  ?u a lox:GroundUnit ; rdfs:label ?label .
}

# C4ISR-style assets in the combined graph
PREFIX cwix: <http://www.sisostds.org/ontologies/C2SIM/cwix2023#>
SELECT ?s ?label WHERE {
  ?s rdfs:label ?label .
  FILTER(CONTAINS(LCASE(STR(?label)), "cwix"))
} LIMIT 20
```

## NER → OWL mapping (indicative)

| NER label | OWL / C2SIM class |
|-----------|-------------------|
| ORG | `c2sim:OperationalEntity` / `lox:GroundUnit` |
| LOC | Location / PointLocation |
| MISC | PlatformEntity |
| EVENT | MilitaryTask |
| document type cues | SITREP / OPORD / INTSUM individuals |

## Compose with NATO template

```bash
COMPOSE_TURTLE_DIR=datasets/osint/ontologies \
make compose TEMPLATE=nato_synthesis_note TOPIC="CWIX 2023"
```

## Web ingestion

```bash
make datasets-ingest-web
```

Mode A (HMI): sign in as `demo-user` / `demo-admin`, drag topic folders from
`datasets/osint/` or `datasets/enterprise/`.

Mode B (curl): obtain a Keycloak token, then `POST /ingest/document` with
multipart `file` + `metadata` JSON (`topic_id`, `corpus`, `doc_type`, …).

Isolation check: `demo-user` querying *AcmeSystems Project ATLAS* → 0 hits;
`demo-admin` querying *SITREP Objective ALPHA* → 0 hits.

## Ontology integration notes

Generated ontologies under `osint/ontologies/` are safe for local RDF
ingestion and `COMPOSE_TURTLE_DIR`. Official artifacts, when downloaded, are
placed in `ontologies/official/` so generated `.owl` / `.ttl` files remain
unchanged. See also `datasets/osint/ONTOLOGY_INTEGRATION.md` after
`make datasets`.

See [Zero-to-Hero](../zero_to_hero.md) §§3.4–3.5 and §5.5, and
[Templates](templates.md).
