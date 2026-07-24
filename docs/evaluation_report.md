# BEIR Retrieval Evaluation Report

_Generated 2026-07-24 04:39 UTC_

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
| SciFact | SPLADE | 0.699 | 0.689 | -0.010 | 0.652 | -0.047 | 0.645 | -0.054 |
| FiQA-2018 | SPLADE | 0.342 | 0.303 | -0.039 | 0.218 | -0.124 | 0.369 | +0.027 |
| ArguAna | SPLADE | 0.472 | 0.449 | -0.023 | 0.384 | -0.088 | 0.502 | +0.030 |

### Published baselines (reference)

| Dataset | BEIR BM25 | SPLADE | Contriever | **Best** |
|---|---:|---:|---:|---|
| SciFact | 0.665 | 0.699 | 0.677 | **SPLADE** (0.699) |
| FiQA-2018 | 0.236 | 0.342 | 0.329 | **SPLADE** (0.342) |
| ArguAna | 0.397 | 0.472 | 0.435 | **SPLADE** (0.472) |

### Gap to best published system (detail)

| Dataset | Best system | Best NDCG@10 | T-KEIR gap | Local BM25 gap | Local Dense gap | T-KEIR vs BM25 | T-KEIR vs SPLADE | T-KEIR vs Contriever |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| SciFact | SPLADE | 0.699 | -0.010 | -0.047 | -0.054 | +0.024 | -0.010 | +0.012 |
| FiQA-2018 | SPLADE | 0.342 | -0.039 | -0.124 | +0.027 | +0.067 | -0.039 | -0.026 |
| ArguAna | SPLADE | 0.472 | -0.023 | -0.088 | +0.030 | +0.052 | -0.023 | +0.014 |

## Per-dataset metrics

### SciFact (`scifact`)

- Corpus size: **5,183** documents  
- Test queries: **300**
- Dense baseline model: `sentence-transformers/all-MiniLM-L6-v2`
- **Best published system:** `SPLADE` (NDCG@10 = 0.699)
- T-KEIR status: **ok** (QueryAnalyzer + Vespa hybrid)
- **T-KEIR gap to best (SPLADE):** `-0.010` (T-KEIR 0.689 − 0.699)
- Local BM25 gap to best: `-0.047`
- Local Dense gap to best: `-0.054`

| Metric | T-KEIR | Local BM25 | Local Dense |
|---|---:|---:|---:|
| NDCG@10 | 0.689 | 0.652 | 0.645 |
| MAP@100 | 0.661 | 0.613 | 0.603 |
| Recall@100 | 0.772 | 0.873 | 0.925 |

#### Error analysis (T-KEIR)

- **False positive** — query `1`: «0-dimensional biomaterials show inductive properties.»
  - Rank #1 doc `393001` (score=0.0557) is not relevant. Snippet: High Km soluble 5'-nucleotidase from human placenta. Properties and allosteric regulation by IMP and ATP. A human place…
- **False negative** — query `1`: «0-dimensional biomaterials show inductive properties.»
  - Gold doc `31715818` completely missed (not in top-100). Snippet: New opportunities: the use of nanotechnologies to manipulate and track stem cells. Nanotechnologies are emerging platfo…
- **Near miss** — query `508`: «Hematopoietic Stem Cell purification reaches purity rate of up to 50%.»
  - Gold doc `13980338` retrieved at rank 25/100 (missed NDCG@10). Snippet: Combined Single-Cell Functional and Gene Expression Analysis Resolves Heterogeneity within Stem Cell Populations Hetero…

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

### FiQA-2018 (`fiqa`)

- Corpus size: **57,638** documents  
- Test queries: **648**
- Dense baseline model: `sentence-transformers/all-MiniLM-L6-v2`
- **Best published system:** `SPLADE` (NDCG@10 = 0.342)
- T-KEIR status: **ok** (QueryAnalyzer + Vespa hybrid)
- **T-KEIR gap to best (SPLADE):** `-0.039` (T-KEIR 0.303 − 0.342)
- Local BM25 gap to best: `-0.124`
- Local Dense gap to best: `+0.027`

| Metric | T-KEIR | Local BM25 | Local Dense |
|---|---:|---:|---:|
| NDCG@10 | 0.303 | 0.218 | 0.369 |
| MAP@100 | 0.249 | 0.172 | 0.310 |
| Recall@100 | 0.353 | 0.475 | 0.706 |

#### Error analysis (T-KEIR)

- **False positive** — query `8`: «How to deposit a cheque issued to an associate in my business into my business account?»
  - Rank #2 doc `508754` (score=0.7570) is not relevant. Snippet: "I have checked with Bank of America, and they say the ONLY way to cash (or deposit, or otherwise get access to the fun…
