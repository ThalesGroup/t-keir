# BEIR Retrieval Evaluation Report

_Generated 2026-07-27 14:28 UTC_

## Overview

This report benchmarks three retrieval systems on BEIR datasets:

1. **T-KEIR retrieval only** — `thot.tools.eval.hybrid_retrieve.retrieve_hybrid`: BGE-M3 dense+sparse **RRF-fused with BM25**, then **ColBERT MaxSim** rerank via `thot.tools.search.rerank.colbert_rerank` (same as Vespa passage search stage-2). Answer generation is **not** run. (BGE sparse ≠ SPLADE; Local Dense alone sits within ~0.003 of SPLADE on SciFact.)
2. **Local BM25 (Okapi)** — in-memory `rank_bm25` baseline (`score_bm25`).
3. **Local dense+sparse** — BGE-M3 FlagEmbedding (`score_bge_hybrid`, `bge-m3`), same encode path as ingest / T-KEIR first-stage.

Retrieval cut-off is **top-100**. Metrics use `beir.retrieval.evaluation.EvaluateRetrieval` (pytrec_eval).

> **Leaderboard:** SciFact / FiQA-2018 / ArguAna NDCG@10 values for BM25, SPLADE, and Contriever are the published BEIR reference scores. Local BM25 is not Elasticsearch-identical; local BGE-M3 dense+sparse is not Contriever. **T-KEIR** is the system under evaluation against that public leaderboard.

## Leaderboard comparison (NDCG@10)

Gap = system NDCG@10 − **best published** NDCG@10 on that dataset (among BEIR BM25, SPLADE, Contriever). Negative ⇒ behind the leaderboard leader.

| Dataset | Best published | Best score | **T-KEIR** | Gap T-KEIR → best | Local BM25 | Gap BM25 → best | Local Dense | Gap Dense → best |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| SciFact | SPLADE | 0.699 | 0.708 | +0.009 | 0.652 | -0.047 | 0.696 | -0.003 |
| FiQA-2018 | SPLADE | 0.342 | 0.349 | +0.007 | 0.218 | -0.124 | 0.403 | +0.061 |
| ArguAna | SPLADE | 0.472 | 0.464 | -0.008 | 0.384 | -0.088 | 0.529 | +0.057 |

### Published baselines (reference)

| Dataset | BEIR BM25 | SPLADE | Contriever | **Best** |
|---|---:|---:|---:|---|
| SciFact | 0.665 | 0.699 | 0.677 | **SPLADE** (0.699) |
| FiQA-2018 | 0.236 | 0.342 | 0.329 | **SPLADE** (0.342) |
| ArguAna | 0.397 | 0.472 | 0.435 | **SPLADE** (0.472) |

### Gap to best published system (detail)

| Dataset | Best system | Best NDCG@10 | T-KEIR gap | Local BM25 gap | Local Dense gap | T-KEIR vs BM25 | T-KEIR vs SPLADE | T-KEIR vs Contriever |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| SciFact | SPLADE | 0.699 | +0.009 | -0.047 | -0.003 | +0.043 | +0.009 | +0.031 |
| FiQA-2018 | SPLADE | 0.342 | +0.007 | -0.124 | +0.061 | +0.113 | +0.007 | +0.020 |
| ArguAna | SPLADE | 0.472 | -0.008 | -0.088 | +0.057 | +0.067 | -0.008 | +0.029 |

## Per-dataset metrics

### SciFact (`scifact`)

- Corpus size: **5,183** documents  
- Test queries: **300**
- BGE-M3 dense+sparse baseline: `bge-m3` (local `resources/modeling/net/bge-m3`)
- **Best published system:** `SPLADE` (NDCG@10 = 0.699)
- T-KEIR status: **ok** (`hybrid_retrieve.retrieve_hybrid`)
- **T-KEIR gap to best (SPLADE):** `+0.009` (T-KEIR 0.708 − 0.699)
- Local BM25 gap to best: `-0.047`
- Local Dense gap to best: `-0.003`

| Metric | T-KEIR | Local BM25 | Local Dense |
|---|---:|---:|---:|
| NDCG@10 | 0.708 | 0.652 | 0.696 |
| MAP@100 | 0.672 | 0.613 | 0.654 |
| Recall@100 | 0.940 | 0.873 | 0.930 |

#### Error analysis (T-KEIR)

**1. False positive** — query id `1`

**Query**

> 0-dimensional biomaterials show inductive properties.

**Observation:** Rank #1 doc `40212412` (score=0.9646) is not relevant. Snippet: Periosteal bone formation--a neglected determinant of bone strength. Life forms that have low body mass can hunt for food on the undersurface of branches or along shear cliff faces quite unperturbed …

**Analysis:** Irrelevant document ranked #1 (score=0.9646) despite not being in the qrels. Lexical coverage vs query: **33%** (2/6 query tokens). Shared: `dimensional`, `properties`. Query tokens absent from this hit: `0`, `biomaterials`, `inductive`, `show`. Best gold `31715818` covers **0%** of query tokens (shared: _(none)_; missing on gold: `0`, `biomaterials`, `dimensional`, `inductive`, `properties`, `show`). The false positive matches the query surface form as well as or better than the gold — ranking rewarded topical / lexical similarity rather than labeled relevance (paraphrase, stance, or answer-specific content).

**2. False positive** — query id `3`

**Query**

> 1,000 genomes project enables mapping of genetic sequence variation consisting of rare variants with larger penetrance effects than common variants.

**Observation:** Rank #1 doc `2739854` (score=0.9941) is not relevant. Snippet: Rare and common variants: twenty arguments Genome-wide association studies have greatly improved our understanding of the genetic basis of disease risk. The fact that they tend not to identify more t…

**Analysis:** Irrelevant document ranked #1 (score=0.9941) despite not being in the qrels. Lexical coverage vs query: **32%** (6/19 query tokens). Shared: `common`, `genetic`, `of`, `rare`, `than`, `variants`. Query tokens absent from this hit: `000`, `1`, `consisting`, `effects`, `enables`, `genomes`, `larger`, `mapping`, `penetrance`, `project`, `sequence`, `variation` … (+1 more). Best gold `14717500` covers **42%** of query tokens (shared: `000`, `common`, `genetic`, `of`, `rare`, `than`, `variants`, `with`; missing on gold: `1`, `consisting`, `effects`, `enables`, `genomes`, `larger`, `mapping`, `penetrance`, `project`, `sequence`, `variation`). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**3. False positive** — query id `5`

**Query**

> 1/2000 in UK have abnormal PrP positivity.

**Observation:** Rank #2 doc `18617259` (score=0.9026) is not relevant. Snippet: Research Letters We report a case of preclinical variant Creutzfeldt-Jakob disease (vCJD) in a patient who died from a non-neurological disorder 5 years after receiving a blood transfusion from a don…

**Analysis:** Irrelevant document ranked #2 (score=0.9026) despite not being in the qrels. Lexical coverage vs query: **50%** (4/8 query tokens). Shared: `have`, `in`, `prp`, `uk`. Query tokens absent from this hit: `1`, `2000`, `abnormal`, `positivity`. Best gold `13734012` covers **62%** of query tokens (shared: `abnormal`, `have`, `in`, `prp`, `uk`; missing on gold: `1`, `2000`, `positivity`). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**4. False negative** — query id `1`

**Query**

> 0-dimensional biomaterials show inductive properties.

**Observation:** Gold doc `31715818` completely missed (not in top-100). Snippet: New opportunities: the use of nanotechnologies to manipulate and track stem cells. Nanotechnologies are emerging platforms that could be useful in measuring, understanding, and manipulating stem cell…

**Analysis:** Gold `31715818` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **0%** (shared: _(none)_; missing on gold: `0`, `biomaterials`, `dimensional`, `inductive`, `properties`, `show`). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `40212412` (score=0.9646, coverage=33%); #2 `13231899` (score=0.8972, coverage=17%); #3 `825728` (score=0.8530, coverage=33%).

**5. False negative** — query id `132`

**Query**

> Aspirin inhibits the production of PGE2.

**Observation:** Gold doc `7975937` completely missed (not in top-100). Snippet: Cyclooxygenase-Dependent Tumor Growth through Evasion of Immunity The mechanisms by which melanoma and other cancer cells evade anti-tumor immunity remain incompletely understood. Here, we show that …

**Analysis:** Gold `7975937` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **50%** (shared: `of`, `production`, `the`; missing on gold: `aspirin`, `inhibits`, `pge2`). Several distinctive query tokens never appear in the gold text, so pure lexical matching under-weights the correct doc. Top retrieved instead: #1 `27615329` (score=0.9999, coverage=50%); #2 `6945691` (score=0.9852, coverage=67%); #3 `58006489` (score=0.9851, coverage=50%).

**6. False negative** — query id `133`

**Query**

> Assembly of invadopodia is triggered by focal generation of phosphatidylinositol-3,4-biphosphate and the activation of the nonreceptor tyrosine kinase Src.

**Observation:** Gold doc `38485364` completely missed (not in top-100). Snippet: The adaptor protein Tks5/Fish is required for podosome formation and function, and for the protease-driven invasion of cancer cells. Tks5/Fish is a scaffolding protein with five SH3 domains and one P…

**Analysis:** Gold `38485364` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **26%** (shared: `and`, `is`, `of`, `src`, `the`; missing on gold: `3`, `4`, `activation`, `assembly`, `biphosphate`, `by`, `focal`, `generation`, `invadopodia`, `kinase`, `nonreceptor`, `phosphatidylinositol` … (+2 more)). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `16280642` (score=1.0000, coverage=47%); #2 `35660758` (score=0.9409, coverage=58%); #3 `86694016` (score=0.9288, coverage=42%).

**7. Near miss** — query id `13`

**Query**

> 5% of perinatal mortality is due to low birth weight.

**Observation:** Gold doc `1606628` retrieved at rank 16/100 (missed NDCG@10). Snippet: Estimates of global prevalence of childhood underweight in 1990 and 2015. CONTEXT One key target of the United Nations Millennium Development goals is to reduce the prevalence of underweight among ch…

