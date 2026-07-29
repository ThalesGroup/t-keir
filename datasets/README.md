# Datasets

Versioned Zero-to-Hero demo data and BEIR evaluation sets.

| Path | Role |
|------|------|
| `osint/` | NATO C4ISR OSINT (`VERSION`, `corpus.jsonl`, `business_ontology.yaml`, `ontologies/`) |
| `enterprise/` | AcmeSystems enterprise (`VERSION`, `corpus.jsonl`, `business_ontology.yaml`) |
| `scifact/`, `fiqa/`, `arguana/` | BEIR IR evaluation corpora + `business_ontology.yaml` |
| `scidocs/` | BEIR SciDocs — ontology committed; corpus via `download.sh` (~245 MiB) |


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

**SciDocs** bulk files (`corpus.jsonl`, `queries.jsonl`, `qrels/`) are gitignored —
run `bash datasets/scidocs/download.sh` or `make scidocs-download`.

## Optional regenerate / download

```bash
make datasets                 # refresh generate + best-effort download
make datasets DATASETS_DOWNLOAD=0
make datasets-ontologies      # VERSION + business YAML + C2SIM OWL/TTL only
```
## Rag Datasets

```bash
pip install datasets huggingface_hub requests tqdm
python download_rag_datasets.py --output_dir ./rag_benchmarks
```

HuggingFace splits are saved as both `.parquet` and `.json` (JSON array of records).
Re-running the script skips existing downloads and fills any missing `.json` siblings.

Published baselines (gap-to-leader targets):  
[`rag_benchmarks/LEADERBOARD.md`](rag_benchmarks/LEADERBOARD.md) · [`rag_benchmarks/leaderboard.yaml`](rag_benchmarks/leaderboard.yaml).

T-KEIR-only generation eval (oracle evidence → NLP → ontology → forge → LLM; no retrieve):

```bash
make generate-eval
make generate-eval GEN_DATASETS=multihop
make generate-eval GEN_DATASETS=covidqa \
  GEN_EXTRA="--max-queries 5 --no-forge-prompt --no-reasoner"
```
