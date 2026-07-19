# Intent ↔ OAuth scope alignment (Policy-as-Code).
# Evaluated by tkeir-governor in-process today; bundle for OPA sidecar later.
# Phase A MCP tools (search, rag_query, ontology_query, document_get) all map
# to intent "search" / scope "intent:search" — see thot/mcp/tools_catalog.py.
#
# Input shape (future OPA):
#   input.intent     — declared intent (search, ingest, …)
#   input.scopes     — OAuth scopes from JWT
#   input.mode       — governor mode (observe|enforce)

package tkeir.intents

default allow := false

intent_scope := {
    "search": "intent:search",
    "ingest": "intent:ingest",
    "index": "intent:index",
    "delete": "intent:delete",
    "audit.read": "intent:audit.read",
    "agent.run": "intent:agent.run",
    "generate": "intent:generate",
    "tool.invoke": "intent:tool.invoke",
}

allow if {
    input.intent == "admin.override"
    "intent:admin.override" in input.scopes
}

allow if {
    required := intent_scope[input.intent]
    required in input.scopes
}

deny_reason := sprintf("missing scope %v for intent %v", [required, input.intent]) if {
    required := intent_scope[input.intent]
    not required in input.scopes
    not "intent:admin.override" in input.scopes
}
