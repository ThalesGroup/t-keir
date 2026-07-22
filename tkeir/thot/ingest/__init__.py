"""Title: ingest package init

Document ingestion API, staging manifests, and idempotent indexing.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.ingest.models import IngestJobStatus, IngestManifest

__all__ = ["IngestJobStatus", "IngestManifest"]
