# Corpus & Ontologies

Two offline-first demo corpora for Zero-to-Hero: NATO C4ISR OSINT and
AcmeSystems enterprise docs, with per-user (`user_space`) and per-folder
(`topic_id`) segregation.

## Overview

| Corpus | Directory | Default Keycloak user | Docs |
|--------|-----------|----------------------|------|
| OSINT / NATO C4ISR | `workspace/corpus_nato/` | `demo-user` | 1 500 |
| Enterprise (AcmeSystems) | `workspace/corpus_enterprise/` | `demo-admin` | 500 |

P0 (auth off) indexes both into `dev@tkeir`. P1 Compose routes each corpus
to its Keycloak principal so cross-user RAG returns zero hits.

```bash
make corpus                  # generate both corpora offline
make corpus-download         # best-effort SISO + EnterpriseRAG-Bench
make corpus-ingest           # P0 CLI ingest (--fallback-index)
make corpus-ingest-user      # P1 OSINT → demo-user
make corpus-ingest-admin     # P1 Enterprise → demo-admin
make corpus-ingest-web       # HMI + curl guide
make corpus-demo             # generate → ingest (P0)
make corpus-clean
```

## Corpus A — NATO OSINT

Formats (seed=42, 1 500 docs): txt, md, html, json, pdf, docx, csv under
`raw/`, `markdown/`, `html/`, `json/`, `pdf/`, `docx/`, `csv/`.

| `topic_id` | Document types |
|------------|----------------|
| `situational_awareness` | SITREP, SALUTE, AIS, ADSB |
| `intelligence` | INTSUM, ENTITY |
| `operations` | OPORD, AAR, LOGSIT |
| `publications` | NATOPUB |

### Ontologies (`corpus_nato/ontologies/`)

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

Point the document-ontology pipeline at these files to enrich each document
graph before Vespa indexing (`derive-from` in
`tkeir/configs/document-ontology.yaml`) — see
[Document ontology](document_ontology.md).

## Corpus B — Enterprise

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

### `tools/corpus/generate_tkeir_corpus.py`

| Flag | Default | Meaning |
|------|---------|---------|
| `--output` / `-o` | `./workspace` | Output root |
| `--count-osint` | 1500 | OSINT document count |
| `--count-enterprise` | 500 | Enterprise document count |
| `--seed` / `-s` | 42 | Deterministic RNG |
| `--corpus` | `all` | `osint` \| `enterprise` \| `all` |
| `--only-ontologies` | off | Skip documents |
| `--download` | off | Best-effort official artifacts |
| `--quiet` / `-q` | off | Quiet mode |

`TKEIR_CORPUS_OFFLINE=1` forces download to no-op.

### `tools/corpus/ingest_corpus.py`

| Flag | Meaning |
|------|---------|
| `--corpus-dir` | Root with `corpus_nato/` / `corpus_enterprise/` |
| `--api-url` | Ingest base (default `:8091`) |
| `--corpus` | `osint` \| `enterprise` \| `all` |
| `--topics` / `--formats` | Filters |
| `--user-space` | Override for all docs |
| `--token` / `--token-url` + `--username` / `--password` | Auth |
| `--dry-run` | Report only |
| `--fallback-index` | `make pipeline` + `make index` when ingest is down |
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
COMPOSE_TURTLE_DIR=workspace/corpus_nato/ontologies \
make compose TEMPLATE=nato_synthesis_note TOPIC="CWIX 2023"
```

## Web ingestion

```bash
make corpus-ingest-web
```

Mode A (HMI): sign in as `demo-user` / `demo-admin`, drag topic folders from
`workspace/corpus_nato/` or `workspace/corpus_enterprise/`.

Mode B (curl): obtain a Keycloak token, then `POST /ingest/document` with
multipart `file` + `metadata` JSON (`topic_id`, `corpus`, `doc_type`, …).

Isolation check: `demo-user` querying *AcmeSystems Project ATLAS* → 0 hits;
`demo-admin` querying *SITREP Objective ALPHA* → 0 hits.

## Ontology integration notes

Generated ontologies under `corpus_nato/ontologies/` are safe for local RDF
ingestion and `COMPOSE_TURTLE_DIR`. Official artifacts, when downloaded, are
placed in `ontologies/official/` so generated `.owl` / `.ttl` files remain
unchanged. See also `workspace/corpus_nato/ONTOLOGY_INTEGRATION.md` after
`make corpus`.

See [Zero-to-Hero](../zero_to_hero.md) §§3.4–3.5 and §5.5, and
[Templates](templates.md).
