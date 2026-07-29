# BEIR rank fixtures (corpus-independent)

Synthetic ranking cases under `cases.yaml` — no BEIR download required.

## Offline check

```bash
cd tkeir && uv run pytest tests/unittests/TestBeirRankFixtures.py -q
```

The unit test ranks each case with a **local fixture overlap scorer** (no Vespa).
Production search uses T-KEIR hybrid retrieve + ColBERT; `lexical_signal`
only provides `tokenize` / `token_stems` for query expansion and ontology indexing.
