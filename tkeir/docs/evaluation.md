# Evaluation

T-KEIR retrieval quality is measured with the [BEIR](https://github.com/beir-cellar/beir)
benchmark suite via `make beir-eval`.

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

Every run **always** writes the Markdown report to:

`tkeir/docs/evaluation_report.md`

That file is part of this documentation site (see
[BEIR evaluation report](evaluation_report.md)). Override with `--report` /
`BEIR_REPORT` only if you also want a copy elsewhere; the docs path is still
updated.

## Related docs

- [Vespa search and RAG](tools/vespa_rag.md) — indexing, search API, concurrency
- [Dev container](devcontainer.md) — TLS / CA tips when downloading BEIR datasets
