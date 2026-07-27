# Local neural models

Weights downloaded by `make pull-bge-model` / `make setup` live here (not in
the Hugging Face hub cache).

| Path | Model |
|------|--------|
| `bge-m3/` | BAAI/bge-m3 (FlagEmbedding dense + sparse) |

Runtime loaders (`thot.tools.search.bge_m3`) read only from this tree.
Re-download with `make pull-bge-model FORCE_BGE=1`.