- **False negative** — query `8`: «How to deposit a cheque issued to an associate in my business into my business account?»
  - Gold doc `566392` completely missed (not in top-100). Snippet: Have the check reissued to the proper payee.
- **Near miss** — query `89`: «How can I deposit a check made out to my business into my personal account?»
  - Gold doc `64556` retrieved at rank 22/100 (missed NDCG@10). Snippet: If you're a sole proprietor there's no reason to have a separate business account, as long as you keep adequate records…

#### Error analysis (Local BM25)

- **False positive** — query `8`: «How to deposit a cheque issued to an associate in my business into my business account?»
  - Rank #2 doc `261856` (score=41.8126) is not relevant. Snippet: Banks has to complete KYC. In case you want to open a bank account, most will ask for proof of address. I also feel it …
- **False negative** — query `8`: «How to deposit a cheque issued to an associate in my business into my business account?»
  - Gold doc `566392` completely missed (not in top-100). Snippet: Have the check reissued to the proper payee.
- **Near miss** — query `104`: «Investing/business with other people's money: How does it work?»
  - Gold doc `575869` retrieved at rank 99/100 (missed NDCG@10). Snippet: "Basically, you either borrow money, or get other people to invest in your business by buying stock or something analog…

#### Error analysis (Local Dense)

- **False positive** — query `8`: «How to deposit a cheque issued to an associate in my business into my business account?»
  - Rank #2 doc `508754` (score=0.5982) is not relevant. Snippet: "I have checked with Bank of America, and they say the ONLY way to cash (or deposit, or otherwise get access to the fun…
- **False negative** — query `8`: «How to deposit a cheque issued to an associate in my business into my business account?»
  - Gold doc `566392` completely missed (not in top-100). Snippet: Have the check reissued to the proper payee.
- **Near miss** — query `26`: «Applying for and receiving business credit»
  - Gold doc `285255` retrieved at rank 64/100 (missed NDCG@10). Snippet: "I'm afraid the great myth of limited liability companies is that all such vehicles have instant access to credit. Limi…

#### Why these failures happen

FiQA questions use specialized financial jargon (tickers, instruments, accounting terms). Lexical mismatch is the dominant failure mode: queries mention colloquial investor language while gold posts use formal or acronym-heavy phrasing. Dense models help when wording differs but sense is shared; they still struggle with numeral-heavy or ticker-specific questions where the correct answer document is short and dominated by symbols rather than natural language.

For **T-KEIR**, failures additionally reflect hybrid-rank trade-offs (lexical vs embedding weights), query analysis term selection, and embedding-provider domain coverage — not only raw lexical overlap.

### ArguAna (`arguana`)

- Corpus size: **8,674** documents  
- Test queries: **1,406**
- Dense baseline model: `sentence-transformers/all-MiniLM-L6-v2`
- **Best published system:** `SPLADE` (NDCG@10 = 0.472)
- T-KEIR status: **ok** (QueryAnalyzer + Vespa hybrid)
- **T-KEIR gap to best (SPLADE):** `-0.023` (T-KEIR 0.449 − 0.472)
- Local BM25 gap to best: `-0.088`
- Local Dense gap to best: `+0.030`

| Metric | T-KEIR | Local BM25 | Local Dense |
|---|---:|---:|---:|
| NDCG@10 | 0.449 | 0.384 | 0.502 |
| MAP@100 | 0.393 | 0.320 | 0.422 |
| Recall@100 | 0.680 | 0.841 | 0.977 |

#### Error analysis (T-KEIR)

- **False positive** — query `test-environment-aeghhgwpe-pro02a`: «Being vegetarian helps the environment Becoming a vegetarian is an environmentally friendly thing to do. Modern farming is one of the main sources of pollution…»
  - Rank #2 doc `validation-society-gfhbcimrst-con05a` (score=0.0550) is not relevant. Snippet: Autonomy (Please note that this argument cannot be run in conjunction with argument four as they are contradictory) 42%…
- **False negative** — query `test-environment-aeghhgwpe-con01a`: «Humans can choose their own nutrition plan Humans are omnivores – we are meant to eat both meat and plants. Like our early ancestors we have sharp canine teeth…»
  - Gold doc `test-environment-aeghhgwpe-con01b` completely missed (not in top-100). Snippet: animals environment general health health general weight philosophy ethics Human evolved as omnivores over thousands of…
