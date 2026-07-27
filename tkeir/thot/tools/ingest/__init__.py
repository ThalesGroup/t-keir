"""Title: ingest package init

Document ingestion API, staging manifests, and Vespa indexing.

Indexing entry points:
- ``thot.tools.ingest.index_passages`` — embed + upsert global/user passages
- ``thot.tools.ingest.index_documents`` — CLI / directory indexer
- ``thot.tools.ingest.worker`` — async ingest jobs

Search / retrieval stays under ``thot.tools.search``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.tools.ingest.models import IngestJobStatus, IngestManifest

__all__ = ["IngestJobStatus", "IngestManifest"]
