"""Title: Ingest shutdown

Request a process-wide ingest server stop (used by stop-on-failed).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import os
import signal
import threading

LOGGER = logging.getLogger(__name__)

_lock = threading.Lock()
_shutdown_requested = False
_shutdown_reason: str | None = None


def shutdown_requested() -> bool:
    """Return True when a stop-on-failed / admin stop was requested."""
    return _shutdown_requested


def shutdown_reason() -> str | None:
    """Return the last shutdown reason, if any."""
    return _shutdown_reason


def request_ingest_shutdown(reason: str, *, force_exit: bool = False) -> None:
    """Ask the ingest process to exit (SIGTERM), once.

    Args:
        reason: Human-readable cause (logged and returned by ``/ingest/stop``).
        force_exit: When True, call ``os._exit(1)`` after signaling (last resort).

    Example:
        >>> request_ingest_shutdown  # doctest: +ELLIPSIS
        <function request_ingest_shutdown...>
    """
    global _shutdown_requested, _shutdown_reason
    with _lock:
        if _shutdown_requested:
            return
        _shutdown_requested = True
        _shutdown_reason = reason
    LOGGER.error("Ingest shutdown requested: %s", reason)
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except OSError as exc:
        LOGGER.warning("SIGTERM failed (%s); falling back to exit", exc)
        force_exit = True
    if force_exit:
        # BackgroundTasks / stuck pipelines — hard stop for fast debug loops.
        os._exit(1)
