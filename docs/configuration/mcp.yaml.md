# `mcp.yaml` / `mcp-client.yaml` — configuration reference

Paths:

- Server: `tkeir/configs/mcp.yaml`
- Client: `tkeir/configs/mcp-client.yaml`

See also [MCP server](../tools/mcp.md) for tool contracts and auth flows.

## `mcp.yaml` (server)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `service` | string | `tkeir-mcp` | Service name (logs / metrics) |
| `host` | string | `0.0.0.0` | Bind address |
| `port` | int | `8093` | Listen port |
| `auth_enabled` | bool | `false` | When true, require Bearer JWT with `intent:search` (or `MCP_DEV_TOKEN`) |
| `governor_mode` | enum | `observe` | `observe` = missing scope logged; `enforce` = deny |
| `rag_url` | string | `""` | Optional RAG HTTP base for `rag_query` generation (e.g. `http://tkeir-api:8090`) |
| `tools.search` | bool | `true` | Expose search / passage-retrieval tool |
| `tools.rag_query` | bool | `true` | Expose generation tool (needs `rag_url`) |
| `tools.ontology_query` | bool | `true` | Expose ontology reasoner tool |
| `tools.document_get` | bool | `true` | Expose document fetch by id / ref |

## `mcp-client.yaml` (client)

Client connection settings for agents / CLI that call the MCP server (URL, timeouts, optional auth header). Field-level detail and examples: [MCP](../tools/mcp.md).

## Related

- [Configuration overview](index.md)  
- Retrieval behaviour when `tools.search` is on: [rag.yaml](rag.yaml.md)
