"""Title: action package init

Action identity package — correlation, ActionRecord, observe middleware.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.action.correlation import (
    CORRELATION_HEADER,
    TraceContext,
    current_action_id,
    current_correlation_id,
    generate_trace_id,
    get_trace_context,
    parse_traceparent,
    reset_trace_context,
    set_trace_context,
)
from thot.action.models import ActionRecord, new_action_id

__all__ = [
    "ActionRecord",
    "CORRELATION_HEADER",
    "TraceContext",
    "current_action_id",
    "current_correlation_id",
    "generate_trace_id",
    "get_trace_context",
    "new_action_id",
    "parse_traceparent",
    "reset_trace_context",
    "set_trace_context",
]
