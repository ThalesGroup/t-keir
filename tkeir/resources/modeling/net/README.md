# Local neural models

Weights downloaded by `make pull-bge-model`, `make install-converter-models`,
and `make setup` live here (not in the Hugging Face hub cache).

| Path | Model |
|------|--------|
| `bge-m3/` | BAAI/bge-m3 (FlagEmbedding dense + sparse) |
| `blip-image-captioning-base/` | Salesforce BLIP-base (converter image captions) |

Runtime loaders (`thot.tools.search.bge_m3`, converter captions) read only
from this tree. Re-download with `make pull-bge-model FORCE_BGE=1` or
`make install-converter-models FORCE_CONVERTER_MODELS=1`.
