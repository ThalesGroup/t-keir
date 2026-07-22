# MCP server (tkeir-mcp)

> Phase A — read-only MCP tools over the caller's Vespa streaming group.
> **Not an agent runtime** (that is [Agents](agents.md) / `tkeir-agent`).

## Who uses it (external vs agents)

**`tkeir-mcp` is the HTTP/stdio surface for external MCP clients** (Cursor,
Claude Desktop, other MCP hosts). Start it with `make mcp` when those clients
should call T-KEIR tools.

**Agents do not call this service.** `tkeir-agent` invokes the same
`McpHandlers` library **in-process** (Vespa + optional RAG via `MCP_RAG_URL`).
Search / `rag_query` work with Vespa (and RAG) alone — you do not need
`tkeir-mcp` running for agent or workflow runs.

```text
External MCP clients ──► tkeir-mcp (:8093) ──► McpHandlers ──► Vespa / RAG
                              ▲
                              │ same code (library)
tkeir-agent ──────────────────┴──► McpHandlers ──► Vespa / RAG
         (no hop through the MCP process)
```

Optional **outbound** tools (`configs/mcp-client.yaml`) are a separate path:
agents may call *other* egress-allow-listed MCP servers; that still does not
require the local `tkeir-mcp` process.

## What it exposes

| Tool | Intent | Purpose |
|------|--------|---------|
| `search` | `intent:search` | Hybrid retrieval in `user_space` |
| `rag_query` | `intent:search` | RAG (or retrieval-only if `MCP_RAG_URL` unset) |
| `ontology_query` | `intent:search` | Merge parent RDF + prompt summary |
| `document_get` | `intent:search` | Fetch one parent doc (cross-tenant denied) |

`user_space` is **never** accepted from tool arguments — it comes only from
Bearer JWT / `VESPA_USER_SPACE` / `dev@tkeir`.

## Run

```bash
# HTTP (Compose-friendly, default)
make mcp
# → http://localhost:8093/health  /mcp/tools  /mcp/call

# List tools + sample search (requires Vespa for real hits)
make mcp-tools MCP_QUERY="your question"

# Official MCP stdio transport (optional extra)
make mcp MCP_STDIO=1   # needs: uv sync --extra mcp
```

Compose profile:

```bash
make compose-up PROFILES=core,mcp
```

## Authz & audit

- `MCP_AUTH_ENABLED=true` requires Bearer with `intent:search` (or `MCP_DEV_TOKEN`).
- `GOVERNOR_MODE=observe|enforce` — observe fail-open on missing scope; enforce denies.
- Every tool call emits an `ActionRecord` (`ext.action_kind=tool.invoke`) with
  `correlation_id` and `user_space`.

## Layout

```text
tkeir/thot/mcp/
  transport.py     # isolates official mcp SDK
  tools_catalog.py
  authz.py
  handlers.py
  server.py        # tkeir-mcp entrypoint
```

See also [Vespa RAG](vespa_rag.md), [Agents](agents.md), and the regularity /
governor docs for intent scopes.