- **Near miss** — query `test-environment-assgbatj-pro05a`: «It would send out a consistent message Most countries have animal welfare laws to prevent animal cruelty but have laws like the UK’s Animals (Scientific Proced…»
  - Gold doc `test-environment-assgbatj-pro05b` retrieved at rank 13/100 (missed NDCG@10). Snippet: animals science science general ban animal testing junior There is a moral difference between harm for the sake of harm…

#### Error analysis (Local BM25)

- **False positive** — query `test-environment-aeghhgwpe-pro02a`: «Being vegetarian helps the environment Becoming a vegetarian is an environmentally friendly thing to do. Modern farming is one of the main sources of pollution…»
  - Rank #2 doc `test-environment-aeghhgwpe-pro03b` (score=918.6280) is not relevant. Snippet: animals environment general health health general weight philosophy ethics The key to good health is a balanced diet, n…
- **False negative** — query `test-environment-assgbatj-con04a`: «Animal research is only used when it’s needed EU member states and the US have laws to stop animals being used for research if there is any alternative. The 3R…»
  - Gold doc `test-environment-assgbatj-con04b` completely missed (not in top-100). Snippet: animals science science general ban animal testing junior Not every country has laws like the EU or the US. In countrie…
- **Near miss** — query `test-environment-aeghhgwpe-con01a`: «Humans can choose their own nutrition plan Humans are omnivores – we are meant to eat both meat and plants. Like our early ancestors we have sharp canine teeth…»
  - Gold doc `test-environment-aeghhgwpe-con01b` retrieved at rank 37/100 (missed NDCG@10). Snippet: animals environment general health health general weight philosophy ethics Human evolved as omnivores over thousands of…

#### Error analysis (Local Dense)

- **False positive** — query `test-environment-aeghhgwpe-pro02a`: «Being vegetarian helps the environment Becoming a vegetarian is an environmentally friendly thing to do. Modern farming is one of the main sources of pollution…»
  - Rank #2 doc `test-environment-aeghhgwpe-pro01b` (score=0.6577) is not relevant. Snippet: animals environment general health health general weight philosophy ethics There is a great moral difference between hu…
- **False negative** — query `test-sport-otshwbe2uuyt-pro01a`: «Europe must not give approval to this regime. Viktor Yanukovych fairly came to power in 2010 however since then he has set about attacking the country’s fragil…»
  - Gold doc `test-sport-otshwbe2uuyt-pro01b` completely missed (not in top-100). Snippet: olympics team sports house would boycott euro 2012 ukraine unless yulia timoshenko Attending football matches is not gi…
- **Near miss** — query `test-environment-aeghhgwpe-con03a`: «Survival of the fittest It is natural for human beings to farm, kill, and eat other species. In the wild there is a brutal struggle for existence as is shown b…»
  - Gold doc `test-environment-aeghhgwpe-con03b` retrieved at rank 40/100 (missed NDCG@10). Snippet: animals environment general health health general weight philosophy ethics To suggest that battery farms are in some wa…

#### Why these failures happen

ArguAna is counterargument retrieval: the relevant document is often an opposing stance that deliberately avoids repeating the query's key phrases. Pure lexical overlap therefore systematically under-ranks true counterarguments and promotes thematically similar but stance-aligned essays (false positives). Dense retrieval mitigates some lexical gaps, but stance polarity and argumentative structure are not encoded strongly by generic sentence embeddings, so many gold counterarguments remain buried outside the top ranks.

For **T-KEIR**, failures additionally reflect hybrid-rank trade-offs (lexical vs embedding weights), query analysis term selection, and embedding-provider domain coverage — not only raw lexical overlap.

## Method notes

1. Datasets are cached under `./datasets/{name}/` via `beir.util.download_and_unzip`.
2. **T-KEIR (retrieval only):** BEIR docs → full NLP (`chunking` + structural `chunk-questions`) → embed + index → `QueryAnalyzerTask` + Vespa hybrid top-100. **Answer generation is disabled** (`RetrievalEmbeddingClient` rejects `LLM.generate`). Multi-chunk hits get a mild evidence boost. Corpus is reindexed per dataset for a clean ranking surface.
3. Local BM25: `rank_bm25.BM25Okapi` over title+text.
4. Local dense: BEIR `DenseRetrievalExactSearch` + `SentenceBERT('sentence-transformers/all-MiniLM-L6-v2')`, cosine similarity.
5. Metrics: NDCG@10, MAP@100, Recall@100 via `EvaluateRetrieval.evaluate`.
6. Leaderboard: published BEIR BM25 / SPLADE / Contriever NDCG@10. **Best published** = max of those three. **Gap to best** = system_score − best_score (negative = behind the leaderboard leader).
7. Failure types: false positives (top-3 irrelevant), false negatives (gold missing from top-100), near misses (gold ranked 11–100).
