# BEIR Retrieval Evaluation Report

_Generated 2026-07-16 20:27 UTC_

## Overview

This report benchmarks three retrieval systems on BEIR datasets:

1. **T-KEIR retrieval only** — full-document NLP indexing + QueryAnalyzer + adaptive Vespa rank profiles. Answer generation is **not** run (embeddings only).
2. **Local BM25 (Okapi)** — in-memory `rank_bm25` baseline.
3. **Local dense** — SentenceTransformer `sentence-transformers/all-MiniLM-L6-v2`.

Retrieval cut-off is **top-100**. Metrics use `beir.retrieval.evaluation.EvaluateRetrieval` (pytrec_eval).

> **Leaderboard:** SciFact / FiQA-2018 / ArguAna NDCG@10 values for BM25, SPLADE, and Contriever are the published BEIR reference scores. Local BM25 is not Elasticsearch-identical; dense MiniLM is not Contriever. **T-KEIR** is the system under evaluation against that public leaderboard.

## Leaderboard comparison (NDCG@10)

Gap = system NDCG@10 − **best published** NDCG@10 on that dataset (among BEIR BM25, SPLADE, Contriever). Negative ⇒ behind the leaderboard leader.

| Dataset | Best published | Best score | **T-KEIR** | Gap T-KEIR → best | Local BM25 | Gap BM25 → best | Local Dense | Gap Dense → best |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| SciFact | SPLADE | 0.699 | 0.737 | +0.038 | 0.652 | -0.047 | 0.645 | -0.054 |

### Published baselines (reference)

| Dataset | BEIR BM25 | SPLADE | Contriever | **Best** |
|---|---:|---:|---:|---|
| SciFact | 0.665 | 0.699 | 0.677 | **SPLADE** (0.699) |

### Gap to best published system (detail)

| Dataset | Best system | Best NDCG@10 | T-KEIR gap | Local BM25 gap | Local Dense gap | T-KEIR vs BM25 | T-KEIR vs SPLADE | T-KEIR vs Contriever |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| SciFact | SPLADE | 0.699 | +0.038 | -0.047 | -0.054 | +0.072 | +0.038 | +0.060 |

## Per-dataset metrics

### SciFact (`scifact`)

- Corpus size: **5,183** documents  
- Test queries: **300**
- Dense baseline model: `sentence-transformers/all-MiniLM-L6-v2`
- **Best published system:** `SPLADE` (NDCG@10 = 0.699)
- T-KEIR status: **ok** (QueryAnalyzer + Vespa hybrid)
- **T-KEIR gap to best (SPLADE):** `+0.038` (T-KEIR 0.737 − 0.699)
- Local BM25 gap to best: `-0.047`
- Local Dense gap to best: `-0.054`

| Metric | T-KEIR | Local BM25 | Local Dense |
|---|---:|---:|---:|
| NDCG@10 | 0.737 | 0.652 | 0.645 |
| MAP@100 | 0.704 | 0.613 | 0.603 |
| Recall@100 | 0.855 | 0.873 | 0.925 |

#### Error analysis (T-KEIR)

- **False positive** — query `1`: «0-dimensional biomaterials show inductive properties.»
  - Rank #1 doc `13231899` (score=0.0439) is not relevant. Snippet: In situ regulation of DC subsets and T cells mediates tumor regression in mice. Vaccines are largely ineffective for pa…
- **False negative** — query `1`: «0-dimensional biomaterials show inductive properties.»
  - Gold doc `31715818` completely missed (not in top-100). Snippet: New opportunities: the use of nanotechnologies to manipulate and track stem cells. Nanotechnologies are emerging platfo…
- **Near miss** — query `133`: «Assembly of invadopodia is triggered by focal generation of phosphatidylinositol-3,4-biphosphate and the activation of the nonreceptor tyrosine kinase Src.»
  - Gold doc `12640810` retrieved at rank 14/100 (missed NDCG@10). Snippet: Cortactin regulates cofilin and N-WASp activities to control the stages of invadopodium assembly and maturation Invadop…

#### Error analysis (Local BM25)

- **False positive** — query `1`: «0-dimensional biomaterials show inductive properties.»
  - Rank #1 doc `10608397` (score=10.1725) is not relevant. Snippet: High-performance neuroprosthetic control by an individual with tetraplegia. BACKGROUND Paralysis or amputation of an ar…
- **False negative** — query `1`: «0-dimensional biomaterials show inductive properties.»
  - Gold doc `31715818` completely missed (not in top-100). Snippet: New opportunities: the use of nanotechnologies to manipulate and track stem cells. Nanotechnologies are emerging platfo…
- **Near miss** — query `13`: «5% of perinatal mortality is due to low birth weight.»
  - Gold doc `1606628` retrieved at rank 48/100 (missed NDCG@10). Snippet: Estimates of global prevalence of childhood underweight in 1990 and 2015. CONTEXT One key target of the United Nations …

#### Error analysis (Local Dense)

- **False positive** — query `1`: «0-dimensional biomaterials show inductive properties.»
  - Rank #1 doc `29638116` (score=0.3540) is not relevant. Snippet: Complex Tissue and Disease Modeling using hiPSCs. Defined genetic models based on human pluripotent stem cells have ope…
- **False negative** — query `48`: «A total of 1,000 people in the UK are asymptomatic carriers of vCJD infection.»
  - Gold doc `13734012` completely missed (not in top-100). Snippet: Prevalent abnormal prion protein in human appendixes after bovine spongiform encephalopathy epizootic: large scale surv…
- **Near miss** — query `13`: «5% of perinatal mortality is due to low birth weight.»
  - Gold doc `1606628` retrieved at rank 17/100 (missed NDCG@10). Snippet: Estimates of global prevalence of childhood underweight in 1990 and 2015. CONTEXT One key target of the United Nations …

#### Why these failures happen

SciFact pairs scientific claims with abstract-level evidence. BM25 often succeeds when claim tokens overlap heavily with abstracts, but fails on paraphrased claims, negation, and statistical evidence phrased differently from the gold paper. Dense retrieval recovers some paraphrases via semantic similarity, yet can still miss when the gold abstract shares little surface form and the embedding space under-represents niche biomedical entities.

For **T-KEIR**, failures additionally reflect hybrid-rank trade-offs (lexical vs embedding weights), query analysis term selection, and embedding-provider domain coverage — not only raw lexical overlap.

## Method notes

1. Datasets are cached under `./datasets/{name}/` via `beir.util.download_and_unzip`.
2. **T-KEIR (retrieval only):** BEIR docs → full NLP (`chunking` + structural `chunk-questions`) → embed + index → `QueryAnalyzerTask` + Vespa hybrid top-100. **Answer generation is disabled** (`RetrievalEmbeddingClient` rejects `LLM.generate`). Multi-chunk hits get a mild evidence boost. Corpus is reindexed per dataset for a clean ranking surface.
3. Local BM25: `rank_bm25.BM25Okapi` over title+text.
4. Local dense: BEIR `DenseRetrievalExactSearch` + `SentenceBERT('sentence-transformers/all-MiniLM-L6-v2')`, cosine similarity.
5. Metrics: NDCG@10, MAP@100, Recall@100 via `EvaluateRetrieval.evaluate`.
6. Leaderboard: published BEIR BM25 / SPLADE / Contriever NDCG@10. **Best published** = max of those three. **Gap to best** = system_score − best_score (negative = behind the leaderboard leader).
7. Failure types: false positives (top-3 irrelevant), false negatives (gold missing from top-100), near misses (gold ranked 11–100).
