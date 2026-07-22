"""Title: Outbound MCP client with egress allow-list (Phase D).

Protocol plumbing only — agent logic stays in ``thot.agent``. External tool
outputs always pass through :func:`thot.agent.safety.wrap_untrusted`.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import yaml

from thot.agent.safety import wrap_untrusted
from thot.core.TkeirPaths import configs_dir
from thot.mcp.authz import McpPrincipal

LOGGER = logging.getLogger(__name__)


class OutboundTransport(Protocol):
    """Swappable transport for one external MCP server."""

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Invoke a remote tool and return a JSON-able result."""


@dataclass(frozen=True)
class EgressRule:
    """One allow-list entry."""

    host: str
    ports: tuple[int, ...] = ()
    tools: tuple[str, ...] = ()


@dataclass
class EgressPolicy:
    """Deny-by-default egress gate for outbound MCP HTTP.

    Example:
        >>> from thot.mcp.client import EgressPolicy, EgressRule
        >>> p = EgressPolicy(rules=(EgressRule("127.0.0.1", (8099,), ("echo_cite",)),))
        >>> p.allows_url("http://127.0.0.1:8099/mcp/call", tool="echo_cite")
        True
        >>> p.allows_url("http://evil.example:8099/mcp/call", tool="echo_cite")
        False
    """

    rules: tuple[EgressRule, ...] = ()
    mode: str = "observe"

    def allows_host_port_tool(
        self, host: str, port: int | None, tool: str
    ) -> bool:
        host_l = (host or "").lower()
        for rule in self.rules:
            if rule.host.lower() != host_l:
                continue
            if rule.ports and port is not None and port not in rule.ports:
                continue
            if rule.tools and tool not in rule.tools:
                continue
            return True
        return False

    def allows_url(self, url: str, *, tool: str) -> bool:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme == "https" else 80
        return self.allows_host_port_tool(host, port, tool)

    def check_or_raise(self, url: str, *, tool: str) -> None:
        if self.allows_url(url, tool=tool):
            return
        msg = f"egress denied for tool={tool!r} url={url!r}"
        if self.mode == "enforce":
            raise PermissionError(msg)
        LOGGER.warning("%s (observe mode — allowing)", msg)


def load_egress_policy(
    path: Path | None = None,
) -> EgressPolicy:
    """Load egress allow-list from ``configs/mcp-client.yaml``.

    Example:
        >>> from thot.mcp.client import load_egress_policy
        >>> policy = load_egress_policy()
        >>> isinstance(policy.rules, tuple)
        True
    """
    cfg_path = path or Path(configs_dir()) / "mcp-client.yaml"
    mode = (os.getenv("GOVERNOR_MODE") or "observe").lower()
    if not cfg_path.is_file():
        return EgressPolicy(rules=(), mode=mode)
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    mode = str(raw.get("governor_mode") or mode).lower()
    rules: list[EgressRule] = []
    for item in raw.get("egress_allowlist") or []:
        if not isinstance(item, dict):
            continue
        host = str(item.get("host") or "")
        ports = tuple(int(p) for p in item.get("ports") or [])
        tools = tuple(str(t) for t in item.get("tools") or [])
        if host:
            rules.append(EgressRule(host=host, ports=ports, tools=tools))
    return EgressPolicy(rules=tuple(rules), mode=mode)


@dataclass
class ExternalToolSpec:
    """Declarative external tool bound to a transport."""

    name: str
    description: str
    input_schema: dict[str, Any]
    transport: OutboundTransport
    base_url: str = ""
    intent: str = "tool.invoke"


