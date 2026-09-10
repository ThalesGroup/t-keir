"""Title: Standalone CLI tools for T-KEIR.

Subpackages:
- ``pipeline`` — document analysis pipeline CLI
- ``search`` — Vespa retrieval and RAG
- ``ingest`` — document fetch, staging, and Vespa indexing
- ``eval`` — BEIR / retrieval evaluation (smoke + full metrics)
- ``annotation`` — MWE / annotation resource compilation
- ``corpus`` — markdown directory → ``{dataset, records}`` JSON
- ``install_spacy_models`` / ``install_converter_models`` — setup downloads
  into ``resources/modeling/``

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""
