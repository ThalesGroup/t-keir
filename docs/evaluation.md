# Evaluation

T-KEIR retrieval quality is measured with the [BEIR](https://github.com/beir-cellar/beir)
benchmark suite via `make beir-eval`.

## Datasets

By default the harness evaluates three BEIR datasets
(`DEFAULT_DATASETS` in `thot.tools.search.beir_eval`). They are small enough for
repeated local runs, yet cover different retrieval failure modes that matter for
T-KEIR’s NLP + hybrid Vespa path.

| Id | Display name | Task | Domain | Corpus | Test queries | Avg. relevant / query |
|----|--------------|------|--------|--------|--------------|------------------------|
| `scifact` | SciFact | Fact checking | Scientific abstracts | 5,183 | 300 | ~1.1 |
| `fiqa` | FiQA-2018 | Question answering | Personal finance | 57,638 | 648 | ~2.6 |
| `arguana` | ArguAna | Argument / counterargument | Debate essays | 8,674 | 1,406 | ~1.0 |

Sizes follow the published BEIR table. Downloads land under `./datasets/` when
missing. Published **NDCG@10** reference scores used in the report:

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

## How to run

From the repository root:

```bash
# Default datasets: scifact fiqa arguana
make beir-eval

# One dataset
make beir-eval BEIR_DATASETS=scifact

# Skip local dense baseline (faster)
make beir-eval BEIR_DATASETS=scifact BEIR_EXTRA=--skip-dense
```

The CLI module is `thot.tools.search.beir_eval`. It indexes with the T-KEIR
NLP pipeline into Vespa, retrieves with `QueryAnalyzerTask` (no answer
generation), and compares against local BM25 and dense baselines plus published
BEIR leaderboard numbers (BM25 / SPLADE / Contriever).

## Report location

After **each** dataset finishes, the harness writes:

| Path | Contents |
|------|----------|
| `docs/evaluation_report.md` | Cumulative MkDocs report (always) |
| `results/beir/report.md` | Same cumulative snapshot (intermediate) |
| `results/beir/<dataset>/report.md` | That dataset alone |

While more datasets remain, the cumulative files include an **Intermediate**
banner (`N/M` completed). The final write drops the banner.

Override with `--report` / `BEIR_REPORT` for an extra copy; the paths above are
still updated. See [BEIR evaluation report](evaluation_report.md).

## Related docs

- [BEIR evaluation report](evaluation_report.md) — latest measured metrics
- [Vespa search and RAG](tools/vespa_rag.md) — indexing, search API, concurrency
- [Dev container](devcontainer.md) — TLS / CA tips when downloading BEIR datasets
