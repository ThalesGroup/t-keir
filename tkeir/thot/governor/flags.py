"""Title: Flags

Runtime kill-switch flags store.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from thot.action.models import utc_now_rfc3339
from thot.governor.models import KillScope, KillSwitchState, RuntimeFlags

_ALL_SCOPES: tuple[KillScope, ...] = (
    "all",
    "ingest",
    "index",
    "inference",
    "hmi-write",
    "agents",
)


def _default_flags() -> RuntimeFlags:
    return RuntimeFlags(
        updated_at=utc_now_rfc3339(),
        scopes={scope: KillSwitchState() for scope in _ALL_SCOPES},
    )


class RuntimeFlagsStore:
    """Thread-safe JSON-backed runtime flags."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if self.path.is_file() and self.path.stat().st_size > 0:
            try:
                self._flags = self._read()
            except (json.JSONDecodeError, ValueError, OSError):
                self._flags = _default_flags()
                self._write(self._flags)
        else:
            self._flags = _default_flags()
            self._write(self._flags)

    def _read(self) -> RuntimeFlags:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return RuntimeFlags.model_validate(payload)

    def _write(self, flags: RuntimeFlags) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                flags.model_dump(by_alias=True, mode="json"),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def snapshot(self) -> RuntimeFlags:
        with self._lock:
            return self._flags.model_copy(deep=True)

    def set_kill(
        self,
        scope: KillScope,
        *,
        active: bool,
        reason: str,
        actor: str,
    ) -> RuntimeFlags:
        """Activate or clear a kill-switch scope.

        Args:
            scope: One of ``all``, ``ingest``, ``index``, ``inference``,
                ``hmi-write``, ``agents``.
            active: True to kill, False to clear.
            reason: Human-readable reason (audit trail).
            actor: Who flipped the switch.

        Returns:
            Updated RuntimeFlags snapshot.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.flags import RuntimeFlagsStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RuntimeFlagsStore(Path(td) / "flags.json")
            ...     _ = store.set_kill(
            ...         "inference", active=True, reason="drill", actor="ops"
            ...     )
            ...     store.is_killed("inference")
            True
        """
        with self._lock:
            flags = self._flags.model_copy(deep=True)
            now = utc_now_rfc3339()
            flags.updated_at = now
            state = flags.scopes.get(scope, KillSwitchState())
            state.active = active
            state.reason = reason
            state.activated_at = now if active else ""
            state.activated_by = actor if active else ""
            flags.scopes[scope] = state
            if scope == "all" and active:
                for key in _ALL_SCOPES:
                    if key != "all":
                        child = flags.scopes[key]
                        child.active = True
                        child.reason = reason or "global kill"
                        child.activated_at = now
                        child.activated_by = actor
            self._flags = flags
            self._write(flags)
            return flags

    def is_killed(self, scope: KillScope) -> bool:
        """Return True if ``scope`` (or global ``all``) is active.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.flags import RuntimeFlagsStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RuntimeFlagsStore(Path(td) / "flags.json")
            ...     store.is_killed("ingest")
            False
        """
        flags = self.snapshot()
        if flags.scopes.get("all", KillSwitchState()).active:
            return True
        return flags.scopes.get(scope, KillSwitchState()).active
