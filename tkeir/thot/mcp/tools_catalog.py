"""Title: Declarative MCP tool catalogue for T-KEIR read-only tools.

Example:
    >>> from thot.mcp.tools_catalog import list_tool_names
    >>> "search" in list_tool_names()
    True

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    """One MCP tool: schema, intent, and handler name.

    Attributes:
        name: Tool name exposed to MCP clients.
        description: Human-readable summary.
        input_schema: JSON Schema for arguments (never includes ``user_space``).
        intent: Governor / OPA intent (Phase A: ``search`` for all read tools).
        handler: Key in the handler registry.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    intent: str = "search"
    handler: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="search",
        description=(
            "Hybrid retrieval over the caller's indexes (BM25 + ANN). "
            "Pass search_mode='both' to fuse shared global corpus AND "
            "personal user space. Tenant isolation is enforced server-side."
        ),
        intent="search",
        handler="search",
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language search query",
                },
                "hits": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 10,
                    "description": "Maximum chunk hits to return",
                },
                "language": {
                    "type": "string",
                    "description": "Optional language hint (e.g. en, fr)",
                },
                "search_mode": {
                    "type": "string",
                    "enum": ["auto", "global", "user", "both"],
                    "description": (
                        "Dual-hybrid index mode. Use 'both' to search "
                        "shared global corpus AND personal user space."
                    ),
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="rag_query",
        description=(
            "Retrieval-augmented generation scoped to the caller's "
            "user_space. Returns answer, report_markdown, ontology summary, "
            "and grounded chunks when the RAG backend is available. "
            "Pass search_mode='both' to fuse global + user indexes."
        ),
        intent="search",
        handler="rag_query",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "hits": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 8,
                },
                "language": {"type": "string"},
                "generate": {
                    "type": "boolean",
                    "default": True,
                    "description": "If false, return retrieval-only results",
                },
                "search_mode": {
                    "type": "string",
                    "enum": ["auto", "global", "user", "both"],
                    "description": (
                        "Dual-hybrid index mode. Use 'both' for global + user."
                    ),
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="ontology_query",
        description=(
            "Merge RDF Turtle/JSON-LD from retrieved parent documents in the "
            "caller's user_space and return a prompt-oriented summary plus "
            "optional keyword / entity filters."
        ),
        intent="search",
        handler="ontology_query",
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Query used to select parent documents",
                },
                "hits": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 30,
                    "default": 5,
                },
                "max_triples": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 40,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="document_get",
        description=(
            "Fetch one parent document by source_doc_id or Vespa document "
            "reference. Fails if the document is outside the caller's "
            "user_space."
        ),
        intent="search",
        handler="document_get",
        input_schema={
            "type": "object",
            "properties": {
                "source_doc_id": {
                    "type": "string",
                    "description": "Pipeline source_doc_id (preferred)",
                },
                "doc_ref": {
                    "type": "string",
                    "description": "Full Vespa document id (optional)",
                },
            },
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="okf_bundle_list",
        description=(
            "List OKF knowledge bundles available in the caller's user_space."
        ),
        intent="search",
        handler="okf_bundle_list",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="okf_bundle_get",
        description=(
            "Return the OKF index.md and concept list for a bundle. "
            "When concept_id is set, return that concept's full markdown."
        ),
        intent="search",
        handler="okf_bundle_get",
        input_schema={
            "type": "object",
            "properties": {
                "bundle_id": {
                    "type": "string",
                    "description": "OKF bundle identifier",
                },
                "concept_id": {
                    "type": "string",
                    "description": (
                        "Optional bundle-relative concept path without .md"
                    ),
                },
            },
            "required": ["bundle_id"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="workspace_wiki_list",
        description=(
            "List LLM Wiki markdown files under the caller's personal "
            "workspace (typically wiki/). Optional prior context for agents."
        ),
        intent="search",
        handler="workspace_wiki_list",
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "default": "wiki",
                    "description": (
                        "Workspace-relative directory (default wiki)"
                    ),
                },
            },
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="workspace_wiki_get",
        description=(
            "Read one LLM Wiki markdown file from the caller's personal "
            "workspace by relative path."
        ),
        intent="search",
        handler="workspace_wiki_get",
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Workspace-relative path (e.g. wiki/foo.md)"
                    ),
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="okf_wiki_put",
        description=(
            "Write or overwrite the LLMWiki page (wiki.md) for an OKF bundle "
            "owned by the caller. Markdown must be grounded in prior findings."
        ),
        intent="search",
        handler="okf_wiki_put",
        input_schema={
            "type": "object",
            "properties": {
                "bundle_id": {
                    "type": "string",
                    "description": "OKF bundle identifier",
                },
                "markdown": {
                    "type": "string",
                    "description": "Full LLMWiki markdown (type: Wiki)",
                },
            },
            "required": ["bundle_id", "markdown"],
            "additionalProperties": False,
        },
    ),
)


def list_tool_names() -> list[str]:
    """Return registered MCP tool names.

    Example:
        >>> from thot.mcp.tools_catalog import list_tool_names
        >>> sorted(list_tool_names())[0]
        'document_get'
    """
    return [tool.name for tool in TOOLS]


def get_tool(name: str) -> ToolSpec:
    """Look up a tool by name.

    Example:
        >>> from thot.mcp.tools_catalog import get_tool
        >>> get_tool("search").intent
        'search'
    """
    for tool in TOOLS:
        if tool.name == name:
            return tool
    raise KeyError(f"unknown MCP tool: {name}")


def tools_as_mcp_list() -> list[dict[str, Any]]:
    """Serialize tools for MCP ``tools/list`` responses.

    Example:
        >>> from thot.mcp.tools_catalog import tools_as_mcp_list
        >>> tools_as_mcp_list()[0]["name"] in list_tool_names()
        True
    """
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.input_schema,
        }
        for tool in TOOLS
    ]
