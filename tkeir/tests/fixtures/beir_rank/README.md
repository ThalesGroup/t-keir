# Corpus-independent ranking fixtures

Self-contained mini-corpora that reproduce smoke-report failure **patterns**
without downloading BEIR (`scifact` / `fiqa` / `arguana`).

| File | Role |
|------|------|
| `cases.yaml` | Synthetic ranking cases (FN / FP / near-miss) |
| `perf_budgets.yaml` | Stage timing budgets (mocked pipeline) |

## Assert vocabulary

| `assert` | Meaning |
|----------|---------|
| `gold_in_top_k` | Every gold id appears in the top-`k` ranked list |
| `gold_ranks_above_hard_negative` | Best gold rank &lt; best hard-negative rank |
| `gold_rank_le_top_k` | Best gold rank ≤ `top_k` |

## Patterns (from smoke)

- `scientific_alias` — FoxO3a ↔ FOXO
- `morphological_alias` — p150n ↔ p150Glued
- `stopword_topic_bleed` — shared “diabetes/risk” without distinctive token
- `short_gold_answer` — one-sentence gold buried by long distractors
- `paraphrase` — answer uses different surface form
- `query_near_copy` — almost-identical opposing text ranks #1
- `weak_surface_gold` — gold correct but under-promoted
- `related_pair` — low lexical overlap between paired arguments

## Offline check

```bash
cd tkeir && uv run pytest tests/unittests/TestBeirRankFixtures.py -q
```

The unit test ranks each case with `lexical_signal.score_documents` (no Vespa).
Production dual-hybrid now fuses the same signal (`configs/rag.yaml`
`final_fusion.weights.lexical_overlap`).
