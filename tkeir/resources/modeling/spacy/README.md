# Local spaCy pipelines

Pipelines downloaded by `make install-spacy-models` / `make setup` live here
(not as venv site-packages). Runtime loaders (`SpacyModelLoader`) read this
tree first, then fall back to a pip-installed package if present.

| Path | Model |
|------|--------|
| `en_core_web_sm/`, `en_core_web_md/` | English |
| `fr_core_news_sm/`, `fr_core_news_md/` | French |
| `xx_ent_wiki_sm/` | Multilingual NER fallback |
| `de_core_news_sm/`, `es_core_news_sm`, … | Extra European `sm` models |
| *(none)* | Arabic uses `spacy.blank("ar")` |

Re-download with `make install-spacy-models FORCE_SPACY_MODELS=1`.
