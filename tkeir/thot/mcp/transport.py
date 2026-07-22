"""Title: MCP transport isolation — official SDK behind a swappable facade.

The agent loop never imports ``mcp`` directly. This module may use the
SDK when installed; otherwise a FastAPI JSON tool API still serves tools.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable

LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from thot.mcp.server import McpRuntime


def mcp_sdk_available() -> bool:
    """Return True when the official ``mcp`` package can be imported.

    Example:
        >>> from thot.mcp.transport import mcp_sdk_available
        >>> isinstance(mcp_sdk_available(), bool)
        True
    """
    try:
        import mcp  # noqa: F401

        return True
    except ImportError:
        return False


async def run_stdio_server(
    runtime: "McpRuntime",
) -> None:
    """Serve tools over stdio using the official MCP SDK.

    Raises:
        RuntimeError: If the ``mcp`` package is not installed.

    Example:
        >>> from thot.mcp.transport import mcp_sdk_available
        >>> mcp_sdk_available() or True
        True
    """
    if not mcp_sdk_available():
        raise RuntimeError(
            "Official mcp package not installed. "
            "Install with: uv sync --extra mcp  (or pip install mcp)"
        )

    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    from thot.mcp.tools_catalog import TOOLS

    server = Server("tkeir-mcp")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=tool.name,
                description=tool.description,
                inputSchema=tool.input_schema,
            )
            for tool in TOOLS
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any] | None):
        result = await runtime.call_tool(
            name, arguments or {}, authorization=runtime.default_authorization
        )
        import json

        return [TextContent(type="text", text=json.dumps(result, default=str))]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


CallToolFn = Callable[
    [str, dict[str, Any], str | None],
    Awaitable[dict[str, Any]],
]