**Analysis:** Gold `1606628` retrieved at rank **16**/100 (score=0.7740) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **60%** (shared: `5`, `due`, `is`, `of`, `to`, `weight`; missing: `birth`, `low`, `mortality`, `perinatal`). Rank-1 was `7662395` (score=0.9911, coverage=60% vs gold 60%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**8. Near miss** — query id `36`

**Query**

> A deficiency of vitamin B12 increases blood levels of homocysteine.

**Observation:** Gold doc `5152028` retrieved at rank 25/100 (missed NDCG@10). Snippet: Folic acid improves endothelial function in coronary artery disease via mechanisms largely independent of homocysteine lowering. BACKGROUND Homocysteine is a risk factor for coronary artery disease (…

**Analysis:** Gold `5152028` retrieved at rank **25**/100 (score=0.7770) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **33%** (shared: `a`, `homocysteine`, `of`; missing: `b12`, `blood`, `deficiency`, `increases`, `levels`, `vitamin`). Rank-1 was `18557974` (score=1.0000, coverage=67% vs gold 33%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**9. Near miss** — query id `128`

**Query**

> Arterioles have a larger lumen diameter than venules.

**Observation:** Gold doc `8290953` retrieved at rank 29/100 (missed NDCG@10). Snippet: Scaffold-based three-dimensional human fibroblast culture provides a structural matrix that supports angiogenesis in infarcted heart tissue. BACKGROUND We have developed techniques to implant angioge…

**Analysis:** Gold `8290953` retrieved at rank **29**/100 (score=0.6171) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **62%** (shared: `a`, `arterioles`, `have`, `than`, `venules`; missing: `diameter`, `larger`, `lumen`). Rank-1 was `1122279` (score=0.9988, coverage=38% vs gold 62%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.


#### Error analysis (Local BM25)

**1. False positive** — query id `1`

**Query**

> 0-dimensional biomaterials show inductive properties.

**Observation:** Rank #1 doc `10608397` (score=10.1725) is not relevant. Snippet: High-performance neuroprosthetic control by an individual with tetraplegia. BACKGROUND Paralysis or amputation of an arm results in the loss of the ability to orient the hand and grasp, manipulate, a…

**Analysis:** Irrelevant document ranked #1 (score=10.1725) despite not being in the qrels. Lexical coverage vs query: **33%** (2/6 query tokens). Shared: `0`, `dimensional`. Query tokens absent from this hit: `biomaterials`, `inductive`, `properties`, `show`. Best gold `31715818` covers **0%** of query tokens (shared: _(none)_; missing on gold: `0`, `biomaterials`, `dimensional`, `inductive`, `properties`, `show`). The false positive matches the query surface form as well as or better than the gold — ranking rewarded topical / lexical similarity rather than labeled relevance (paraphrase, stance, or answer-specific content).

**2. False positive** — query id `3`

**Query**

> 1,000 genomes project enables mapping of genetic sequence variation consisting of rare variants with larger penetrance effects than common variants.

**Observation:** Rank #2 doc `2739854` (score=42.1567) is not relevant. Snippet: Rare and common variants: twenty arguments Genome-wide association studies have greatly improved our understanding of the genetic basis of disease risk. The fact that they tend not to identify more t…

**Analysis:** Irrelevant document ranked #2 (score=42.1567) despite not being in the qrels. Lexical coverage vs query: **32%** (6/19 query tokens). Shared: `common`, `genetic`, `of`, `rare`, `than`, `variants`. Query tokens absent from this hit: `000`, `1`, `consisting`, `effects`, `enables`, `genomes`, `larger`, `mapping`, `penetrance`, `project`, `sequence`, `variation` … (+1 more). Best gold `14717500` covers **42%** of query tokens (shared: `000`, `common`, `genetic`, `of`, `rare`, `than`, `variants`, `with`; missing on gold: `1`, `consisting`, `effects`, `enables`, `genomes`, `larger`, `mapping`, `penetrance`, `project`, `sequence`, `variation`). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**3. False positive** — query id `5`

**Query**

> 1/2000 in UK have abnormal PrP positivity.

**Observation:** Rank #2 doc `18617259` (score=19.1565) is not relevant. Snippet: Research Letters We report a case of preclinical variant Creutzfeldt-Jakob disease (vCJD) in a patient who died from a non-neurological disorder 5 years after receiving a blood transfusion from a don…

**Analysis:** Irrelevant document ranked #2 (score=19.1565) despite not being in the qrels. Lexical coverage vs query: **50%** (4/8 query tokens). Shared: `have`, `in`, `prp`, `uk`. Query tokens absent from this hit: `1`, `2000`, `abnormal`, `positivity`. Best gold `13734012` covers **62%** of query tokens (shared: `abnormal`, `have`, `in`, `prp`, `uk`; missing on gold: `1`, `2000`, `positivity`). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**4. False negative** — query id `1`

**Query**

> 0-dimensional biomaterials show inductive properties.

**Observation:** Gold doc `31715818` completely missed (not in top-100). Snippet: New opportunities: the use of nanotechnologies to manipulate and track stem cells. Nanotechnologies are emerging platforms that could be useful in measuring, understanding, and manipulating stem cell…

**Analysis:** Gold `31715818` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **0%** (shared: _(none)_; missing on gold: `0`, `biomaterials`, `dimensional`, `inductive`, `properties`, `show`). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `10608397` (score=10.1725, coverage=33%); #2 `43385013` (score=9.8617, coverage=50%); #3 `40212412` (score=9.5557, coverage=33%).

**5. False negative** — query id `132`

**Query**

> Aspirin inhibits the production of PGE2.

**Observation:** Gold doc `7975937` completely missed (not in top-100). Snippet: Cyclooxygenase-Dependent Tumor Growth through Evasion of Immunity The mechanisms by which melanoma and other cancer cells evade anti-tumor immunity remain incompletely understood. Here, we show that …

**Analysis:** Gold `7975937` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **50%** (shared: `of`, `production`, `the`; missing on gold: `aspirin`, `inhibits`, `pge2`). Several distinctive query tokens never appear in the gold text, so pure lexical matching under-weights the correct doc. Top retrieved instead: #1 `21181273` (score=23.2185, coverage=67%); #2 `6945691` (score=22.8008, coverage=67%); #3 `54482327` (score=21.0634, coverage=67%).

**6. False negative** — query id `133`

**Query**

> Assembly of invadopodia is triggered by focal generation of phosphatidylinositol-3,4-biphosphate and the activation of the nonreceptor tyrosine kinase Src.

**Observation:** Gold doc `38485364` completely missed (not in top-100). Snippet: The adaptor protein Tks5/Fish is required for podosome formation and function, and for the protease-driven invasion of cancer cells. Tks5/Fish is a scaffolding protein with five SH3 domains and one P…

**Analysis:** Gold `38485364` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **26%** (shared: `and`, `is`, `of`, `src`, `the`; missing on gold: `3`, `4`, `activation`, `assembly`, `biphosphate`, `by`, `focal`, `generation`, `invadopodia`, `kinase`, `nonreceptor`, `phosphatidylinositol` … (+2 more)). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `5270265` (score=54.3506, coverage=53%); #2 `26688294` (score=53.9626, coverage=47%); #3 `19752008` (score=53.6147, coverage=58%).

**7. Near miss** — query id `13`

**Query**

> 5% of perinatal mortality is due to low birth weight.

**Observation:** Gold doc `1606628` retrieved at rank 48/100 (missed NDCG@10). Snippet: Estimates of global prevalence of childhood underweight in 1990 and 2015. CONTEXT One key target of the United Nations Millennium Development goals is to reduce the prevalence of underweight among ch…

**Analysis:** Gold `1606628` retrieved at rank **48**/100 (score=18.5280) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **60%** (shared: `5`, `due`, `is`, `of`, `to`, `weight`; missing: `birth`, `low`, `mortality`, `perinatal`). Rank-1 was `1263446` (score=30.6219, coverage=90% vs gold 60%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**8. Near miss** — query id `36`

**Query**

> A deficiency of vitamin B12 increases blood levels of homocysteine.

**Observation:** Gold doc `5152028` retrieved at rank 31/100 (missed NDCG@10). Snippet: Folic acid improves endothelial function in coronary artery disease via mechanisms largely independent of homocysteine lowering. BACKGROUND Homocysteine is a risk factor for coronary artery disease (…

**Analysis:** Gold `5152028` retrieved at rank **31**/100 (score=20.8033) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **33%** (shared: `a`, `homocysteine`, `of`; missing: `b12`, `blood`, `deficiency`, `increases`, `levels`, `vitamin`). Rank-1 was `42441846` (score=42.5412, coverage=67% vs gold 33%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**9. Near miss** — query id `133`

**Query**

> Assembly of invadopodia is triggered by focal generation of phosphatidylinositol-3,4-biphosphate and the activation of the nonreceptor tyrosine kinase Src.

**Observation:** Gold doc `12640810` retrieved at rank 13/100 (missed NDCG@10). Snippet: Cortactin regulates cofilin and N-WASp activities to control the stages of invadopodium assembly and maturation Invadopodia are matrix-degrading membrane protrusions in invasive carcinoma cells. The …

**Analysis:** Gold `12640810` retrieved at rank **13**/100 (score=46.5274) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **37%** (shared: `3`, `and`, `assembly`, `invadopodia`, `is`, `of`, `the`; missing: `4`, `activation`, `biphosphate`, `by`, `focal`, `generation`, `kinase`, `nonreceptor`, `phosphatidylinositol`, `src`, `triggered`, `tyrosine`). Rank-1 was `5270265` (score=54.3506, coverage=53% vs gold 37%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.


#### Error analysis (Local Dense)

**1. False positive** — query id `1`

**Query**

> 0-dimensional biomaterials show inductive properties.

**Observation:** Rank #1 doc `35149431` (score=0.5758) is not relevant. Snippet: P0 glycoprotein peptides 56–71 and 180–199 dose-dependently induce acute and chronic experimental autoimmune neuritis in Lewis rats associated with epitope spreading Two synthetic peripheral nerve my…

**Analysis:** Irrelevant document ranked #1 (score=0.5758) despite not being in the qrels. Lexical coverage vs query: **0%** (0/6 query tokens). Shared: _(none)_. Query tokens absent from this hit: `0`, `biomaterials`, `dimensional`, `inductive`, `properties`, `show`. Best gold `31715818` covers **0%** of query tokens (shared: _(none)_; missing on gold: `0`, `biomaterials`, `dimensional`, `inductive`, `properties`, `show`). The false positive matches the query surface form as well as or better than the gold — ranking rewarded topical / lexical similarity rather than labeled relevance (paraphrase, stance, or answer-specific content).

**2. False positive** — query id `3`

**Query**

> 1,000 genomes project enables mapping of genetic sequence variation consisting of rare variants with larger penetrance effects than common variants.

**Observation:** Rank #1 doc `1388704` (score=0.6852) is not relevant. Snippet: The essence of SNPs. Single nucleotide polymorphisms (SNPs) are an abundant form of genome variation, distinguished from rare variations by a requirement for the least abundant allele to have a frequ…

**Analysis:** Irrelevant document ranked #1 (score=0.6852) despite not being in the qrels. Lexical coverage vs query: **26%** (5/19 query tokens). Shared: `1`, `genetic`, `of`, `rare`, `variation`. Query tokens absent from this hit: `000`, `common`, `consisting`, `effects`, `enables`, `genomes`, `larger`, `mapping`, `penetrance`, `project`, `sequence`, `than` … (+2 more). Best gold `14717500` covers **42%** of query tokens (shared: `000`, `common`, `genetic`, `of`, `rare`, `than`, `variants`, `with`; missing on gold: `1`, `consisting`, `effects`, `enables`, `genomes`, `larger`, `mapping`, `penetrance`, `project`, `sequence`, `variation`). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**3. False positive** — query id `5`

**Query**

> 1/2000 in UK have abnormal PrP positivity.

**Observation:** Rank #2 doc `7751726` (score=0.5924) is not relevant. Snippet: A feasibility study for a randomised controlled trial of the Positive Reappraisal Coping Intervention, a novel supportive technique for recurrent miscarriage INTRODUCTION Recurrent miscarriage (RM) i…

**Analysis:** Irrelevant document ranked #2 (score=0.5924) despite not being in the qrels. Lexical coverage vs query: **25%** (2/8 query tokens). Shared: `have`, `in`. Query tokens absent from this hit: `1`, `2000`, `abnormal`, `positivity`, `prp`, `uk`. Best gold `13734012` covers **62%** of query tokens (shared: `abnormal`, `have`, `in`, `prp`, `uk`; missing on gold: `1`, `2000`, `positivity`). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**4. False negative** — query id `1`

**Query**

> 0-dimensional biomaterials show inductive properties.

**Observation:** Gold doc `31715818` completely missed (not in top-100). Snippet: New opportunities: the use of nanotechnologies to manipulate and track stem cells. Nanotechnologies are emerging platforms that could be useful in measuring, understanding, and manipulating stem cell…

**Analysis:** Gold `31715818` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **0%** (shared: _(none)_; missing on gold: `0`, `biomaterials`, `dimensional`, `inductive`, `properties`, `show`). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `35149431` (score=0.5758, coverage=0%); #2 `40212412` (score=0.5703, coverage=33%); #3 `21456232` (score=0.5323, coverage=17%).

**5. False negative** — query id `128`

**Query**

> Arterioles have a larger lumen diameter than venules.

**Observation:** Gold doc `8290953` completely missed (not in top-100). Snippet: Scaffold-based three-dimensional human fibroblast culture provides a structural matrix that supports angiogenesis in infarcted heart tissue. BACKGROUND We have developed techniques to implant angioge…

**Analysis:** Gold `8290953` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **62%** (shared: `a`, `arterioles`, `have`, `than`, `venules`; missing on gold: `diameter`, `larger`, `lumen`). Several distinctive query tokens never appear in the gold text, so pure lexical matching under-weights the correct doc. Top retrieved instead: #1 `12549585` (score=0.5750, coverage=38%); #2 `79447` (score=0.5606, coverage=25%); #3 `25175997` (score=0.5595, coverage=38%).

**6. False negative** — query id `132`

**Query**

> Aspirin inhibits the production of PGE2.

**Observation:** Gold doc `7975937` completely missed (not in top-100). Snippet: Cyclooxygenase-Dependent Tumor Growth through Evasion of Immunity The mechanisms by which melanoma and other cancer cells evade anti-tumor immunity remain incompletely understood. Here, we show that …

**Analysis:** Gold `7975937` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **50%** (shared: `of`, `production`, `the`; missing on gold: `aspirin`, `inhibits`, `pge2`). Several distinctive query tokens never appear in the gold text, so pure lexical matching under-weights the correct doc. Top retrieved instead: #1 `9159125` (score=0.6722, coverage=67%); #2 `2443495` (score=0.6651, coverage=50%); #3 `58006489` (score=0.6570, coverage=50%).

**7. Near miss** — query id `13`

**Query**

> 5% of perinatal mortality is due to low birth weight.

**Observation:** Gold doc `1606628` retrieved at rank 11/100 (missed NDCG@10). Snippet: Estimates of global prevalence of childhood underweight in 1990 and 2015. CONTEXT One key target of the United Nations Millennium Development goals is to reduce the prevalence of underweight among ch…

**Analysis:** Gold `1606628` retrieved at rank **11**/100 (score=0.5732) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **60%** (shared: `5`, `due`, `is`, `of`, `to`, `weight`; missing: `birth`, `low`, `mortality`, `perinatal`). Rank-1 was `1263446` (score=0.6934, coverage=90% vs gold 60%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**8. Near miss** — query id `36`

**Query**

> A deficiency of vitamin B12 increases blood levels of homocysteine.

**Observation:** Gold doc `5152028` retrieved at rank 19/100 (missed NDCG@10). Snippet: Folic acid improves endothelial function in coronary artery disease via mechanisms largely independent of homocysteine lowering. BACKGROUND Homocysteine is a risk factor for coronary artery disease (…

**Analysis:** Gold `5152028` retrieved at rank **19**/100 (score=0.5297) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **33%** (shared: `a`, `homocysteine`, `of`; missing: `b12`, `blood`, `deficiency`, `increases`, `levels`, `vitamin`). Rank-1 was `18557974` (score=0.7042, coverage=67% vs gold 33%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**9. Near miss** — query id `70`

**Query**

> Activation of PPM1D suppresses p53 function.

**Observation:** Gold doc `4414547` retrieved at rank 17/100 (missed NDCG@10). Snippet: Mosaic PPM1D mutations are associated with predisposition to breast and ovarian cancer Improved sequencing technologies offer unprecedented opportunities for investigating the role of rare genetic va…

**Analysis:** Gold `4414547` retrieved at rank **17**/100 (score=0.6216) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **67%** (shared: `function`, `of`, `p53`, `ppm1d`; missing: `activation`, `suppresses`). Rank-1 was `9483851` (score=0.7000, coverage=33% vs gold 67%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.


#### Why these failures happen

SciFact pairs scientific claims with abstract-level evidence. BM25 often succeeds when claim tokens overlap heavily with abstracts, but fails on paraphrased claims, negation, and statistical evidence phrased differently from the gold paper. Dense retrieval recovers some paraphrases via semantic similarity, yet can still miss when the gold abstract shares little surface form and the embedding space under-represents niche biomedical entities.

For **T-KEIR**, failures additionally reflect RRF fusion trade-offs (BGE vs BM25 ranks), ColBERT MaxSim rerank errors, and domain paraphrase gaps — not only raw lexical overlap.

### FiQA-2018 (`fiqa`)

- Corpus size: **57,638** documents  
- Test queries: **648**
- BGE-M3 dense+sparse baseline: `bge-m3` (local `resources/modeling/net/bge-m3`)
- **Best published system:** `SPLADE` (NDCG@10 = 0.342)
- T-KEIR status: **ok** (`hybrid_retrieve.retrieve_hybrid`)
- **T-KEIR gap to best (SPLADE):** `+0.007` (T-KEIR 0.349 − 0.342)
- Local BM25 gap to best: `-0.124`
- Local Dense gap to best: `+0.061`

| Metric | T-KEIR | Local BM25 | Local Dense |
|---|---:|---:|---:|
| NDCG@10 | 0.349 | 0.218 | 0.403 |
| MAP@100 | 0.295 | 0.172 | 0.342 |
| Recall@100 | 0.663 | 0.475 | 0.688 |

#### Error analysis (T-KEIR)

**1. False positive** — query id `8`

**Query**

> How to deposit a cheque issued to an associate in my business into my business account?

**Observation:** Rank #2 doc `590102` (score=0.9097) is not relevant. Snippet: When a business asks me to make out a cheque to a person rather than the business name, I take that as a red flag. Frankly it usually means that the person doesn't want the money going through their …

**Analysis:** Irrelevant document ranked #2 (score=0.9097) despite not being in the qrels. Lexical coverage vs query: **54%** (7/13 query tokens). Shared: `a`, `account`, `an`, `business`, `cheque`, `in`, `to`. Query tokens absent from this hit: `associate`, `deposit`, `how`, `into`, `issued`, `my`. Best gold `65404` covers **62%** of query tokens (shared: `a`, `account`, `associate`, `business`, `cheque`, `deposit`, `in`, `to`; missing on gold: `an`, `how`, `into`, `issued`, `my`). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**2. False positive** — query id `15`

**Query**

> Can I send a money order from USPS as a business?

**Observation:** Rank #1 doc `224000` (score=0.9906) is not relevant. Snippet: "A money order is basically a pre-paid check. The physical cash would probably get deposited into a ""master"" custodial bank account. Each money order has a different bank account number on the chec…

**Analysis:** Irrelevant document ranked #1 (score=0.9906) despite not being in the qrels. Lexical coverage vs query: **60%** (6/10 query tokens). Shared: `a`, `as`, `can`, `money`, `order`, `usps`. Query tokens absent from this hit: `business`, `from`, `i`, `send`. Best gold `325273` covers **70%** of query tokens (shared: `a`, `as`, `business`, `can`, `from`, `money`, `order`; missing on gold: `i`, `send`, `usps`). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**3. False positive** — query id `18`

**Query**

> 1 EIN doing business under multiple business names

**Observation:** Rank #1 doc `377152` (score=1.0000) is not relevant. Snippet: "According to IRS Publication 1635, Understanding your EIN (PDF), under ""What is an EIN?"" on page 2: Caution: An EIN is for use in connection with your business activities only. Do not use your EIN…

**Analysis:** Irrelevant document ranked #1 (score=1.0000) despite not being in the qrels. Lexical coverage vs query: **43%** (3/7 query tokens). Shared: `business`, `ein`, `under`. Query tokens absent from this hit: `1`, `doing`, `multiple`, `names`. Best gold `88124` covers **29%** of query tokens (shared: `ein`, `under`; missing on gold: `1`, `business`, `doing`, `multiple`, `names`). The false positive matches the query surface form as well as or better than the gold — ranking rewarded topical / lexical similarity rather than labeled relevance (paraphrase, stance, or answer-specific content).

**4. False negative** — query id `8`

**Query**

> How to deposit a cheque issued to an associate in my business into my business account?

**Observation:** Gold doc `566392` completely missed (not in top-100). Snippet: Have the check reissued to the proper payee.

**Analysis:** Gold `566392` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **8%** (shared: `to`; missing on gold: `a`, `account`, `an`, `associate`, `business`, `cheque`, `deposit`, `how`, `in`, `into`, `issued`, `my`). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `65404` (score=1.0000, coverage=62%); #2 `590102` (score=0.9097, coverage=54%); #3 `508754` (score=0.8919, coverage=62%).

**5. False negative** — query id `34`

**Query**

> 401k Transfer After Business Closure

**Observation:** Gold doc `599545` completely missed (not in top-100). Snippet: You should probably consult an attorney. However, if the owner was a corporation/LLC and it has been officially dissolved, you can provide an evidence of that from your State's department of State/Co…

**Analysis:** Gold `599545` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **0%** (shared: _(none)_; missing on gold: `401k`, `after`, `business`, `closure`, `transfer`). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `154839` (score=0.9461, coverage=60%); #2 `122114` (score=0.9426, coverage=40%); #3 `64459` (score=0.9195, coverage=60%).

**6. False negative** — query id `42`

**Query**

> What are the ins/outs of writing equipment purchases off as business expenses in a home based business?

**Observation:** Gold doc `327263` completely missed (not in top-100). Snippet: First of all, Dilip's answer explains well how the business deductions generally work. For most (big) expenses you depreciate it. However, in some cases you need to capitalize it, which is another ac…

**Analysis:** Gold `327263` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **35%** (shared: `business`, `expenses`, `in`, `of`, `the`, `what`; missing on gold: `a`, `are`, `as`, `based`, `equipment`, `home`, `ins`, `off`, `outs`, `purchases`, `writing`). Several distinctive query tokens never appear in the gold text, so pure lexical matching under-weights the correct doc. Top retrieved instead: #1 `283079` (score=0.9917, coverage=59%); #2 `88967` (score=0.9484, coverage=65%); #3 `581265` (score=0.9418, coverage=65%).

**7. Near miss** — query id `15`

**Query**

> Can I send a money order from USPS as a business?

**Observation:** Gold doc `325273` retrieved at rank 15/100 (missed NDCG@10). Snippet: Sure you can. You can fill in whatever you want in the From section of a money order, so your business name and address would be fine. The price only includes the money order itself. You can hand del…

**Analysis:** Gold `325273` retrieved at rank **15**/100 (score=0.7361) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **70%** (shared: `a`, `as`, `business`, `can`, `from`, `money`, `order`; missing: `i`, `send`, `usps`). Rank-1 was `224000` (score=0.9906, coverage=60% vs gold 70%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**8. Near miss** — query id `26`

**Query**

> Applying for and receiving business credit

**Observation:** Gold doc `285255` retrieved at rank 44/100 (missed NDCG@10). Snippet: "I'm afraid the great myth of limited liability companies is that all such vehicles have instant access to credit. Limited liability on a company with few physical assets to underwrite the loan, or w…

**Analysis:** Gold `285255` retrieved at rank **44**/100 (score=0.0594) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **50%** (shared: `business`, `credit`, `for`; missing: `and`, `applying`, `receiving`). Rank-1 was `176284` (score=1.0000, coverage=83% vs gold 50%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**9. Near miss** — query id `42`

**Query**

> What are the ins/outs of writing equipment purchases off as business expenses in a home based business?

**Observation:** Gold doc `331981` retrieved at rank 33/100 (missed NDCG@10). Snippet: Keep this rather corny acronym in mind. Business expenses must be CORN: As other posters have already pointed out, certain expenses that are capital items (computers, furniture, etc.) must be depreci…

**Analysis:** Gold `331981` retrieved at rank **33**/100 (score=0.6713) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **53%** (shared: `a`, `are`, `as`, `business`, `expenses`, `in`, `of`, `off`, `the`; missing: `based`, `equipment`, `home`, `ins`, `outs`, `purchases`, `what`, `writing`). Rank-1 was `283079` (score=0.9917, coverage=59% vs gold 53%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.


#### Error analysis (Local BM25)

**1. False positive** — query id `8`

**Query**

> How to deposit a cheque issued to an associate in my business into my business account?

**Observation:** Rank #2 doc `261856` (score=41.8126) is not relevant. Snippet: Banks has to complete KYC. In case you want to open a bank account, most will ask for proof of address. I also feel it is difficult for bank to encash a cheque payable to a business in your account. …

**Analysis:** Irrelevant document ranked #2 (score=41.8126) despite not being in the qrels. Lexical coverage vs query: **46%** (6/13 query tokens). Shared: `a`, `account`, `business`, `cheque`, `in`, `to`. Query tokens absent from this hit: `an`, `associate`, `deposit`, `how`, `into`, `issued`, `my`. Best gold `65404` covers **62%** of query tokens (shared: `a`, `account`, `associate`, `business`, `cheque`, `deposit`, `in`, `to`; missing on gold: `an`, `how`, `into`, `issued`, `my`). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**2. False positive** — query id `15`

**Query**

> Can I send a money order from USPS as a business?

**Observation:** Rank #1 doc `420483` (score=30.9165) is not relevant. Snippet: On your end of the deal, the biggest risk is probably counterfeiting. That said, I'd think that most of the downside would be for the buyer since they would have no way to prove that they paid you. P…

**Analysis:** Irrelevant document ranked #1 (score=30.9165) despite not being in the qrels. Lexical coverage vs query: **70%** (7/10 query tokens). Shared: `a`, `can`, `i`, `money`, `order`, `send`, `usps`. Query tokens absent from this hit: `as`, `business`, `from`. Best gold `325273` covers **70%** of query tokens (shared: `a`, `as`, `business`, `can`, `from`, `money`, `order`; missing on gold: `i`, `send`, `usps`). The false positive matches the query surface form as well as or better than the gold — ranking rewarded topical / lexical similarity rather than labeled relevance (paraphrase, stance, or answer-specific content).

**3. False positive** — query id `18`

**Query**

> 1 EIN doing business under multiple business names

**Observation:** Rank #1 doc `377152` (score=22.9050) is not relevant. Snippet: "According to IRS Publication 1635, Understanding your EIN (PDF), under ""What is an EIN?"" on page 2: Caution: An EIN is for use in connection with your business activities only. Do not use your EIN…

**Analysis:** Irrelevant document ranked #1 (score=22.9050) despite not being in the qrels. Lexical coverage vs query: **43%** (3/7 query tokens). Shared: `business`, `ein`, `under`. Query tokens absent from this hit: `1`, `doing`, `multiple`, `names`. Best gold `88124` covers **29%** of query tokens (shared: `ein`, `under`; missing on gold: `1`, `business`, `doing`, `multiple`, `names`). The false positive matches the query surface form as well as or better than the gold — ranking rewarded topical / lexical similarity rather than labeled relevance (paraphrase, stance, or answer-specific content).

**4. False negative** — query id `8`

**Query**

> How to deposit a cheque issued to an associate in my business into my business account?

**Observation:** Gold doc `566392` completely missed (not in top-100). Snippet: Have the check reissued to the proper payee.

**Analysis:** Gold `566392` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **8%** (shared: `to`; missing on gold: `a`, `account`, `an`, `associate`, `business`, `cheque`, `deposit`, `how`, `in`, `into`, `issued`, `my`). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `65404` (score=51.5059, coverage=62%); #2 `261856` (score=41.8126, coverage=46%); #3 `543812` (score=41.4706, coverage=77%).

**5. False negative** — query id `15`

**Query**

> Can I send a money order from USPS as a business?

**Observation:** Gold doc `325273` completely missed (not in top-100). Snippet: Sure you can. You can fill in whatever you want in the From section of a money order, so your business name and address would be fine. The price only includes the money order itself. You can hand del…

**Analysis:** Gold `325273` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **70%** (shared: `a`, `as`, `business`, `can`, `from`, `money`, `order`; missing on gold: `i`, `send`, `usps`). Several distinctive query tokens never appear in the gold text, so pure lexical matching under-weights the correct doc. Top retrieved instead: #1 `420483` (score=30.9165, coverage=70%); #2 `321826` (score=29.0966, coverage=40%); #3 `454734` (score=28.7581, coverage=50%).

**6. False negative** — query id `26`

**Query**

> Applying for and receiving business credit

**Observation:** Gold doc `285255` completely missed (not in top-100). Snippet: "I'm afraid the great myth of limited liability companies is that all such vehicles have instant access to credit. Limited liability on a company with few physical assets to underwrite the loan, or w…

**Analysis:** Gold `285255` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **50%** (shared: `business`, `credit`, `for`; missing on gold: `and`, `applying`, `receiving`). Several distinctive query tokens never appear in the gold text, so pure lexical matching under-weights the correct doc. Top retrieved instead: #1 `176284` (score=22.1484, coverage=83%); #2 `227910` (score=21.8141, coverage=83%); #3 `338406` (score=20.5766, coverage=83%).

**7. Near miss** — query id `104`

**Query**

> Investing/business with other people's money: How does it work?

**Observation:** Gold doc `575869` retrieved at rank 99/100 (missed NDCG@10). Snippet: "Basically, you either borrow money, or get other people to invest in your business by buying stock or something analogous. Sometimes you can get people to ""park"" money with you. For example, many …

**Analysis:** Gold `575869` retrieved at rank **99**/100 (score=13.8029) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **64%** (shared: `business`, `it`, `money`, `other`, `people`, `s`, `with`; missing: `does`, `how`, `investing`, `work`). Rank-1 was `386803` (score=19.2986, coverage=64% vs gold 64%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**8. Near miss** — query id `549`

**Query**

> Where to request ACH Direct DEBIT of funds from MY OWN personal bank account?

**Observation:** Gold doc `214024` retrieved at rank 14/100 (missed NDCG@10). Snippet: Call Wells Fargo or go to a branch. Tell them what you're trying to accomplish, not the vehicle you think you should use to get there. Don't tell them you want to ACH DEBIT from YOUR ACCOUNT of YOUR …

**Analysis:** Gold `214024` retrieved at rank **14**/100 (score=30.2129) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **50%** (shared: `account`, `ach`, `bank`, `debit`, `from`, `of`, `to`; missing: `direct`, `funds`, `my`, `own`, `personal`, `request`, `where`). Rank-1 was `449279` (score=40.4243, coverage=64% vs gold 50%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**9. Near miss** — query id `585`

**Query**

> Following an investment guru a good idea?

**Observation:** Gold doc `140226` retrieved at rank 81/100 (missed NDCG@10). Snippet: "The best answer here is ""maybe, but probably not"". A few quick reasons: Its not a bad idea to watch other investors especially those who can move markets but do your own research on an investment …

**Analysis:** Gold `140226` retrieved at rank **81**/100 (score=13.0910) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **57%** (shared: `a`, `an`, `idea`, `investment`; missing: `following`, `good`, `guru`). Rank-1 was `426550` (score=18.7093, coverage=86% vs gold 57%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.


#### Error analysis (Local Dense)

**1. False positive** — query id `8`

**Query**

> How to deposit a cheque issued to an associate in my business into my business account?

**Observation:** Rank #2 doc `564553` (score=0.6847) is not relevant. Snippet: "If the cheque is not crossed, then your friend can write ""payable to [your name]"" above his signature when he endorses it. If it is crossed, you'll have to deposit it into his account. Given that …

**Analysis:** Irrelevant document ranked #2 (score=0.6847) despite not being in the qrels. Lexical coverage vs query: **46%** (6/13 query tokens). Shared: `a`, `account`, `cheque`, `deposit`, `into`, `to`. Query tokens absent from this hit: `an`, `associate`, `business`, `how`, `in`, `issued`, `my`. Best gold `65404` covers **62%** of query tokens (shared: `a`, `account`, `associate`, `business`, `cheque`, `deposit`, `in`, `to`; missing on gold: `an`, `how`, `into`, `issued`, `my`). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**2. False positive** — query id `15`

**Query**

> Can I send a money order from USPS as a business?

**Observation:** Rank #2 doc `224000` (score=0.7057) is not relevant. Snippet: "A money order is basically a pre-paid check. The physical cash would probably get deposited into a ""master"" custodial bank account. Each money order has a different bank account number on the chec…

**Analysis:** Irrelevant document ranked #2 (score=0.7057) despite not being in the qrels. Lexical coverage vs query: **60%** (6/10 query tokens). Shared: `a`, `as`, `can`, `money`, `order`, `usps`. Query tokens absent from this hit: `business`, `from`, `i`, `send`. Best gold `325273` covers **70%** of query tokens (shared: `a`, `as`, `business`, `can`, `from`, `money`, `order`; missing on gold: `i`, `send`, `usps`). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**3. False positive** — query id `18`

**Query**

> 1 EIN doing business under multiple business names

**Observation:** Rank #1 doc `377152` (score=0.6643) is not relevant. Snippet: "According to IRS Publication 1635, Understanding your EIN (PDF), under ""What is an EIN?"" on page 2: Caution: An EIN is for use in connection with your business activities only. Do not use your EIN…

**Analysis:** Irrelevant document ranked #1 (score=0.6643) despite not being in the qrels. Lexical coverage vs query: **43%** (3/7 query tokens). Shared: `business`, `ein`, `under`. Query tokens absent from this hit: `1`, `doing`, `multiple`, `names`. Best gold `88124` covers **29%** of query tokens (shared: `ein`, `under`; missing on gold: `1`, `business`, `doing`, `multiple`, `names`). The false positive matches the query surface form as well as or better than the gold — ranking rewarded topical / lexical similarity rather than labeled relevance (paraphrase, stance, or answer-specific content).

**4. False negative** — query id `8`

**Query**

> How to deposit a cheque issued to an associate in my business into my business account?

**Observation:** Gold doc `566392` completely missed (not in top-100). Snippet: Have the check reissued to the proper payee.

**Analysis:** Gold `566392` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **8%** (shared: `to`; missing on gold: `a`, `account`, `an`, `associate`, `business`, `cheque`, `deposit`, `how`, `in`, `into`, `issued`, `my`). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `65404` (score=0.8209, coverage=62%); #2 `564553` (score=0.6847, coverage=46%); #3 `308938` (score=0.6801, coverage=62%).

**5. False negative** — query id `34`

**Query**

> 401k Transfer After Business Closure

**Observation:** Gold doc `599545` completely missed (not in top-100). Snippet: You should probably consult an attorney. However, if the owner was a corporation/LLC and it has been officially dissolved, you can provide an evidence of that from your State's department of State/Co…

**Analysis:** Gold `599545` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **0%** (shared: _(none)_; missing on gold: `401k`, `after`, `business`, `closure`, `transfer`). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `458917` (score=0.6813, coverage=40%); #2 `255277` (score=0.6560, coverage=20%); #3 `492659` (score=0.6548, coverage=20%).

**6. False negative** — query id `42`

**Query**

> What are the ins/outs of writing equipment purchases off as business expenses in a home based business?

**Observation:** Gold doc `272709` completely missed (not in top-100). Snippet: Most items used in business have to be depreciated; you get to deduct a small fraction of the cost each year depending on the lifetime of the item as per IRS rules. That is, you cannot assume a one-y…

**Analysis:** Gold `272709` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **41%** (shared: `a`, `are`, `as`, `business`, `in`, `of`, `the`; missing on gold: `based`, `equipment`, `expenses`, `home`, `ins`, `off`, `outs`, `purchases`, `what`, `writing`). Several distinctive query tokens never appear in the gold text, so pure lexical matching under-weights the correct doc. Top retrieved instead: #1 `283079` (score=0.6954, coverage=59%); #2 `581265` (score=0.6876, coverage=65%); #3 `510863` (score=0.6691, coverage=47%).

**7. Near miss** — query id `18`

**Query**

> 1 EIN doing business under multiple business names

**Observation:** Gold doc `88124` retrieved at rank 11/100 (missed NDCG@10). Snippet: You're confusing a lot of things here. Company B LLC will have it's sales run under Company A LLC, and cease operating as a separate entity These two are contradicting each other. If B LLC ceases to …

**Analysis:** Gold `88124` retrieved at rank **11**/100 (score=0.5757) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **29%** (shared: `ein`, `under`; missing: `1`, `business`, `doing`, `multiple`, `names`). Rank-1 was `377152` (score=0.6643, coverage=43% vs gold 29%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**8. Near miss** — query id `26`

**Query**

> Applying for and receiving business credit

**Observation:** Gold doc `285255` retrieved at rank 17/100 (missed NDCG@10). Snippet: "I'm afraid the great myth of limited liability companies is that all such vehicles have instant access to credit. Limited liability on a company with few physical assets to underwrite the loan, or w…

**Analysis:** Gold `285255` retrieved at rank **17**/100 (score=0.6317) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **50%** (shared: `business`, `credit`, `for`; missing: `and`, `applying`, `receiving`). Rank-1 was `176284` (score=0.7302, coverage=83% vs gold 50%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**9. Near miss** — query id `42`

**Query**

> What are the ins/outs of writing equipment purchases off as business expenses in a home based business?

**Observation:** Gold doc `327263` retrieved at rank 78/100 (missed NDCG@10). Snippet: First of all, Dilip's answer explains well how the business deductions generally work. For most (big) expenses you depreciate it. However, in some cases you need to capitalize it, which is another ac…

**Analysis:** Gold `327263` retrieved at rank **78**/100 (score=0.5421) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **35%** (shared: `business`, `expenses`, `in`, `of`, `the`, `what`; missing: `a`, `are`, `as`, `based`, `equipment`, `home`, `ins`, `off`, `outs`, `purchases`, `writing`). Rank-1 was `283079` (score=0.6954, coverage=59% vs gold 35%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.


#### Why these failures happen

FiQA questions use specialized financial jargon (tickers, instruments, accounting terms). Lexical mismatch is the dominant failure mode: queries mention colloquial investor language while gold posts use formal or acronym-heavy phrasing. Dense models help when wording differs but sense is shared; they still struggle with numeral-heavy or ticker-specific questions where the correct answer document is short and dominated by symbols rather than natural language.

For **T-KEIR**, failures additionally reflect RRF fusion trade-offs (BGE vs BM25 ranks), ColBERT MaxSim rerank errors, and domain paraphrase gaps — not only raw lexical overlap.

### ArguAna (`arguana`)

- Corpus size: **8,674** documents  
- Test queries: **1,406**
- BGE-M3 dense+sparse baseline: `bge-m3` (local `resources/modeling/net/bge-m3`)
- **Best published system:** `SPLADE` (NDCG@10 = 0.472)
- T-KEIR status: **ok** (`hybrid_retrieve.retrieve_hybrid`)
- **T-KEIR gap to best (SPLADE):** `-0.008` (T-KEIR 0.464 − 0.472)
- Local BM25 gap to best: `-0.088`
- Local Dense gap to best: `+0.057`

| Metric | T-KEIR | Local BM25 | Local Dense |
|---|---:|---:|---:|
| NDCG@10 | 0.464 | 0.384 | 0.529 |
| MAP@100 | 0.395 | 0.320 | 0.443 |
| Recall@100 | 0.980 | 0.841 | 0.984 |

#### Error analysis (T-KEIR)

**1. False positive** — query id `test-environment-aeghhgwpe-pro02a`

**Query**

> Being vegetarian helps the environment Becoming a vegetarian is an environmentally friendly thing to do. Modern farming is one of the main sources of pollution in our rivers. Beef farming is one of the main causes of deforestation, and as long as people continue to buy fast food in their billions, there will be a financial incentive to continue cutting down trees to make room for cattle. Because of our desire to eat fish, our rivers and seas are being emptied of fish and many species are facing extinction. Energy resources are used up much more greedily by meat farming than my farming cereals, pulses etc. Eating meat and fish not only causes cruelty to animals, it causes serious harm to the environment and to biodiversity. For example consider Meat production related pollution and defores…

**Observation:** Rank #2 doc `test-international-sepiahbaaw-pro02a` (score=0.8682) is not relevant. Snippet: ss economic policy international africa house believes africans are worse Environmental Damage Both licit and illicit resource extraction have caused ecological and environmental damage in Africa. Th…

**Analysis:** Irrelevant document ranked #2 (score=0.8682) despite not being in the qrels. Lexical coverage vs query: **13%** (44/332 query tokens). Shared: `1`, `2`, `3`, `4`, `a`, `agriculture`, `and`, `are`, `as`, `august`, `being`, `but` … (+32 more). Query tokens absent from this hit: `000`, `10`, `100`, `13`, `17`, `18`, `1992`, `1997`, `2003`, `2004`, `2006`, `2008` … (+276 more). Best gold `test-environment-aeghhgwpe-pro02b` covers **25%** of query tokens (shared: `1`, `18`, `2`, `2008`, `4`, `5`, `a`, `about`, `all`, `an`, `and`, `animals` … (+70 more); missing on gold: `000`, `10`, `100`, `13`, `17`, `1992`, `1997`, `2003`, `2004`, `2006`, `2009`, `21st` … (+238 more)). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**2. False positive** — query id `test-environment-aeghhgwpe-pro01a`

**Query**

> It is immoral to kill animals As evolved human beings it is our moral duty to inflict as little pain as possible for our survival. So if we do not need to inflict pain to animals in order to survive, we should not do it. Farm animals such as chickens, pigs, sheep, and cows are sentient living beings like us - they are our evolutionary cousins and like us they can feel pleasure and pain. The 18th century utilitarian philosopher Jeremy Bentham even believed that animal suffering was just as serious as human suffering and likened the idea of human superiority to racism. It is wrong to farm and kill these animals for food when we do not need to do so. The methods of farming and slaughter of these animals are often barbaric and cruel - even on supposedly 'free range' farms. [1] Ten billion ani…

**Observation:** Rank #2 doc `training-environment-assghbansb-pro02a` (score=0.8728) is not relevant. Snippet: Harming animals for entertainment is immoral If a creature suffers then there can be no moral justification for refusing to take that suffering into consideration. All animals are sentient beings tha…

**Analysis:** Irrelevant document ranked #2 (score=0.8728) despite not being in the qrels. Lexical coverage vs query: **30%** (65/218 query tokens). Shared: `a`, `all`, `an`, `and`, `animal`, `animals`, `any`, `are`, `as`, `barbaric`, `be`, `because` … (+53 more). Query tokens absent from this hit: `1`, `18th`, `1989`, `2`, `2008`, `30`, `adulterated`, `ago`, `analogy`, `another`, `antibiotics`, `around` … (+141 more). Best gold `test-environment-aeghhgwpe-pro01b` covers **25%** of query tokens (shared: `a`, `all`, `an`, `and`, `animal`, `animals`, `are`, `around`, `be`, `beings`, `but`, `by` … (+42 more); missing on gold: `1`, `18th`, `1989`, `2`, `2008`, `30`, `adulterated`, `ago`, `analogy`, `another`, `antibiotics`, `any` … (+152 more)). The false positive matches the query surface form as well as or better than the gold — ranking rewarded topical / lexical similarity rather than labeled relevance (paraphrase, stance, or answer-specific content).

**3. False positive** — query id `test-environment-aeghhgwpe-pro03a`

**Query**

> Vegetarianism is healthier There are significant health benefits to 'going veggie'; a vegetarian diet contains high quantities of fibre, vitamins, and minerals, and is low in fat. (A vegan diet is even better since eggs and dairy products are high in cholesterol.) The risk of contracting many forms of cancer is increased by eating meat: in 1996 the American Cancer Society recommended that red meat should be excluded from the diet entirely. Eating meat also increases the risk of heart disease - vegetables contain no cholesterol, which can build up to cause blocked arteries in meat-eaters. An American study found out that: “that men in the highest quintile of red-meat consumption — those who ate about 5 oz. of red meat a day, roughly the equivalent of a small steak had a 31% higher risk of …

**Observation:** Rank #2 doc `test-environment-aeghhgwpe-pro04b` (score=0.8609) is not relevant. Snippet: animals environment general health health general weight philosophy ethics Food safety and hygiene are very important for everyone, and governments should act to ensure that high standards are in pla…

**Analysis:** Irrelevant document ranked #2 (score=0.8609) despite not being in the qrels. Lexical coverage vs query: **23%** (34/147 query tokens). Shared: `1`, `10`, `2009`, `a`, `about`, `and`, `are`, `as`, `be`, `by`, `can`, `diet` … (+22 more). Query tokens absent from this hit: `1996`, `23rd`, `31`, `5`, `against`, `also`, `american`, `an`, `approximately`, `arteries`, `ate`, `bean` … (+101 more). Best gold `test-environment-aeghhgwpe-pro03b` covers **27%** of query tokens (shared: `1`, `5`, `a`, `also`, `and`, `are`, `as`, `be`, `benefits`, `by`, `can`, `cholesterol` … (+28 more); missing on gold: `10`, `1996`, `2009`, `23rd`, `31`, `about`, `against`, `american`, `an`, `approximately`, `arteries`, `ate` … (+95 more)). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**4. False negative** — query id `test-sport-otshwbe2uuyt-pro01a`

**Query**

> Europe must not give approval to this regime. Viktor Yanukovych fairly came to power in 2010 however since then he has set about attacking the country’s fragile democracy. There are numerous cases showing this democratic decline. For example changes to the constitution that occurred after the Orange revolution have been rolled back to give more power to the presidency. [1] Most visibly opponents of the regime such as Yulia Timoshenko have been jailed in politically motivated trials. At the same time there have been attacks on the freedom of the media and Ukraine has fallen down rankings of press freedom in 2010-11 with its score from freedom house falling from 56 to 59 with its ranking falling to 130th. [2] Ukraine, like its neighbours Russia and Belarus, has become a ‘virtual mafia state…

**Observation:** Gold doc `test-sport-otshwbe2uuyt-pro01b` completely missed (not in top-100). Snippet: olympics team sports house would boycott euro 2012 ukraine unless yulia timoshenko Attending football matches is not giving approval to a country’s government. Leaders when attending international fo…

**Analysis:** Gold `test-sport-otshwbe2uuyt-pro01b` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **14%** (shared: `2012`, `a`, `and`, `approval`, `are`, `as`, `back`, `country`, `for`, `house`, `international`, `is` … (+11 more); missing on gold: `1`, `11`, `118th`, `130th`, `152nd`, `16`, `2`, `2007`, `2010`, `2011`, `3`, `4` … (+130 more)). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `test-sport-otshwbe2uuyt-pro02a` (score=0.8571, coverage=33%); #2 `test-sport-otshwbe2uuyt-con05a` (score=0.8503, coverage=24%); #3 `test-sport-otshwbe2uuyt-con02a` (score=0.8246, coverage=25%).

**5. False negative** — query id `test-free-speech-debate-nshbbsbfb-pro04a`

**Query**

> It is simply impractical for a major international broadcaster to hand out powers of veto to small sectional interests. The BBC would quickly be left with a content either devoid of interest or of content were it to allow such a veto to become normative. Especially were it, as appears to be the case here, to offer such a veto to people who didn’t watch the programme. As a result, although some of the responsibility for avoiding offence lies with the broadcaster at least an equal share must lie with the viewer. Even at the more basic level of ‘will I like this’, responsibility lies with both parties. The BBC undertakes to provide a diverse range of programming so that there is a reasonable chance that the overwhelming majority should be able to find something of interest but does so on the…

**Observation:** Gold doc `test-free-speech-debate-nshbbsbfb-pro04b` completely missed (not in top-100). Snippet: nothing sacred house believes bbc should be free blaspheme There is clearly a different threshold between the questions “do I like soap operas?” and “do I appreciate having my beliefs excoriated on n…

**Analysis:** Gold `test-free-speech-debate-nshbbsbfb-pro04b` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **16%** (shared: `a`, `as`, `bbc`, `be`, `here`, `i`, `is`, `like`, `offence`, `on`, `programme`, `should` … (+5 more); missing on gold: `able`, `allow`, `already`, `although`, `an`, `appears`, `assume`, `assumption`, `at`, `avoiding`, `basic`, `become` … (+76 more)). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `test-free-speech-debate-nshbbsbfb-pro02a` (score=0.8938, coverage=36%); #2 `test-free-speech-debate-nshbbsbfb-con03a` (score=0.8774, coverage=33%); #3 `test-free-speech-debate-nshbbsbfb-pro03a` (score=0.8543, coverage=33%).

**6. False negative** — query id `test-free-speech-debate-yfsdfkhbwu-con02a`

**Query**

> ‘Separation of town and gown’ There are two parties involved in this interaction, the state and the university. To pretend that is an entirely one way process is to ignore reality. Contrary to the belief of many Senior Common Rooms, states do not exist for the convenience of universities. Indeed universities quite happily accept the political and economic stability provided by states at exactly the same time as criticising the methods they need to use to maintain it. However, ultimately universities are service providers from the point of view of the state, training and skilling the workforce. The university provides its expertise in exchange for funding and student fees. Where, exactly, the opinions of the faculty enter into such an equation is not clear and appears to have been assumed …

**Observation:** Gold doc `test-free-speech-debate-yfsdfkhbwu-con02b` completely missed (not in top-100). Snippet: y free speech debate free know house believes western universities Singapore in this particular instance is securing far more than a ‘service provider’ from a university whose foundation precedes tha…

**Analysis:** Gold `test-free-speech-debate-yfsdfkhbwu-con02b` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **15%** (shared: `a`, `an`, `and`, `argue`, `as`, `be`, `benefit`, `by`, `for`, `free`, `from`, `here` … (+14 more); missing on gold: `15`, `2009`, `academics`, `accept`, `adopt`, `announced`, `appears`, `apply`, `approach`, `are`, `arrangement`, `asian` … (+138 more)). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `test-free-speech-debate-yfsdfkhbwu-con03a` (score=0.8725, coverage=25%); #2 `training-digital-freedoms-pidfakhwcs-pro01a` (score=0.8386, coverage=24%); #3 `test-education-udfakusma-pro02a` (score=0.8251, coverage=24%).

**7. Near miss** — query id `test-environment-assgbatj-pro05a`

**Query**

> It would send out a consistent message Most countries have animal welfare laws to prevent animal cruelty but have laws like the UK’s Animals (Scientific Procedures) Act 1986, [10] that stop animal testing being a crime. This makes means some people can do things to animals, but not others. If the government are serious about animal abuse, why allow anyone to do it?

**Observation:** Gold doc `test-environment-assgbatj-pro05b` retrieved at rank 22/100 (missed NDCG@10). Snippet: animals science science general ban animal testing junior There is a moral difference between harm for the sake of harming an animal and harm in order to save lives. Lifesaving drugs is a very differ…

**Analysis:** Gold `test-environment-assgbatj-pro05b` retrieved at rank **22**/100 (score=0.6900) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **20%** (shared: `a`, `animal`, `animals`, `are`, `laws`, `testing`, `that`, `the`, `to`, `welfare`; missing: `10`, `1986`, `about`, `abuse`, `act`, `allow`, `anyone`, `being`, `but`, `can`, `consistent`, `countries` … (+29 more)). Rank-1 was `test-philosophy-apessghwba-pro05a` (score=0.9233, coverage=55% vs gold 20%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**8. Near miss** — query id `test-environment-assgbatj-pro04a`

**Query**

> Most animals can suffer more than some people It’s possible to think of people that can’t suffer, like those in a persistent vegetative state, or with significant intellectual disabilities. We could go for one of three options. Either we could experiment on animals, but not such people, which is morally not consistent. We could allow both, but do we want to do painful medical research on the disabled? Or, we could do neither.[9]

**Observation:** Gold doc `test-environment-assgbatj-pro04b` retrieved at rank 19/100 (missed NDCG@10). Snippet: animals science science general ban animal testing junior The decision to test is not based upon the capacity to suffer. But it should be remembered that the individual being tested would not be the …

**Analysis:** Gold `test-environment-assgbatj-pro04b` retrieved at rank **19**/100 (score=0.6900) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **23%** (shared: `animals`, `but`, `disabled`, `for`, `is`, `it`, `not`, `one`, `suffer`, `that`, `the`, `to` … (+1 more); missing: `9`, `a`, `allow`, `both`, `can`, `consistent`, `could`, `disabilities`, `do`, `either`, `experiment`, `go` … (+31 more)). Rank-1 was `test-philosophy-apessghwba-pro04a` (score=0.9313, coverage=66% vs gold 23%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**9. Near miss** — query id `test-environment-assgbatj-con05a`

**Query**

> Research animals are well treated Animals used in research generally don’t suffer. While they may be in pain, they are generally given pain killers, and when they are put down this is done humanely. [16] They are looked after, as healthy animals mean better experimental results. These animals live better lives than they would in the wild. As long as animals are treated well there shouldn’t be a moral objection to animal research. This is exactly the same as with raising animals that will be used for meat.

**Observation:** Gold doc `test-environment-assgbatj-con05b` retrieved at rank 20/100 (missed NDCG@10). Snippet: animals science science general ban animal testing junior Just because an animal is treated well as it is brought up doesn’t stop the very real suffering during testing. Stricter rules and painkiller…

**Analysis:** Gold `test-environment-assgbatj-con05b` retrieved at rank **20**/100 (score=0.7167) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **21%** (shared: `and`, `animal`, `animals`, `as`, `be`, `don`, `is`, `t`, `the`, `treated`, `well`, `would`; missing: `16`, `a`, `after`, `are`, `better`, `done`, `down`, `exactly`, `experimental`, `for`, `generally`, `given` … (+34 more)). Rank-1 was `test-philosophy-apessghwba-con05a` (score=0.9423, coverage=71% vs gold 21%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.


#### Error analysis (Local BM25)

**1. False positive** — query id `test-environment-aeghhgwpe-pro02a`

**Query**

> Being vegetarian helps the environment Becoming a vegetarian is an environmentally friendly thing to do. Modern farming is one of the main sources of pollution in our rivers. Beef farming is one of the main causes of deforestation, and as long as people continue to buy fast food in their billions, there will be a financial incentive to continue cutting down trees to make room for cattle. Because of our desire to eat fish, our rivers and seas are being emptied of fish and many species are facing extinction. Energy resources are used up much more greedily by meat farming than my farming cereals, pulses etc. Eating meat and fish not only causes cruelty to animals, it causes serious harm to the environment and to biodiversity. For example consider Meat production related pollution and defores…

**Observation:** Rank #2 doc `test-environment-aeghhgwpe-pro03b` (score=918.6280) is not relevant. Snippet: animals environment general health health general weight philosophy ethics The key to good health is a balanced diet, not a meat- and fish-free diet. Meat and fish are good sources of protein, iron, …

**Analysis:** Irrelevant document ranked #2 (score=918.6280) despite not being in the qrels. Lexical coverage vs query: **13%** (43/332 query tokens). Shared: `1`, `3`, `5`, `a`, `all`, `amount`, `and`, `animals`, `are`, `as`, `be`, `being` … (+31 more). Query tokens absent from this hit: `000`, `10`, `100`, `13`, `17`, `18`, `1992`, `1997`, `2`, `2003`, `2004`, `2006` … (+277 more). Best gold `test-environment-aeghhgwpe-pro02b` covers **25%** of query tokens (shared: `1`, `18`, `2`, `2008`, `4`, `5`, `a`, `about`, `all`, `an`, `and`, `animals` … (+70 more); missing on gold: `000`, `10`, `100`, `13`, `17`, `1992`, `1997`, `2003`, `2004`, `2006`, `2009`, `21st` … (+238 more)). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**2. False positive** — query id `test-environment-aeghhgwpe-pro01a`

**Query**

> It is immoral to kill animals As evolved human beings it is our moral duty to inflict as little pain as possible for our survival. So if we do not need to inflict pain to animals in order to survive, we should not do it. Farm animals such as chickens, pigs, sheep, and cows are sentient living beings like us - they are our evolutionary cousins and like us they can feel pleasure and pain. The 18th century utilitarian philosopher Jeremy Bentham even believed that animal suffering was just as serious as human suffering and likened the idea of human superiority to racism. It is wrong to farm and kill these animals for food when we do not need to do so. The methods of farming and slaughter of these animals are often barbaric and cruel - even on supposedly 'free range' farms. [1] Ten billion ani…

**Observation:** Rank #1 doc `training-environment-assghbansb-pro02a` (score=629.8438) is not relevant. Snippet: Harming animals for entertainment is immoral If a creature suffers then there can be no moral justification for refusing to take that suffering into consideration. All animals are sentient beings tha…

**Analysis:** Irrelevant document ranked #1 (score=629.8438) despite not being in the qrels. Lexical coverage vs query: **30%** (65/218 query tokens). Shared: `a`, `all`, `an`, `and`, `animal`, `animals`, `any`, `are`, `as`, `barbaric`, `be`, `because` … (+53 more). Query tokens absent from this hit: `1`, `18th`, `1989`, `2`, `2008`, `30`, `adulterated`, `ago`, `analogy`, `another`, `antibiotics`, `around` … (+141 more). Best gold `test-environment-aeghhgwpe-pro01b` covers **25%** of query tokens (shared: `a`, `all`, `an`, `and`, `animal`, `animals`, `are`, `around`, `be`, `beings`, `but`, `by` … (+42 more); missing on gold: `1`, `18th`, `1989`, `2`, `2008`, `30`, `adulterated`, `ago`, `analogy`, `another`, `antibiotics`, `any` … (+152 more)). The false positive matches the query surface form as well as or better than the gold — ranking rewarded topical / lexical similarity rather than labeled relevance (paraphrase, stance, or answer-specific content).

**3. False positive** — query id `test-environment-aeghhgwpe-pro03a`

**Query**

> Vegetarianism is healthier There are significant health benefits to 'going veggie'; a vegetarian diet contains high quantities of fibre, vitamins, and minerals, and is low in fat. (A vegan diet is even better since eggs and dairy products are high in cholesterol.) The risk of contracting many forms of cancer is increased by eating meat: in 1996 the American Cancer Society recommended that red meat should be excluded from the diet entirely. Eating meat also increases the risk of heart disease - vegetables contain no cholesterol, which can build up to cause blocked arteries in meat-eaters. An American study found out that: “that men in the highest quintile of red-meat consumption — those who ate about 5 oz. of red meat a day, roughly the equivalent of a small steak had a 31% higher risk of …

**Observation:** Rank #2 doc `test-environment-aeghhgwpe-pro02b` (score=390.0279) is not relevant. Snippet: animals environment general health health general weight philosophy ethics You don’t have to be vegetarian to be green. Many special environments have been created by livestock farming – for example …

**Analysis:** Irrelevant document ranked #2 (score=390.0279) despite not being in the qrels. Lexical coverage vs query: **27%** (40/147 query tokens). Shared: `1`, `5`, `a`, `about`, `also`, `an`, `and`, `are`, `as`, `be`, `by`, `can` … (+28 more). Query tokens absent from this hit: `10`, `1996`, `2009`, `23rd`, `31`, `against`, `american`, `approximately`, `arteries`, `ate`, `bean`, `beans` … (+95 more). Best gold `test-environment-aeghhgwpe-pro03b` covers **27%** of query tokens (shared: `1`, `5`, `a`, `also`, `and`, `are`, `as`, `be`, `benefits`, `by`, `can`, `cholesterol` … (+28 more); missing on gold: `10`, `1996`, `2009`, `23rd`, `31`, `about`, `against`, `american`, `an`, `approximately`, `arteries`, `ate` … (+95 more)). The false positive matches the query surface form as well as or better than the gold — ranking rewarded topical / lexical similarity rather than labeled relevance (paraphrase, stance, or answer-specific content).

**4. False negative** — query id `test-environment-assgbatj-con04a`

**Query**

> Animal research is only used when it’s needed EU member states and the US have laws to stop animals being used for research if there is any alternative. The 3Rs principles are commonly used. Animal testing is being Refined for better results and less suffering, Replaced, and Reduced in terms of the number of animals used. This means that less animals have to suffer, and the research is better.

**Observation:** Gold doc `test-environment-assgbatj-con04b` completely missed (not in top-100). Snippet: animals science science general ban animal testing junior Not every country has laws like the EU or the US. In countries with low welfare standards animal testing is a more attractive option. Animal …

**Analysis:** Gold `test-environment-assgbatj-con04b` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **26%** (shared: `animal`, `animals`, `eu`, `in`, `is`, `laws`, `only`, `research`, `testing`, `the`, `to`, `us`; missing on gold: `3rs`, `alternative`, `and`, `any`, `are`, `being`, `better`, `commonly`, `for`, `have`, `if`, `it` … (+22 more)). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `test-philosophy-apessghwba-con04a` (score=196.6243, coverage=65%); #2 `test-philosophy-apessghwba-pro03b` (score=168.0943, coverage=52%); #3 `test-philosophy-apessghwba-con05a` (score=162.3627, coverage=54%).

**5. False negative** — query id `test-environment-chbwtlgcc-pro04a`

**Query**

> Consequences of increased GHGs Increased GHGs in the atmosphere have numerous significant consequences: -glaciers, ice sheets, and perma frost will continue to melt. This will increase water levels, release more GHGs (methane, which is twenty times more powerful as a greenhouse gas than CO2 and CO2), and reflect less heat back into the atmosphere exacerbating climate change1. -the oceans (which are a natural carbon sink) are becoming increasingly acidic which will significantly damage ecosystems such as coral reefs. Additionally, changes in the chemistry of the ocean could affect the amount of CO2 it can absorb and process annually. -there will be increasing incidents of extreme weather such as hurricanes, floods, and record high/low temperatures. Extreme weather can destroy ecosystems th…

**Observation:** Gold doc `test-environment-chbwtlgcc-pro04b` completely missed (not in top-100). Snippet: climate house believes were too late global climate change These consequences are often speculation. With such a large and complex system we have no way of knowing what the consequences of climate ch…

**Analysis:** Gold `test-environment-chbwtlgcc-pro04b` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **13%** (shared: `a`, `accelerate`, `and`, `are`, `be`, `change`, `climate`, `consequences`, `earth`, `have`, `in`, `of` … (+6 more); missing on gold: `08`, `1`, `1000s`, `2`, `2008`, `2011`, `23rd`, `5c`, `above`, `absorb`, `absorption`, `acidic` … (+105 more)). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `training-environment-cpiahwdwf-pro03a` (score=273.9403, coverage=19%); #2 `training-environment-ogecephwgn-pro03a` (score=272.5136, coverage=21%); #3 `training-environment-cephbesane-pro02a` (score=268.5194, coverage=25%).

**6. False negative** — query id `test-environment-chbwtlgcc-con03a`

**Query**

> New Technology Humanity has revolutionized the world repeatedly through such monumental inventions as agriculture, steel, anti-biotics, and microchips. And as technology has improved, so too has the rate at which technology improves. It is predicted that there will be 32 times more change between 2000 and 2050 than there was between 1950 and 2000. In the midst of this, many great minds will be focussed on emissions abatement and climate control technologies. So, even if the most severe climate predictions do come to pass, it is unimaginable that humanity will not find a way to intervene. Even small changes will make a difference – more efficient coal power stations can emit a third less emissions than less efficient ones 1. Renewable energy will become more competitive and scalable and te…

**Observation:** Gold doc `test-environment-chbwtlgcc-con03b` completely missed (not in top-100). Snippet: climate house believes were too late global climate change Technological improvements will almost certainly be developed for those who can afford them (as most technology is). However, climate change…

**Analysis:** Gold `test-environment-chbwtlgcc-con03b` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **15%** (shared: `able`, `as`, `be`, `can`, `change`, `climate`, `is`, `most`, `not`, `on`, `technology`, `that` … (+5 more); missing on gold: `1`, `10`, `1950`, `2000`, `2009`, `2050`, `32`, `a`, `abatement`, `agriculture`, `and`, `anti` … (+85 more)). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `test-environment-chbwtlgcc-pro03a` (score=197.5610, coverage=28%); #2 `test-environment-chbwtlgcc-con01a` (score=196.5386, coverage=26%); #3 `training-environment-echbcatspct-pro01a` (score=195.8021, coverage=31%).

**7. Near miss** — query id `test-environment-aeghhgwpe-con01a`

**Query**

> Humans can choose their own nutrition plan Humans are omnivores – we are meant to eat both meat and plants. Like our early ancestors we have sharp canine teeth for tearing animal flesh and digestive systems adapted to eating meat and fish as well as vegetables. Our stomachs are also adapted to eating both meat and vegetable matter. All of this means that eating meat is part of being human. Only in a few western countries are people self-indulgent enough to deny their nature and get upset about a normal human diet. We were made to eat both meat and vegetables - cutting out half of this diet will inevitably mean we lose that natural balance. Eating meat is entirely natural. Like many other species, human beings were once hunters. In the wild animals kill and are killed, often very brutally …

**Observation:** Gold doc `test-environment-aeghhgwpe-con01b` retrieved at rank 37/100 (missed NDCG@10). Snippet: animals environment general health health general weight philosophy ethics Human evolved as omnivores over thousands of years. Yet since the invention of farming there is no longer a need for us to b…

**Analysis:** Gold `test-environment-aeghhgwpe-con01b` retrieved at rank **37**/100 (score=246.5738) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **21%** (shared: `a`, `ancestors`, `and`, `animals`, `as`, `being`, `eat`, `for`, `from`, `get`, `have`, `human` … (+13 more); missing: `about`, `adapted`, `all`, `also`, `animal`, `are`, `balance`, `beings`, `both`, `brutally`, `can`, `canine` … (+84 more)). Rank-1 was `test-environment-aeghhgwpe-pro01b` (score=437.1346, coverage=32% vs gold 21%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**8. Near miss** — query id `test-environment-assgbatj-pro02a`

**Query**

> Animal research causes severe harm to the animals involved The point of animal research is that animals are harmed. Even if they don’t suffer in the experiment, almost all are killed afterwards. With 115 million animals used a year this is a big problem. Releasing medical research animals in to the wild would be dangerous for them, and they would not be usable as pets. [4]. The only solution is that they are wild from birth. It is obvious that it’s not in the interest of animals to be killed or harmed. Research should be banned in order to prevent the deaths of millions of animals.

**Observation:** Gold doc `test-environment-assgbatj-pro02b` retrieved at rank 21/100 (missed NDCG@10). Snippet: animals science science general ban animal testing junior What then is the interest of the animal? If releasing these animals into the wild would kill them then surely it is humane to put them down a…

**Analysis:** Gold `test-environment-assgbatj-pro02b` retrieved at rank **21**/100 (score=206.4039) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **28%** (shared: `and`, `animal`, `animals`, `be`, `experiment`, `if`, `interest`, `is`, `it`, `not`, `of`, `releasing` … (+6 more); missing: `115`, `4`, `a`, `afterwards`, `all`, `almost`, `are`, `as`, `banned`, `big`, `birth`, `causes` … (+35 more)). Rank-1 was `test-philosophy-apessghwba-pro02a` (score=322.4742, coverage=65% vs gold 28%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**9. Near miss** — query id `test-environment-assgbatj-pro05a`

**Query**

> It would send out a consistent message Most countries have animal welfare laws to prevent animal cruelty but have laws like the UK’s Animals (Scientific Procedures) Act 1986, [10] that stop animal testing being a crime. This makes means some people can do things to animals, but not others. If the government are serious about animal abuse, why allow anyone to do it?

**Observation:** Gold doc `test-environment-assgbatj-pro05b` retrieved at rank 29/100 (missed NDCG@10). Snippet: animals science science general ban animal testing junior There is a moral difference between harm for the sake of harming an animal and harm in order to save lives. Lifesaving drugs is a very differ…

**Analysis:** Gold `test-environment-assgbatj-pro05b` retrieved at rank **29**/100 (score=97.5256) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **20%** (shared: `a`, `animal`, `animals`, `are`, `laws`, `testing`, `that`, `the`, `to`, `welfare`; missing: `10`, `1986`, `about`, `abuse`, `act`, `allow`, `anyone`, `being`, `but`, `can`, `consistent`, `countries` … (+29 more)). Rank-1 was `test-philosophy-apessghwba-pro05a` (score=144.8424, coverage=55% vs gold 20%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.


#### Error analysis (Local Dense)

**1. False positive** — query id `test-environment-aeghhgwpe-pro02a`

**Query**

> Being vegetarian helps the environment Becoming a vegetarian is an environmentally friendly thing to do. Modern farming is one of the main sources of pollution in our rivers. Beef farming is one of the main causes of deforestation, and as long as people continue to buy fast food in their billions, there will be a financial incentive to continue cutting down trees to make room for cattle. Because of our desire to eat fish, our rivers and seas are being emptied of fish and many species are facing extinction. Energy resources are used up much more greedily by meat farming than my farming cereals, pulses etc. Eating meat and fish not only causes cruelty to animals, it causes serious harm to the environment and to biodiversity. For example consider Meat production related pollution and defores…

**Observation:** Rank #2 doc `test-international-sepiahbaaw-pro02a` (score=0.6303) is not relevant. Snippet: ss economic policy international africa house believes africans are worse Environmental Damage Both licit and illicit resource extraction have caused ecological and environmental damage in Africa. Th…

**Analysis:** Irrelevant document ranked #2 (score=0.6303) despite not being in the qrels. Lexical coverage vs query: **13%** (44/332 query tokens). Shared: `1`, `2`, `3`, `4`, `a`, `agriculture`, `and`, `are`, `as`, `august`, `being`, `but` … (+32 more). Query tokens absent from this hit: `000`, `10`, `100`, `13`, `17`, `18`, `1992`, `1997`, `2003`, `2004`, `2006`, `2008` … (+276 more). Best gold `test-environment-aeghhgwpe-pro02b` covers **25%** of query tokens (shared: `1`, `18`, `2`, `2008`, `4`, `5`, `a`, `about`, `all`, `an`, `and`, `animals` … (+70 more); missing on gold: `000`, `10`, `100`, `13`, `17`, `1992`, `1997`, `2003`, `2004`, `2006`, `2009`, `21st` … (+238 more)). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**2. False positive** — query id `test-environment-aeghhgwpe-pro01a`

**Query**

> It is immoral to kill animals As evolved human beings it is our moral duty to inflict as little pain as possible for our survival. So if we do not need to inflict pain to animals in order to survive, we should not do it. Farm animals such as chickens, pigs, sheep, and cows are sentient living beings like us - they are our evolutionary cousins and like us they can feel pleasure and pain. The 18th century utilitarian philosopher Jeremy Bentham even believed that animal suffering was just as serious as human suffering and likened the idea of human superiority to racism. It is wrong to farm and kill these animals for food when we do not need to do so. The methods of farming and slaughter of these animals are often barbaric and cruel - even on supposedly 'free range' farms. [1] Ten billion ani…

**Observation:** Rank #2 doc `training-environment-ahwbsawhnbsf-pro02a` (score=0.6550) is not relevant. Snippet: We should treat animals well It is important to treat animals as kindly as we can. Not causing harm to others is among the basic human rights. Although these rights cannot be said to apply directly t…

**Analysis:** Irrelevant document ranked #2 (score=0.6550) despite not being in the qrels. Lexical coverage vs query: **24%** (53/218 query tokens). Shared: `1`, `2`, `a`, `all`, `an`, `and`, `animal`, `animals`, `are`, `as`, `at`, `be` … (+41 more). Query tokens absent from this hit: `18th`, `1989`, `2008`, `30`, `adulterated`, `ago`, `analogy`, `another`, `antibiotics`, `any`, `around`, `barbaric` … (+153 more). Best gold `test-environment-aeghhgwpe-pro01b` covers **25%** of query tokens (shared: `a`, `all`, `an`, `and`, `animal`, `animals`, `are`, `around`, `be`, `beings`, `but`, `by` … (+42 more); missing on gold: `1`, `18th`, `1989`, `2`, `2008`, `30`, `adulterated`, `ago`, `analogy`, `another`, `antibiotics`, `any` … (+152 more)). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**3. False positive** — query id `test-environment-aeghhgwpe-pro03a`

**Query**

> Vegetarianism is healthier There are significant health benefits to 'going veggie'; a vegetarian diet contains high quantities of fibre, vitamins, and minerals, and is low in fat. (A vegan diet is even better since eggs and dairy products are high in cholesterol.) The risk of contracting many forms of cancer is increased by eating meat: in 1996 the American Cancer Society recommended that red meat should be excluded from the diet entirely. Eating meat also increases the risk of heart disease - vegetables contain no cholesterol, which can build up to cause blocked arteries in meat-eaters. An American study found out that: “that men in the highest quintile of red-meat consumption — those who ate about 5 oz. of red meat a day, roughly the equivalent of a small steak had a 31% higher risk of …

**Observation:** Rank #2 doc `test-environment-aeghhgwpe-pro04b` (score=0.6246) is not relevant. Snippet: animals environment general health health general weight philosophy ethics Food safety and hygiene are very important for everyone, and governments should act to ensure that high standards are in pla…

**Analysis:** Irrelevant document ranked #2 (score=0.6246) despite not being in the qrels. Lexical coverage vs query: **23%** (34/147 query tokens). Shared: `1`, `10`, `2009`, `a`, `about`, `and`, `are`, `as`, `be`, `by`, `can`, `diet` … (+22 more). Query tokens absent from this hit: `1996`, `23rd`, `31`, `5`, `against`, `also`, `american`, `an`, `approximately`, `arteries`, `ate`, `bean` … (+101 more). Best gold `test-environment-aeghhgwpe-pro03b` covers **27%** of query tokens (shared: `1`, `5`, `a`, `also`, `and`, `are`, `as`, `be`, `benefits`, `by`, `can`, `cholesterol` … (+28 more); missing on gold: `10`, `1996`, `2009`, `23rd`, `31`, `about`, `against`, `american`, `an`, `approximately`, `arteries`, `ate` … (+95 more)). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**4. False negative** — query id `test-sport-otshwbe2uuyt-pro01a`

**Query**

> Europe must not give approval to this regime. Viktor Yanukovych fairly came to power in 2010 however since then he has set about attacking the country’s fragile democracy. There are numerous cases showing this democratic decline. For example changes to the constitution that occurred after the Orange revolution have been rolled back to give more power to the presidency. [1] Most visibly opponents of the regime such as Yulia Timoshenko have been jailed in politically motivated trials. At the same time there have been attacks on the freedom of the media and Ukraine has fallen down rankings of press freedom in 2010-11 with its score from freedom house falling from 56 to 59 with its ranking falling to 130th. [2] Ukraine, like its neighbours Russia and Belarus, has become a ‘virtual mafia state…

**Observation:** Gold doc `test-sport-otshwbe2uuyt-pro01b` completely missed (not in top-100). Snippet: olympics team sports house would boycott euro 2012 ukraine unless yulia timoshenko Attending football matches is not giving approval to a country’s government. Leaders when attending international fo…

**Analysis:** Gold `test-sport-otshwbe2uuyt-pro01b` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **14%** (shared: `2012`, `a`, `and`, `approval`, `are`, `as`, `back`, `country`, `for`, `house`, `international`, `is` … (+11 more); missing on gold: `1`, `11`, `118th`, `130th`, `152nd`, `16`, `2`, `2007`, `2010`, `2011`, `3`, `4` … (+130 more)). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `training-law-hrilhwsyh-pro04a` (score=0.6284, coverage=16%); #2 `training-international-egilpwhbrh-pro02a` (score=0.6122, coverage=19%); #3 `test-sport-otshwbe2uuyt-con05a` (score=0.6113, coverage=24%).

**5. False negative** — query id `test-free-speech-debate-magghbcrg-con02a`

**Query**

> Radio is yesterday’s technology. Proposition is right to point out the role that has traditionally been filled by relatively small scale radio – providing a relatively cheap method of getting in touch with anybody willing to listen. However, that has, effectively, been rendered redundant by Internet technology. The power of Facebook, Youtube and other sites to disseminate ideas and information as well as phone texting has not only matched that role but surpassed it. With no capital costs in an era of internet cafes and omnipresent cell phones, the free exchange of information through digital and portable technology has met exactly the needs and concerns Proposition highlights. [i] Suggesting that community radio will somehow supplement or enhance that process it taking a step backwards; s…

**Observation:** Gold doc `test-free-speech-debate-magghbcrg-con02b` completely missed (not in top-100). Snippet: media and good government house believes community radio good For all of its potential, the idea that the Internet is a worldwide force is something of a Western conceit. That fact is doubly the case…

**Analysis:** Gold `test-free-speech-debate-magghbcrg-con02b` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **11%** (shared: `a`, `all`, `and`, `community`, `for`, `house`, `in`, `internet`, `is`, `media`, `of`, `radio` … (+5 more); missing on gold: `10`, `18`, `2010`, `2012`, `3`, `5`, `activities`, `aid`, `alex`, `allows`, `already`, `an` … (+120 more)). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `test-free-speech-debate-magghbcrg-pro02a` (score=0.6225, coverage=22%); #2 `test-free-speech-debate-magghbcrg-pro01a` (score=0.5891, coverage=19%); #3 `test-society-cpisydfphwj-pro03b` (score=0.5837, coverage=38%).

**6. False negative** — query id `test-free-speech-debate-nshbbsbfb-pro04a`

**Query**

> It is simply impractical for a major international broadcaster to hand out powers of veto to small sectional interests. The BBC would quickly be left with a content either devoid of interest or of content were it to allow such a veto to become normative. Especially were it, as appears to be the case here, to offer such a veto to people who didn’t watch the programme. As a result, although some of the responsibility for avoiding offence lies with the broadcaster at least an equal share must lie with the viewer. Even at the more basic level of ‘will I like this’, responsibility lies with both parties. The BBC undertakes to provide a diverse range of programming so that there is a reasonable chance that the overwhelming majority should be able to find something of interest but does so on the…

**Observation:** Gold doc `test-free-speech-debate-nshbbsbfb-pro04b` completely missed (not in top-100). Snippet: nothing sacred house believes bbc should be free blaspheme There is clearly a different threshold between the questions “do I like soap operas?” and “do I appreciate having my beliefs excoriated on n…

**Analysis:** Gold `test-free-speech-debate-nshbbsbfb-pro04b` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **16%** (shared: `a`, `as`, `bbc`, `be`, `here`, `i`, `is`, `like`, `offence`, `on`, `programme`, `should` … (+5 more); missing on gold: `able`, `allow`, `already`, `although`, `an`, `appears`, `assume`, `assumption`, `at`, `avoiding`, `basic`, `become` … (+76 more)). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `test-free-speech-debate-nshbbsbfb-pro02a` (score=0.6485, coverage=36%); #2 `test-free-speech-debate-nshbbsbfb-con03a` (score=0.6409, coverage=33%); #3 `test-free-speech-debate-nshbbsbfb-con03b` (score=0.6295, coverage=28%).

**7. Near miss** — query id `test-environment-assgbatj-pro05a`

**Query**

> It would send out a consistent message Most countries have animal welfare laws to prevent animal cruelty but have laws like the UK’s Animals (Scientific Procedures) Act 1986, [10] that stop animal testing being a crime. This makes means some people can do things to animals, but not others. If the government are serious about animal abuse, why allow anyone to do it?

**Observation:** Gold doc `test-environment-assgbatj-pro05b` retrieved at rank 24/100 (missed NDCG@10). Snippet: animals science science general ban animal testing junior There is a moral difference between harm for the sake of harming an animal and harm in order to save lives. Lifesaving drugs is a very differ…

**Analysis:** Gold `test-environment-assgbatj-pro05b` retrieved at rank **24**/100 (score=0.6157) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **20%** (shared: `a`, `animal`, `animals`, `are`, `laws`, `testing`, `that`, `the`, `to`, `welfare`; missing: `10`, `1986`, `about`, `abuse`, `act`, `allow`, `anyone`, `being`, `but`, `can`, `consistent`, `countries` … (+29 more)). Rank-1 was `test-philosophy-apessghwba-pro05a` (score=0.7832, coverage=55% vs gold 20%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**8. Near miss** — query id `test-environment-assgbatj-con01a`

**Query**

> Animals don’t have human rights Humans have large brains, form social groups, communicate and are generally worthy of moral consideration. We also are aware of ourselves and of the nature of death. Some animals have some of these characteristics but not all so should not have the same rights. In harming animals to benefit humans, we enter in to a good moral trade-off to create a greater good. [11]

**Observation:** Gold doc `test-environment-assgbatj-con01b` retrieved at rank 31/100 (missed NDCG@10). Snippet: animals science science general ban animal testing junior To argue that “the ends justify the means” isn’t enough. We don’t know how much animals suffer, as they can’t talk to us. We therefore don’t …

**Analysis:** Gold `test-environment-assgbatj-con01b` retrieved at rank **31**/100 (score=0.6271) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **27%** (shared: `a`, `animals`, `are`, `aware`, `don`, `human`, `in`, `moral`, `of`, `t`, `the`, `to` … (+1 more); missing: `11`, `all`, `also`, `and`, `benefit`, `brains`, `but`, `characteristics`, `communicate`, `consideration`, `create`, `death` … (+23 more)). Rank-1 was `test-philosophy-apessghwba-con01a` (score=0.8609, coverage=67% vs gold 27%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**9. Near miss** — query id `test-environment-opecewiahw-pro04a`

**Query**

> A dam could make the Congo more usable While the Congo is mostly navigable it is only usable internally. The rapids cut the middle Congo off from the sea. The building of the dams could be combined with canalisation and locks to enable international goods to be easily transported to and from the interior. This would help integrate central Africa economically into the global economy making the region much more attractive for investment.

**Observation:** Gold doc `test-environment-opecewiahw-pro04b` retrieved at rank 25/100 (missed NDCG@10). Snippet: omic policy environment climate energy water international africa house would There is currently not enough traffic to justify such a large addition to the project. If it were worthwhile then it coul…

**Analysis:** Gold `test-environment-opecewiahw-pro04b` retrieved at rank **25**/100 (score=0.5213) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **25%** (shared: `a`, `africa`, `be`, `building`, `could`, `dam`, `for`, `international`, `is`, `it`, `the`, `to` … (+1 more); missing: `and`, `attractive`, `canalisation`, `central`, `combined`, `congo`, `cut`, `dams`, `easily`, `economically`, `economy`, `enable` … (+28 more)). Rank-1 was `test-environment-opecewiahw-con02a` (score=0.5945, coverage=30% vs gold 25%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.


#### Why these failures happen

ArguAna is counterargument retrieval: the relevant document is often an opposing stance that deliberately avoids repeating the query's key phrases. Pure lexical overlap therefore systematically under-ranks true counterarguments and promotes thematically similar but stance-aligned essays (false positives). Dense retrieval mitigates some lexical gaps, but stance polarity and argumentative structure are not encoded strongly by generic sentence embeddings, so many gold counterarguments remain buried outside the top ranks.

For **T-KEIR**, failures additionally reflect RRF fusion trade-offs (BGE vs BM25 ranks), ColBERT MaxSim rerank errors, and domain paraphrase gaps — not only raw lexical overlap.

## Method notes

1. Datasets are cached under `./datasets/{name}/` via `beir.util.download_and_unzip`.
2. **T-KEIR (retrieval only):** `thot.tools.eval.hybrid_retrieve.retrieve_hybrid` — BGE-M3 dense+sparse RRF-fused with BM25 (`k=60`), then ColBERT MaxSim via `thot.tools.search.rerank.colbert_rerank` on the top-40 pool (blend 0.55 first-stage + 0.45 ColBERT). **Answer generation is disabled.** Optional Vespa NLP index dumps via `TKEIR_BEIR_INDEX=1`.
3. Local BM25: `hybrid_retrieve.score_bm25` (`rank_bm25.BM25Okapi`).
4. Local BGE-M3 dense+sparse: `hybrid_retrieve.score_bge_hybrid` (`bge-m3`), same encode path as ingest.
5. Metrics: NDCG@10, MAP@100, Recall@100 via `EvaluateRetrieval.evaluate`.
6. Leaderboard: published BEIR BM25 / SPLADE / Contriever NDCG@10. **Best published** = max of those three. **Gap to best** = system_score − best_score (negative = behind the leaderboard leader).
7. Failure analysis: up to three examples per kind (false positive / false negative / near miss). Each case reports the query, the offending or gold document, lexical token coverage vs the query, and a short written analysis.
