# BEIR Retrieval Evaluation Report

_Generated 2026-07-27 12:50 UTC_

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
| FiQA-2018 | SPLADE | 0.342 | err (interrupted (Ctrl+C during index) | — | 0.218 | -0.124 | 0.403 | +0.061 |

### Published baselines (reference)

| Dataset | BEIR BM25 | SPLADE | Contriever | **Best** |
|---|---:|---:|---:|---|
| FiQA-2018 | 0.236 | 0.342 | 0.329 | **SPLADE** (0.342) |

### Gap to best published system (detail)

| Dataset | Best system | Best NDCG@10 | T-KEIR gap | Local BM25 gap | Local Dense gap | T-KEIR vs BM25 | T-KEIR vs SPLADE | T-KEIR vs Contriever |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| FiQA-2018 | SPLADE | 0.342 | — | -0.124 | +0.061 | — | — | — |

## Per-dataset metrics

### FiQA-2018 (`fiqa`)

- Corpus size: **57,638** documents  
- Test queries: **648**
- BGE-M3 dense+sparse baseline: `bge-m3` (local `resources/modeling/net/bge-m3`)
- **Best published system:** `SPLADE` (NDCG@10 = 0.342)
- T-KEIR status: **failed** — interrupted (Ctrl+C during indexing/retrieval)
- **T-KEIR gap to best:** —
- Local BM25 gap to best: `-0.124`
- Local Dense gap to best: `+0.061`

| Metric | T-KEIR | Local BM25 | Local Dense |
|---|---:|---:|---:|
| NDCG@10 | — | 0.218 | 0.403 |
| MAP@100 | — | 0.172 | 0.343 |
| Recall@100 | — | 0.475 | 0.689 |

#### Error analysis (T-KEIR)

**1. False negative** — query id `-`

**Query**

> (tkeir run interrupted)

**Observation:** interrupted (Ctrl+C during indexing/retrieval)


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

**Observation:** Rank #2 doc `224000` (score=0.7053) is not relevant. Snippet: "A money order is basically a pre-paid check. The physical cash would probably get deposited into a ""master"" custodial bank account. Each money order has a different bank account number on the chec…

**Analysis:** Irrelevant document ranked #2 (score=0.7053) despite not being in the qrels. Lexical coverage vs query: **60%** (6/10 query tokens). Shared: `a`, `as`, `can`, `money`, `order`, `usps`. Query tokens absent from this hit: `business`, `from`, `i`, `send`. Best gold `325273` covers **70%** of query tokens (shared: `a`, `as`, `business`, `can`, `from`, `money`, `order`; missing on gold: `i`, `send`, `usps`). Gold has stronger query overlap than this hit, yet still lost the top ranks — hybrid / dense scores or competing near-duplicates likely dominated early retrieval.

**3. False positive** — query id `18`

**Query**

> 1 EIN doing business under multiple business names

**Observation:** Rank #1 doc `377152` (score=0.6642) is not relevant. Snippet: "According to IRS Publication 1635, Understanding your EIN (PDF), under ""What is an EIN?"" on page 2: Caution: An EIN is for use in connection with your business activities only. Do not use your EIN…

**Analysis:** Irrelevant document ranked #1 (score=0.6642) despite not being in the qrels. Lexical coverage vs query: **43%** (3/7 query tokens). Shared: `business`, `ein`, `under`. Query tokens absent from this hit: `1`, `doing`, `multiple`, `names`. Best gold `88124` covers **29%** of query tokens (shared: `ein`, `under`; missing on gold: `1`, `business`, `doing`, `multiple`, `names`). The false positive matches the query surface form as well as or better than the gold — ranking rewarded topical / lexical similarity rather than labeled relevance (paraphrase, stance, or answer-specific content).

**4. False negative** — query id `8`

**Query**

> How to deposit a cheque issued to an associate in my business into my business account?

**Observation:** Gold doc `566392` completely missed (not in top-100). Snippet: Have the check reissued to the proper payee.

**Analysis:** Gold `566392` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **8%** (shared: `to`; missing on gold: `a`, `account`, `an`, `associate`, `business`, `cheque`, `deposit`, `how`, `in`, `into`, `issued`, `my`). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `65404` (score=0.8209, coverage=62%); #2 `564553` (score=0.6847, coverage=46%); #3 `308938` (score=0.6801, coverage=62%).

**5. False negative** — query id `34`

**Query**

> 401k Transfer After Business Closure

**Observation:** Gold doc `599545` completely missed (not in top-100). Snippet: You should probably consult an attorney. However, if the owner was a corporation/LLC and it has been officially dissolved, you can provide an evidence of that from your State's department of State/Co…

**Analysis:** Gold `599545` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **0%** (shared: _(none)_; missing on gold: `401k`, `after`, `business`, `closure`, `transfer`). Low surface overlap suggests paraphrase, synonymy, or specialized phrasing the retriever did not bridge. Top retrieved instead: #1 `458917` (score=0.6816, coverage=40%); #2 `255277` (score=0.6561, coverage=20%); #3 `492659` (score=0.6552, coverage=20%).

**6. False negative** — query id `42`

**Query**

> What are the ins/outs of writing equipment purchases off as business expenses in a home based business?

**Observation:** Gold doc `272709` completely missed (not in top-100). Snippet: Most items used in business have to be depreciated; you get to deduct a small fraction of the cost each year depending on the lifetime of the item as per IRS rules. That is, you cannot assume a one-y…

**Analysis:** Gold `272709` is absent from the top-100 — a complete miss for this judgment. Gold lexical coverage vs query: **41%** (shared: `a`, `are`, `as`, `business`, `in`, `of`, `the`; missing on gold: `based`, `equipment`, `expenses`, `home`, `ins`, `off`, `outs`, `purchases`, `what`, `writing`). Several distinctive query tokens never appear in the gold text, so pure lexical matching under-weights the correct doc. Top retrieved instead: #1 `283079` (score=0.6955, coverage=59%); #2 `581265` (score=0.6876, coverage=65%); #3 `510863` (score=0.6690, coverage=47%).

**7. Near miss** — query id `18`

**Query**

> 1 EIN doing business under multiple business names

**Observation:** Gold doc `88124` retrieved at rank 11/100 (missed NDCG@10). Snippet: You're confusing a lot of things here. Company B LLC will have it's sales run under Company A LLC, and cease operating as a separate entity These two are contradicting each other. If B LLC ceases to …

**Analysis:** Gold `88124` retrieved at rank **11**/100 (score=0.5758) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **29%** (shared: `ein`, `under`; missing: `1`, `business`, `doing`, `multiple`, `names`). Rank-1 was `377152` (score=0.6642, coverage=43% vs gold 29%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**8. Near miss** — query id `26`

**Query**

> Applying for and receiving business credit

**Observation:** Gold doc `285255` retrieved at rank 17/100 (missed NDCG@10). Snippet: "I'm afraid the great myth of limited liability companies is that all such vehicles have instant access to credit. Limited liability on a company with few physical assets to underwrite the loan, or w…

**Analysis:** Gold `285255` retrieved at rank **17**/100 (score=0.6318) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **50%** (shared: `business`, `credit`, `for`; missing: `and`, `applying`, `receiving`). Rank-1 was `176284` (score=0.7302, coverage=83% vs gold 50%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.

**9. Near miss** — query id `42`

**Query**

> What are the ins/outs of writing equipment purchases off as business expenses in a home based business?

**Observation:** Gold doc `327263` retrieved at rank 78/100 (missed NDCG@10). Snippet: First of all, Dilip's answer explains well how the business deductions generally work. For most (big) expenses you depreciate it. However, in some cases you need to capitalize it, which is another ac…

**Analysis:** Gold `327263` retrieved at rank **78**/100 (score=0.5421) — counts for Recall@100 but not NDCG@10. Gold query-token coverage **35%** (shared: `business`, `expenses`, `in`, `of`, `the`, `what`; missing: `a`, `are`, `as`, `based`, `equipment`, `home`, `ins`, `off`, `outs`, `purchases`, `writing`). Rank-1 was `283079` (score=0.6955, coverage=59% vs gold 35%). The system found the right neighborhood but failed to promote the labeled evidence into the top-10.


#### Why these failures happen

FiQA questions use specialized financial jargon (tickers, instruments, accounting terms). Lexical mismatch is the dominant failure mode: queries mention colloquial investor language while gold posts use formal or acronym-heavy phrasing. Dense models help when wording differs but sense is shared; they still struggle with numeral-heavy or ticker-specific questions where the correct answer document is short and dominated by symbols rather than natural language.

For **T-KEIR**, failures additionally reflect RRF fusion trade-offs (BGE vs BM25 ranks), ColBERT MaxSim rerank errors, and domain paraphrase gaps — not only raw lexical overlap.

## Method notes

1. Datasets are cached under `./datasets/{name}/` via `beir.util.download_and_unzip`.
2. **T-KEIR (retrieval only):** `thot.tools.eval.hybrid_retrieve.retrieve_hybrid` — BGE-M3 dense+sparse RRF-fused with BM25 (`k=60`), then ColBERT MaxSim via `thot.tools.search.rerank.colbert_rerank` on the top-40 pool (blend 0.55 first-stage + 0.45 ColBERT). **Answer generation is disabled.** Optional Vespa NLP index dumps via `TKEIR_BEIR_INDEX=1`.
3. Local BM25: `hybrid_retrieve.score_bm25` (`rank_bm25.BM25Okapi`).
4. Local BGE-M3 dense+sparse: `hybrid_retrieve.score_bge_hybrid` (`bge-m3`), same encode path as ingest.
5. Metrics: NDCG@10, MAP@100, Recall@100 via `EvaluateRetrieval.evaluate`.
6. Leaderboard: published BEIR BM25 / SPLADE / Contriever NDCG@10. **Best published** = max of those three. **Gap to best** = system_score − best_score (negative = behind the leaderboard leader).
7. Failure analysis: up to three examples per kind (false positive / false negative / near miss). Each case reports the query, the offending or gold document, lexical token coverage vs the query, and a short written analysis.
