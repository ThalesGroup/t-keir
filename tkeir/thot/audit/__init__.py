"""Title: audit package init

Audit store, WORM archive, reports, and verification.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.audit.hot_store import HotStore

__all__ = ["HotStore"]
