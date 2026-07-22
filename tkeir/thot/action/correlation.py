"""Title: Correlation

W3C trace context helpers and request-scoped correlation IDs.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re
import secrets
from contextvars import ContextVar, Token
from dataclasses import dataclass

CORRELATION_HEADER = "X-Correlation-Id"
TRACEPARENT_HEADER = "traceparent"

_TRACEPARENT_RE = re.compile(
    r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$",
    re.IGNORECASE,
)
_HEX32_RE = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)

_trace_ctx: ContextVar[TraceContext | None] = ContextVar(
    "tkeir_trace_context", default=None
)


@dataclass(frozen=True)
class TraceContext:
    """Request-scoped correlation and action identifiers."""

    correlation_id: str
    action_id: str
    parent_span_id: str | None = None
    sampled: bool = True

    def traceparent(self) -> str:
        """Format a W3C ``traceparent`` header value.

        Example:
            >>> ctx = TraceContext("a" * 32, "01HTESTACTIONID00000000000")
            >>> ctx.traceparent().startswith("00-")
            True
        """
        span_id = (self.parent_span_id or _new_span_id()).lower()
        flags = "01" if self.sampled else "00"
        return f"00-{self.correlation_id.lower()}-{span_id}-{flags}"


def generate_trace_id() -> str:
    """Return a new 32-hex W3C trace-id.

    Example:
        >>> tid = generate_trace_id()
        >>> len(tid) == 32 and int(tid, 16) != 0
        True
    """
    while True:
        value = secrets.token_hex(16)
        if int(value, 16) != 0:
            return value


def _new_span_id() -> str:
    """Return a new 16-hex W3C span-id (non-zero)."""
    while True:
        value = secrets.token_hex(8)
        if int(value, 16) != 0:
            return value


def parse_traceparent(header: str | None) -> TraceContext | None:
    """Parse a W3C ``traceparent`` header into a :class:`TraceContext`.

    Args:
        header: Raw ``traceparent`` value, or ``None``.

    Returns:
        Parsed context, or ``None`` when the header is absent/invalid.

    Example:
        >>> tp = "00-" + ("b" * 32) + "-" + ("c" * 16) + "-01"
        >>> ctx = parse_traceparent(tp)
        >>> ctx is not None and ctx.correlation_id == "b" * 32
        True
    """
    if not header:
        return None
    match = _TRACEPARENT_RE.match(header.strip())
    if not match:
        return None
    _version, trace_id, parent_span, flags = match.groups()
    if int(trace_id, 16) == 0 or int(parent_span, 16) == 0:
        return None
    sampled = (int(flags, 16) & 0x01) == 0x01
    from thot.action.models import new_action_id

    return TraceContext(
        correlation_id=trace_id.lower(),
        action_id=new_action_id(),
        parent_span_id=parent_span.lower(),
        sampled=sampled,
    )


def correlation_from_headers(
    traceparent: str | None,
    correlation_id: str | None,
) -> TraceContext:
    """Resolve correlation from inbound headers or generate a new context.

    Preference order: valid ``traceparent``, then a 32-hex
    ``X-Correlation-Id``, else generate both ids.

    Example:
        >>> ctx = correlation_from_headers(None, "d" * 32)
        >>> ctx.correlation_id == "d" * 32
        True
    """
    parsed = parse_traceparent(traceparent)
    if parsed is not None:
        return parsed
    from thot.action.models import new_action_id

    if correlation_id and _HEX32_RE.match(correlation_id.strip()):
        return TraceContext(
            correlation_id=correlation_id.strip().lower(),
            action_id=new_action_id(),
        )
    return TraceContext(
        correlation_id=generate_trace_id(),
        action_id=new_action_id(),
    )


def set_trace_context(ctx: TraceContext) -> Token:
    """Bind ``ctx`` to the current contextvar; return a reset token."""
    return _trace_ctx.set(ctx)


def reset_trace_context(token: Token) -> None:
    """Restore the previous trace context from ``token``."""
    _trace_ctx.reset(token)


def get_trace_context() -> TraceContext | None:
    """Return the bound :class:`TraceContext`, if any."""
    return _trace_ctx.get()


def current_correlation_id() -> str | None:
    """Return the bound correlation id, or ``None``."""
    ctx = _trace_ctx.get()
    return None if ctx is None else ctx.correlation_id


def current_action_id() -> str | None:
    """Return the bound action id, or ``None``."""
    ctx = _trace_ctx.get()
    return None if ctx is None else ctx.action_id
