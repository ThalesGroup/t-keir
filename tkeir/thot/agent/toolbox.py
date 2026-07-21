"""Tool registry: internal MCP handlers + outbound external MCP tools."""

from __future__ import annotations

from typing import Any

from thot.agent.safety import assert_tool_allowlisted, wrap_untrusted
from thot.mcp.authz import McpPrincipal, strip_tenant_overrides
from thot.mcp.client import OutboundMcpClient
from thot.mcp.handlers import McpHandlers
from thot.mcp.tools_catalog import TOOLS, get_tool


def _validate_required(
    schema: dict[str, Any], arguments: dict[str, Any]
) -> None:
    for key in schema.get("required") or []:
        if key not in arguments:
            raise ValueError(f"missing required argument: {key}")


def _validate_no_extra_props(
    schema: dict[str, Any], arguments: dict[str, Any]
) -> None:
    if schema.get("additionalProperties") is not False:
        return
    allowed = set((schema.get("properties") or {}).keys())
    extra = set(arguments) - allowed
    if extra:
        raise ValueError(f"unexpected arguments: {sorted(extra)}")


def _validate_prop_type(key: str, value: Any, prop: dict[str, Any]) -> None:
    expected = prop.get("type")
    type_checks: dict[str, tuple[type, str]] = {
        "string": (str, "string"),
        "integer": (int, "integer"),
        "boolean": (bool, "boolean"),
    }
    if expected in type_checks:
        py_type, label = type_checks[expected]
        if not isinstance(value, py_type):
            raise ValueError(f"{key} must be {label}")
    if expected != "integer":
        return
    if "minimum" in prop and value < prop["minimum"]:
        raise ValueError(f"{key} below minimum")
    if "maximum" in prop and value > prop["maximum"]:
        raise ValueError(f"{key} above maximum")


def _validate_args(schema: dict[str, Any], arguments: dict[str, Any]) -> None:
    """Minimal JSON Schema checks (required + additionalProperties=false)."""
    _validate_required(schema, arguments)
    _validate_no_extra_props(schema, arguments)
    props = schema.get("properties") or {}
    for key, value in arguments.items():
        _validate_prop_type(key, value, props.get(key) or {})


class ToolRegistry:
    """Per-agent allow-listed tools (internal + optional outbound MCP).

    Example:
        >>> from thot.agent.toolbox import ToolRegistry
        >>> from thot.mcp.authz import McpPrincipal
        >>> reg = ToolRegistry(allow_list=["search"])
        >>> "search" in reg.list_names()
        True
    """

    def __init__(
        self,
        allow_list: list[str],
        *,
        handlers: McpHandlers | None = None,
        outbound: OutboundMcpClient | None = None,
    ) -> None:
        self.outbound = outbound
        internal = {t.name for t in TOOLS}
        external = set(outbound.list_names()) if outbound else set()
        known = internal | external
        unknown = [name for name in allow_list if name not in known]
        if unknown:
            raise ValueError(f"unknown tools in allow-list: {unknown}")
        self.allow_list = list(allow_list)
        self.handlers = handlers or McpHandlers()

    def list_names(self) -> list[str]:
        return list(self.allow_list)

    def tool_specs_for_prompt(self) -> list[dict[str, Any]]:
        """Compact tool schemas for the LLM system/user prompt."""
        specs = []
        for name in self.allow_list:
            if self.outbound and self.outbound.has(name):
                for item in self.outbound.tool_specs_for_prompt():
                    if item["name"] == name:
                        specs.append(item)
                        break
                continue
            tool = get_tool(name)
            specs.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.input_schema,
                }
            )
        return specs

    async def invoke(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        principal: McpPrincipal,
    ) -> dict[str, Any]:
        """Validate, strip tenant overrides, execute, wrap observation.

        Example:
            >>> import asyncio
            >>> from thot.agent.toolbox import ToolRegistry
            >>> from thot.mcp.authz import McpPrincipal
            >>> from thot.mcp.handlers import McpHandlers

            >>> class _Stub:
            ...     async def hybrid_search(self, query, **kw):
            ...         return {"query": query, "user_space": kw["user_space"], "chunks": []}
            ...     async def rag_query(self, query, **kw):
            ...         return await self.hybrid_search(query, **kw)
            ...     async def get_document(self, **kw):
            ...         return {"user_space": kw["user_space"], "fields": {}}
            ...     async def ontology_from_query(self, query, **kw):
            ...         return {"user_space": kw["user_space"], "summary": ""}
            >>> reg = ToolRegistry(["search"], handlers=McpHandlers(backend=_Stub()))
            >>> out = asyncio.run(reg.invoke(
            ...     "search",
            ...     {"query": "q", "user_space": "evil"},
            ...     principal=McpPrincipal(user_space="alice"),
            ... ))
            >>> out["user_space"]
            'alice'
        """
        assert_tool_allowlisted(name, self.allow_list)
        args = strip_tenant_overrides(dict(arguments or {}))
        if principal.user_space and args.get("user_space"):
            raise PermissionError("user_space cannot be supplied in tool args")

        if self.outbound and self.outbound.has(name):
            spec = self.outbound.tools[name]
            _validate_args(spec.input_schema, args)
            return await self.outbound.invoke(name, args, principal=principal)

        tool = get_tool(name)
        _validate_args(tool.input_schema, args)
        result = await self.handlers.invoke(name, args, principal)
        returned = result.get("user_space")
        if returned is not None and str(returned) != principal.user_space:
            raise PermissionError(
                f"tool result user_space {returned!r} != {principal.user_space!r}"
            )
        result["_untrusted_view"] = wrap_untrusted(result, source=name)
        return result
