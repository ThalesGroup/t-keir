"""Title: Structured Logging

Structured JSON logging helpers for platform services.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from thot import __version__ as TKEIR_VERSION
from thot.action.correlation import current_action_id, current_correlation_id


def _utc_ts() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class JsonLogFormatter(logging.Formatter):
    """Format log records as single-line JSON for stdout collectors."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize ``record`` to a JSON object string.

        Example:
            >>> fmt = JsonLogFormatter()
            >>> rec = logging.LogRecord(
            ...     "t", logging.INFO, __file__, 1, "hello", (), None
            ... )
            >>> '"msg": "hello"' in fmt.format(rec)
            True
        """
        payload: dict[str, Any] = {
            "ts": _utc_ts(),
            "level": record.levelname.lower(),
            "service": (
                getattr(record, "service", None)
                or os.getenv("TKEIR_SERVICE", "tkeir")
            ),
            "version": getattr(record, "version", None) or TKEIR_VERSION,
            "correlation_id": (
                getattr(record, "correlation_id", None)
                or current_correlation_id()
                or ""
            ),
            "action_id": (
                getattr(record, "action_id", None) or current_action_id() or ""
            ),
            "actor": getattr(record, "actor", None) or "",
            "msg": record.getMessage(),
        }
        for key in ("http_status", "path", "logger"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_json_logging(
    *,
    service: str | None = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """Attach a JSON stdout handler to the ``tkeir`` logger.

    Does not replace :class:`~thot.core.ThotLogger.ThotLogger` (CLI keeps
    the text format unless callers opt in). Safe to call multiple times.

    Example:
        >>> log = configure_json_logging(service="test")
        >>> log.name
        'tkeir'
    """
    logger = logging.getLogger("tkeir")
    logger.setLevel(level)
    logger.propagate = False
    marker = "tkeir-json-handler"
    for handler in list(logger.handlers):
        if getattr(handler, "_tkeir_marker", None) == marker:
            logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    handler._tkeir_marker = marker  # type: ignore[attr-defined]
    logger.addHandler(handler)
    if service:
        os.environ.setdefault("TKEIR_SERVICE", service)
    return logger


def log_structured(
    level: str,
    msg: str,
    *,
    service: str | None = None,
    correlation_id: str | None = None,
    action_id: str | None = None,
    actor: str | None = None,
    **extra: Any,
) -> None:
    """Emit one structured JSON log line via the ``tkeir`` logger.

    Example:
        >>> _ = configure_json_logging(service="unit")
        >>> log_structured("info", "ping", path="/x")
    """
    logger = logging.getLogger("tkeir")
    if not logger.handlers:
        configure_json_logging(service=service)
    record_extra = {
        "service": service or os.getenv("TKEIR_SERVICE", "tkeir"),
        "version": TKEIR_VERSION,
        "correlation_id": correlation_id or current_correlation_id() or "",
        "action_id": action_id or current_action_id() or "",
        "actor": actor or "",
        **extra,
    }
    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn(msg, extra=record_extra)
