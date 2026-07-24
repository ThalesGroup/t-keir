# Datasets

Versioned Zero-to-Hero demo data and BEIR evaluation sets.

| Path | Role |
|------|------|
| `osint/` | NATO C4ISR OSINT (`VERSION`, `corpus.jsonl`, `business_ontology.yaml`, `ontologies/`) |
| `enterprise/` | AcmeSystems enterprise (`VERSION`, `corpus.jsonl`, `business_ontology.yaml`) |
| `scifact/`, `fiqa/`, `arguana/` | BEIR IR evaluation corpora + `business_ontology.yaml` |


**Zero-to-Hero:** use the committed trees as-is — ingest with
`make datasets-ingest`. You do **not** need `make datasets` first.

## Versioned artifacts (committed)

| File | Purpose |
|------|---------|
| `VERSION` | Dataset release id |
| `CHECKSUMS.sha256` | SHA-256 of versioned files |
| `business_ontology.yaml` | Dual-hybrid query-expansion / overlap payload (Z2H + BEIR) |
| `corpus.jsonl` | Canonical documents (`_id`, `title`, `text`, `metadata`) |
| `manifest.json` | Ingest index (paths, topics, origins) |
| `ontologies/` | C2SIM/C4ISR OWL/TTL (OSINT) |

PDF/DOCX trees and `ontologies/official/` stay local-only (gitignored).

## Optional regenerate / download

```bash
make datasets                 # refresh generate + best-effort download
make datasets DATASETS_DOWNLOAD=0
make datasets-ontologies      # VERSION + business YAML + C2SIM OWL/TTL only
```