@dataclass
class OutboundMcpClient:
    """Registry of external MCP tools behind an egress policy.

    Example:
        >>> import asyncio
        >>> from thot.mcp.client import OutboundMcpClient, ExternalToolSpec, EgressPolicy
        >>> from thot.mcp.authz import McpPrincipal

        >>> class _Echo:
        ...     async def call_tool(self, name, arguments):
        ...         return {"echo": arguments, "user_space": "alice", "chunk_ids": ["c1"]}
        >>> client = OutboundMcpClient(
        ...     policy=EgressPolicy(rules=(), mode="observe"),
        ... )
        >>> client.register(ExternalToolSpec(
        ...     name="echo_cite",
        ...     description="echo",
        ...     input_schema={"type": "object", "properties": {"text": {"type": "string"}},
        ...                   "required": ["text"], "additionalProperties": False},
        ...     transport=_Echo(),
        ...     base_url="in-process://echo",
        ... ))
        >>> out = asyncio.run(client.invoke(
        ...     "echo_cite", {"text": "hi"}, principal=McpPrincipal(user_space="alice"),
        ... ))
        >>> out["echo"]["text"]
        'hi'
        >>> "_untrusted_view" in out
        True
    """

    policy: EgressPolicy = field(default_factory=load_egress_policy)
    tools: dict[str, ExternalToolSpec] = field(default_factory=dict)

    def register(self, spec: ExternalToolSpec) -> None:
        self.tools[spec.name] = spec

    def list_names(self) -> list[str]:
        return sorted(self.tools)

    def has(self, name: str) -> bool:
        return name in self.tools

    def tool_specs_for_prompt(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "inputSchema": spec.input_schema,
                "external": True,
            }
            for spec in self.tools.values()
        ]

    async def invoke(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        principal: McpPrincipal,
    ) -> dict[str, Any]:
        """Call an external tool; wrap result as untrusted data."""
        if name not in self.tools:
            raise KeyError(f"unknown external tool: {name}")
        spec = self.tools[name]
        # In-process transports use a non-http URL and skip host checks when
        # base_url starts with in-process:// — still require tool allow-list
        # when any rule lists tools.
        if spec.base_url.startswith("http://") or spec.base_url.startswith(
            "https://"
        ):
            self.policy.check_or_raise(spec.base_url, tool=name)
        elif self.policy.rules:
            # Still enforce tool name against allow-list tools union
            allowed_tools = {
                t for rule in self.policy.rules for t in rule.tools
            }
            if allowed_tools and name not in allowed_tools:
                msg = f"egress denied for tool={name!r} (not in allow-list)"
                if self.policy.mode == "enforce":
                    raise PermissionError(msg)
                LOGGER.warning("%s (observe — allowing)", msg)

        result = await spec.transport.call_tool(name, dict(arguments or {}))
        if not isinstance(result, dict):
            result = {"result": result}
        # Force tenant stamp; never trust remote user_space
        result["user_space"] = principal.user_space
        result["_untrusted_view"] = wrap_untrusted(
            result, source=f"mcp-external:{name}"
        )
        return result


class HttpJsonMcpTransport:
    """HTTP transport matching tkeir-mcp ``POST /mcp/call`` shape."""

    def __init__(self, base_url: str, *, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/mcp/call",
                json={"name": name, "arguments": arguments},
            )
            response.raise_for_status()
            payload = response.json()
        if isinstance(payload, dict) and "result" in payload:
            result = payload["result"]
            return result if isinstance(result, dict) else {"result": result}
        return payload if isinstance(payload, dict) else {"result": payload}


def build_echo_cite_tool(
    *, transport: OutboundTransport | None = None
) -> ExternalToolSpec:
    """Built-in demo/test external tool that echoes text with a citation id.

    Example:
        >>> from thot.mcp.client import build_echo_cite_tool
        >>> build_echo_cite_tool().name
        'echo_cite'
    """

    class _LocalEcho:
        async def call_tool(self, name: str, arguments: dict[str, Any]):
            text = str(arguments.get("text") or "")
            return {
                "text": text,
                "chunk_ids": ["ext-echo-1"],
                "note": "external echo_cite",
            }

    return ExternalToolSpec(
        name="echo_cite",
        description=(
            "External MCP demo tool: echo text and return a synthetic "
            "chunk_id citation (egress-gated)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to echo",
                }
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        transport=transport or _LocalEcho(),
        base_url="in-process://echo_cite",
    )


def default_outbound_client(
    *, include_echo_cite: bool = True
) -> OutboundMcpClient:
    """Build the process default outbound client.

    Example:
        >>> from thot.mcp.client import default_outbound_client
        >>> "echo_cite" in default_outbound_client().list_names()
        True
    """
    client = OutboundMcpClient(policy=load_egress_policy())
    if include_echo_cite:
        client.register(build_echo_cite_tool())
    return client
