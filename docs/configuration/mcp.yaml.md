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

## `mcp-client.yaml` (outbound client)

Path: `tkeir/configs/mcp-client.yaml`  
Used by **agents** for **external** MCP servers (egress). Internal T-KEIR
tools (`search`, `rag_query`, …) never go through this file — they call
`McpHandlers` in-process. See [MCP](../tools/mcp.md).

```yaml
governor_mode: observe
egress_allowlist:
  - host: "127.0.0.1"
    ports: [8099]
    tools: ["echo_cite"]
servers: {}
```

| Field | Default | Effect |
|-------|---------|--------|
| `governor_mode` | `observe` | `observe` logs disallowed egress; `enforce` **denies** the tool call. Independent of `mcp.yaml` `governor_mode`. |
| `egress_allowlist[]` | shipped localhost `echo_cite` | Empty list = **deny all** remote HTTP MCP. Each row must match host **and** port **and** tool name. |
| `egress_allowlist[].host` | required | Exact host (`127.0.0.1` and `localhost` are separate rows). |
| `egress_allowlist[].ports` | required | Allowed TCP ports for that host. |
| `egress_allowlist[].tools` | required | Tool names the agent may invoke on that host:port. |
| `servers` | `{}` | Named remote MCP servers. Tests inject in-process transports. Production example: `servers.echo.base_url` + `servers.echo.tools`. |

Workflow YAML `external_tools:` must list the same tool names
(`echo_cite`, …) or the orchestrator will not offer them.

## Related

- [Configuration overview](index.md)  
- Retrieval behaviour when `tools.search` is on: [rag.yaml](rag.yaml.md)
