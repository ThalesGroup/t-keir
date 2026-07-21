# Intent ↔ OAuth scope alignment (Policy-as-Code).
# Evaluated by tkeir-governor in-process today; bundle for OPA sidecar later.
# Phase A MCP tools (search, rag_query, ontology_query, document_get) all map
# to intent "search" / scope "intent:search" — see thot/mcp/tools_catalog.py.
#
# Agent mastering (ADR-0008): agent intents additionally require a SPIFFE ID
# under the agent prefix when input.spiffe_enforce is true.
#
# Input shape (future OPA):
#   input.intent          — declared intent (search, ingest, …)
#   input.scopes          — OAuth scopes from JWT
#   input.mode            — governor mode (observe|enforce)
#   input.spiffe_id       — workload SPIFFE ID (agents)
#   input.spiffe_enforce  — bool

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

agent_intents := {"agent.run", "generate", "tool.invoke"}

default_agent_prefix := "spiffe://tkeir.local/agent/"

allow if {
    input.intent == "admin.override"
    "intent:admin.override" in input.scopes
}

allow if {
    required := intent_scope[input.intent]
    required in input.scopes
    agent_spiffe_ok
}

agent_spiffe_ok if {
    not input.spiffe_enforce
}

agent_spiffe_ok if {
    not agent_intents[input.intent]
}

agent_spiffe_ok if {
    agent_intents[input.intent]
    input.spiffe_enforce
    startswith(input.spiffe_id, default_agent_prefix)
}

deny_reason := sprintf("missing scope %v for intent %v", [required, input.intent]) if {
    required := intent_scope[input.intent]
    not required in input.scopes
    not "intent:admin.override" in input.scopes
}

deny_reason := sprintf("missing or disallowed agent SPIFFE ID %v", [input.spiffe_id]) if {
    agent_intents[input.intent]
    input.spiffe_enforce
    not startswith(input.spiffe_id, default_agent_prefix)
}
