"""Title: Structured Logging

Structured JSON and text logging helpers for platform services.

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

# Shared text line format for CLI / ThotLogger / eval.
TEXT_LOG_FORMAT = (
    "%(asctime)s [%(levelname)s] %(name)s "
    "%(filename)s:%(funcName)s:%(lineno)d "
    "[correlation-id:%(correlation_id)s] %(message)s"
)
TEXT_LOG_DATEFMT = "%H:%M:%S"


def _utc_ts() -> str:
    """Return current UTC time as ISO-8601 with millisecond ``Z`` suffix.

    Example:
        >>> ts = _utc_ts()
        >>> ts.endswith("Z") and "T" in ts
        True
    """
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _record_correlation_id(record: logging.LogRecord) -> str:
    """Resolve correlation id for a log record (explicit → context → ``-``).

    Example:
        >>> rec = logging.LogRecord(
        ...     "t", logging.INFO, __file__, 1, "hi", (), None
        ... )
        >>> rec.correlation_id = "abc"
        >>> _record_correlation_id(rec)
        'abc'
    """
    explicit = getattr(record, "correlation_id", None)
    if explicit not in (None, ""):
        return str(explicit)
    bound = current_correlation_id()
    return bound if bound else "-"


class CorrelationIdFilter(logging.Filter):
    """Ensure every record has ``correlation_id`` for formatters."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Stamp ``record.correlation_id`` and allow the record through.

        Example:
            >>> filt = CorrelationIdFilter()
            >>> rec = logging.LogRecord(
            ...     "t", logging.INFO, __file__, 1, "hi", (), None
            ... )
            >>> filt.filter(rec)
            True
            >>> hasattr(rec, "correlation_id")
            True
        """
        record.correlation_id = _record_correlation_id(record)
        return True


class TkeirTextFormatter(logging.Formatter):
    """Human-readable logs with file, function, line, and correlation-id."""

    def __init__(self) -> None:
        """Initialize formatter with :data:`TEXT_LOG_FORMAT`.

        Example:
            >>> fmt = TkeirTextFormatter()
            >>> fmt._fmt is not None
            True
        """
        super().__init__(fmt=TEXT_LOG_FORMAT, datefmt=TEXT_LOG_DATEFMT)

    def format(self, record: logging.LogRecord) -> str:
        """Format ``record`` as a text line with correlation-id.

        Example:
            >>> fmt = TkeirTextFormatter()
            >>> rec = logging.LogRecord(
            ...     "t", logging.INFO, __file__, 1, "hello", (), None
            ... )
            >>> "hello" in fmt.format(rec)
            True
        """
        record.correlation_id = _record_correlation_id(record)
        return super().format(record)


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
            "correlation_id": _record_correlation_id(record),
            "action_id": (
                getattr(record, "action_id", None) or current_action_id() or ""
            ),
            "actor": getattr(record, "actor", None) or "",
            "file": record.filename,
            "function": record.funcName or "",
            "line": record.lineno,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("http_status", "path"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_text_logging(
    *,
    level: int = logging.INFO,
    force: bool = True,
) -> None:
    """Configure root logging with file/function/line/correlation-id.

    Example:
        >>> configure_text_logging(level=logging.INFO)
    """
    root = logging.getLogger()
    if force:
        for handler in list(root.handlers):
            root.removeHandler(handler)
    elif root.handlers:
        root.setLevel(level)
        return
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.addFilter(CorrelationIdFilter())
    handler.setFormatter(TkeirTextFormatter())
    root.addHandler(handler)


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
    handler.addFilter(CorrelationIdFilter())
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
