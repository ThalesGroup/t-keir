"""Title: T-KEIR MCP server — read-only corpus tools (Phase A).

Protocol transport is isolated in :mod:`thot.mcp.transport` so the official
``mcp`` SDK can be swapped without touching agent or tool logic.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from thot.mcp.tools_catalog import TOOLS, ToolSpec, list_tool_names

__all__ = ["TOOLS", "ToolSpec", "list_tool_names"]
