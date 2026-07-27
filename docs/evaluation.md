# Evaluation

T-KEIR retrieval quality is measured with the [BEIR](https://github.com/beir-cellar/beir)
benchmark suite. Use two harnesses:

| Target | Audience | Runtime | Purpose |
|--------|----------|---------|---------|
| **`make beir-smoke`** | Day-to-day development | **&lt; 5 min** | Catch bottlenecks and rank-strategy failures fast |
| **`make beir-eval`** | Full quality report | Hours | Full corpora, dense baseline, MkDocs report |

Both evaluate **`scifact`**, **`fiqa`**, and **`arguana`** (override with
`BEIR_DATASETS=…`). Data lives under `./datasets/` (downloaded on demand).

---

## Quick evaluation — `make beir-smoke`

Development smoke test. Isolates **each** corpus, indexes a ranking-focused
subset (gold + close distractors), measures **time + NDCG**, flags obvious
ranking failures, then **wipes** the BEIR Vespa volume.

### What it does (per corpus)

1. Sample queries with gold answers (default **10** per dataset)
2. For each query, index **gold docs** + **close distractors** (default **10**
   lexically nearest non-gold docs) and pad so the pool has at least
   **`--rank-docs`** candidates (default **10**)
3. Score **BM25** and **T-KEIR passage retrieval** at `top_k` (default **10**,
   raised to match `--rank-docs` when needed). Passages are indexed into the
   Vespa **`global`** schema only (BEIR never uses `user`). Dataset
   `business_ontology.yaml` is used for query expansion and overlap scoring.
4. Record stage timings: Vespa reset, index, retrieve, and avg pipeline
   stages (`nlp`, `expand`, `embed`, `vespa_global`, `rrf`, `ontology`,
   `cross_encoder`, …). Query **`nlp`** is the T-KEIR linguistic pipeline
   on each query (`search.enabled` in `rag.yaml`).
5. Emit rank/strategy **alerts** when something looks broken
6. After all corpora: cleanup Vespa (`reset_vespa_for_beir`)

Dense SentenceTransformer baseline is **skipped** (too slow for a smoke loop).

### Why a subset

Full FiQA (~58k docs) is too large for a tight feedback loop. The smoke index
keeps gold answers plus **close** hard negatives (not random noise), so ranking
mistakes show up without a full reindex.

ArguAna query documents that share an id with the query are excluded from the
index (avoids trivial self-matches).

### Run

```bash
# Default: 10 queries × (≥10 pool + 10 close), NLP chunking, top_k=10, cleanup
make beir-smoke

# Skip NLP (synthetic chunks only — faster, weaker ranking signal)
make beir-smoke BEIR_SMOKE_INDEX_MODE=fast

# Larger ranking pools / more queries
make beir-smoke BEIR_SMOKE_QUERIES=15 BEIR_SMOKE_CLOSE=20 BEIR_SMOKE_RANK_DOCS=20

# Single corpus
make beir-smoke BEIR_DATASETS=scifact

# Keep the Vespa index after the run
make beir-smoke BEIR_SMOKE_EXTRA=--no-cleanup

# BM25-only (no Vespa / T-KEIR) — subset + metrics only
make beir-smoke BEIR_SMOKE_EXTRA=--skip-tkeir
```

| Make variable | Default | Meaning |
|---------------|---------|---------|
| `BEIR_DATASETS` | `scifact fiqa arguana` | Corpora to isolate |
| `BEIR_SMOKE_QUERIES` | `10` | Queries per corpus |
| `BEIR_SMOKE_CLOSE` | `10` | Close (hard-negative) docs **per query** |
| `BEIR_SMOKE_RANK_DOCS` | `10` | Min documents in the indexed pool **per query** |
| `BEIR_SMOKE_TOP_K` | `10` | Retrieval cutoff (docs scored/ranked per query) |
| `BEIR_SMOKE_INDEX_MODE` | `chunking` | `fast` (no NLP) \| `chunking` (NLP) \| `full` |
| `BEIR_SMOKE_EXTRA` | _(empty)_ | Extra CLI flags (`--no-cleanup`, `-v`, …) |
| `BEIR_VESPA_NAME` / `BEIR_VESPA_VOLUME` | dedicated BEIR volume | Same isolation as full eval |

CLI module: `thot.tools.eval.beir_smoke`.

### Alerts (rank / strategy / timing)

Each alert is severity-ordered (`high` → `medium` → `low`) and carries a
**Code focus** hint (module / config to change).

| Code | Meaning |
|------|---------|
| `tkeir_ndcg_zero` | T-KEIR NDCG@10 is 0 while BM25 scores on the same subset |
| `tkeir_behind_bm25` | T-KEIR NDCG@10 &lt; 50% of BM25 |
| `empty_retrievals` | One or more queries returned zero hits |
| `gold_miss_all` | Queries where no gold doc appeared in the top-k |
| `tkeir_error` | Indexing / Vespa / retrieval exception |
| `slow_index` / `slow_retrieve` | Wall-clock bottleneck on index or retrieve |
| `slow_stage_*` | Pipeline stage over threshold (`cross_encoder`, `vespa_global`, …) |

If wall clock exceeds **5 minutes**, the harness logs a warning (shrink
`--queries` / `--close-docs`; use `--index-mode fast` only when timing
index path without NLP; ensure the embedder is warm).

### Smoke reports (action-oriented)

| Path | Contents |
|------|----------|
| `reports/beir/smoke/report.md` | Problems-first Markdown (see below) |
| `reports/beir/smoke/report.json` | Same data + `comparison` + `focus[]` |
| `reports/beir/smoke/report.prev.json` | Previous run (archived on each write) |

Report structure (designed to drive code changes):

1. **Vs previous report** — overall **better / worse / mixed / unchanged**
   (primary: mean Δ T-KEIR NDCG@10; secondary: high-severity alert count)
2. **Focus — problems to fix** — severity-ordered alerts with **Code focus**
3. **Failure examples** — FP / FN with query text + analysis (reproduce locally)
4. **Summary metrics** — NDCG@10 vs BM25, Δ, timings (NDCG cell notes vs prev)
5. **Timings** — retrieval stages sorted by cost

Prerequisite: Vespa up (`make bootstrap`). Smoke uses the dedicated BEIR
volume (`BEIR_VESPA_VOLUME`) so it does not wipe your primary demo index.

Aliases: `make eval-smoke` → `beir-smoke`; `make eval` → `beir-eval`.

---

## Full evaluation — `make beir-eval`

Full corpora, BM25 + **BGE-M3 dense+sparse** (`resources/modeling/net/bge-m3`,
same FlagEmbedding path as `beir-smoke`) + T-KEIR, error analysis, and the
MkDocs quality report. Use after smoke is green, or for release evidence.

```bash
make beir-eval
make beir-eval BEIR_DATASETS=scifact
make beir-eval BEIR_DATASETS=scifact BEIR_EXTRA=--skip-dense
```

CLI: `thot.tools.eval.beir_eval`. Indexes with the T-KEIR NLP pipeline into
Vespa **`global`**, retrieves with `PassageRetrievalPipeline` (**no answer
generation**), and compares against local BM25 / **BGE-M3 dense** baselines
plus published BEIR leaderboard numbers (BM25 / SPLADE / Contriever).
Override dense model only with BGE-M3 (`BEIR_DENSE_MODEL=bge-m3`, default);
MiniLM is rejected.

**Error analysis** (up to three examples per failure kind) reports the full
query, the offending or gold document, lexical token coverage, and a short
written analysis of why ranking failed.

### Full-eval reports

After **each** dataset finishes:

| Path | Contents |
|------|----------|
| `docs/evaluation_report.md` | Cumulative MkDocs report (always) |
| `reports/beir/report.md` | Copy of the cumulative report |
| `reports/beir/<dataset>/report.md` | That dataset alone |

While more datasets remain, the cumulative files include an **Intermediate**
banner (`N/M` completed). Override with `--report` / `BEIR_REPORT` for an
extra copy. See [BEIR evaluation report](evaluation_report.md).

---

## Datasets

| Id | Display name | Task | Domain | Corpus | Test queries | Avg. relevant / query |
|----|--------------|------|--------|--------|--------------|------------------------|
| `scifact` | SciFact | Fact checking | Scientific abstracts | 5,183 | 300 | ~1.1 |
| `fiqa` | FiQA-2018 | Question answering | Personal finance | 57,638 | 648 | ~2.6 |
| `arguana` | ArguAna | Argument / counterargument | Debate essays | 8,674 | 1,406 | ~1.0 |

Published **NDCG@10** reference scores (full eval report):

| Dataset | BEIR BM25 | SPLADE | Contriever |
|---------|----------:|-------:|-----------:|
| SciFact | 0.665 | 0.699 | 0.677 |
| FiQA-2018 | 0.236 | 0.342 | 0.329 |
| ArguAna | 0.397 | 0.472 | 0.435 |

### SciFact (`scifact`)

Pairs **scientific claims** with **abstract-level evidence** (AllenAI SciFact).
Queries are short claims; gold docs are paper abstracts that support or refute
them.

- **Why it is hard:** BM25 works when claim tokens overlap the abstract, but
  fails on paraphrase, negation, and statistics worded differently from the gold
  paper. Dense retrieval recovers some paraphrases, yet can miss niche
  biomedical entities underrepresented in the embedding space.
- **What T-KEIR stresses:** full-document NLP (NER, keywords, ontology cues) plus
  hybrid ranking on short, evidence-seeking queries.

### FiQA-2018 (`fiqa`)

Opinionated **finance QA** from StackExchange-style posts (FiQA shared task).
Queries are investor / consumer questions; documents are longer forum answers.

- **Why it is hard:** specialized jargon (tickers, instruments, accounting).
  Lexical mismatch dominates: colloquial queries vs formal or acronym-heavy
  gold posts. Dense models help on shared sense with different wording; they
  still struggle with numeral- or ticker-heavy questions where the gold post is
  short and symbol-dominated.
- **What T-KEIR stresses:** domain vocabulary and hybrid lexical/semantic match
  on a mid-size corpus (~58k docs).

### ArguAna (`arguana`)

**Counterargument retrieval**: the query is an argumentative passage; the
relevant document is typically an **opposing stance**, not a paraphrase of the
query. Queries are long (often paragraph-scale); roughly one relevant doc per
query.

- **Why it is hard:** true counterarguments deliberately avoid repeating the
  query’s key phrases, so pure lexical overlap under-ranks gold and promotes
  thematically similar but same-stance essays. Generic sentence embeddings only
  partially encode stance polarity and argumentative structure.
- **What T-KEIR stresses:** whether NLP enrichment and adaptive Vespa rank
  profiles help beyond bag-of-words when relevance is *contrastive* rather than
  topical duplication.

> **Note:** In ArguAna, queries also appear in the corpus; the BEIR toolkit
> removes the query id from the candidate set at inference time. T-KEIR’s harness
> uses the standard BEIR loaders for that behaviour.

---

## Related docs

- [BEIR evaluation report](evaluation_report.md) — latest measured metrics (full eval)
- [Vespa search and RAG](tools/vespa_rag.md) — indexing, search API, concurrency
- [Dev container](devcontainer.md) — TLS / CA tips when downloading BEIR datasets
- [Datasets](tools/datasets.md) — Zero-to-Hero OSINT / enterprise trees (separate from BEIR)
