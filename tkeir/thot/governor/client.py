"""Title: Client

Lightweight governor client for workers and services.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from thot.governor.config import governor_settings
from thot.governor.flags import RuntimeFlagsStore
from thot.governor.models import KillScope, RuntimeFlags


class GovernorClient:
    """Read runtime flags from local file or governor HTTP API.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.governor.client import GovernorClient
        >>> with tempfile.TemporaryDirectory() as td:
        ...     client = GovernorClient(flags_path=Path(td) / "flags.json")
        ...     client.is_scope_killed("ingest")
        False
    """

    def __init__(
        self,
        *,
        flags_path: Path | None = None,
        base_url: str | None = None,
    ) -> None:
        """Configure local flags path and optional remote base URL.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.client import GovernorClient
            >>> with tempfile.TemporaryDirectory() as td:
            ...     c = GovernorClient(flags_path=Path(td) / "flags.json")
            ...     c._base_url.startswith("http")
            True
        """
        settings = governor_settings()
        self._flags_path = flags_path or settings.flags_path
        self._base_url = (
            base_url
            or os.getenv("GOVERNOR_URL")
            or f"http://127.0.0.1:{settings.port}"
        ).rstrip("/")
        self._local = RuntimeFlagsStore(self._flags_path)

    def flags(self) -> RuntimeFlags:
        """Fetch flags from HTTP API, falling back to local file.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.client import GovernorClient
            >>> with tempfile.TemporaryDirectory() as td:
            ...     flags = GovernorClient(
            ...         flags_path=Path(td) / "flags.json",
            ...         base_url="http://127.0.0.1:1",
            ...     ).flags()
            ...     "scopes" in flags.model_dump()
            True
        """
        try:
            with urlopen(
                f"{self._base_url}/governor/flags", timeout=2
            ) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return RuntimeFlags.model_validate(payload)
        except (URLError, OSError, ValueError, TimeoutError):
            return self._local.snapshot()

    def is_scope_killed(self, scope: KillScope) -> bool:
        """Return True when ``scope`` or global ``all`` is killed.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.client import GovernorClient
            >>> with tempfile.TemporaryDirectory() as td:
            ...     GovernorClient(
            ...         flags_path=Path(td) / "flags.json"
            ...     ).is_scope_killed("index")
            False
        """
        flags = self.flags()
        if flags.scopes.get("all") and flags.scopes["all"].active:
            return True
        state = flags.scopes.get(scope)
        return bool(state and state.active)

    def assert_scope_active(self, scope: KillScope) -> None:
        """Raise when the scope is killed (for worker pre-flight).

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.client import GovernorClient
            >>> with tempfile.TemporaryDirectory() as td:
            ...     GovernorClient(
            ...         flags_path=Path(td) / "flags.json"
            ...     ).assert_scope_active("ingest")
        """
        if self.is_scope_killed(scope):
            raise RuntimeError(f"governor kill switch active for {scope}")
