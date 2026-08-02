"""Title: Catalog authz

Unit tests for MCP tool catalogue and authz.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import base64
import json

import pytest

from thot.mcp.authz import (
    McpAuthError,
    authorize_tool,
    opa_allows_intent,
    resolve_principal,
    strip_tenant_overrides,
)
from thot.mcp.tools_catalog import get_tool, list_tool_names, tools_as_mcp_list


def _bearer(claims: dict) -> str:
    body = (
        base64.urlsafe_b64encode(json.dumps(claims).encode())
        .decode()
        .rstrip("=")
    )
    return f"Bearer h.{body}.s"


def test_catalogue_lists_phase_a_tools():
    names = set(list_tool_names())
    assert names == {"search", "rag_query", "ontology_query", "document_get"}
    for name in names:
        assert get_tool(name).intent == "search"
        assert "user_space" not in get_tool(name).input_schema.get(
            "properties", {}
        )


def test_tools_as_mcp_list_has_schemas():
    tools = tools_as_mcp_list()
    assert all("inputSchema" in t for t in tools)


def test_strip_tenant_overrides():
    cleaned = strip_tenant_overrides(
        {"query": "q", "user_space": "evil", "group": "x"}
    )
    assert cleaned == {"query": "q"}


def test_resolve_principal_dev_default(monkeypatch):
    monkeypatch.delenv("MCP_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("VESPA_USER_SPACE", raising=False)
    principal = resolve_principal(None)
    assert principal.user_space == "dev@tkeir"
    assert "intent:search" in principal.scopes


def test_resolve_principal_from_jwt(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_ENABLED", "true")
    principal = resolve_principal(
        _bearer(
            {
                "preferred_username": "alice",
                "scope": "intent:search openid",
            }
        )
    )
    assert principal.user_space == "alice"
    assert "intent:search" in principal.scopes


def test_auth_enabled_requires_bearer(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_ENABLED", "true")
    with pytest.raises(McpAuthError) as exc:
        resolve_principal(None)
    assert exc.value.status_code == 401


def test_opa_enforce_denies_missing_scope():
    ok, _ = opa_allows_intent(intent="search", scopes=[], mode="enforce")
    assert ok is False
    ok, _ = opa_allows_intent(
        intent="search", scopes=["intent:search"], mode="enforce"
    )
    assert ok is True


def test_opa_observe_allows_missing_scope():
    ok, reason = opa_allows_intent(intent="search", scopes=[], mode="observe")
    assert ok is True
    assert "observe-allow" in reason


def test_authorize_tool_enforce_mode(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_ENABLED", "true")
    monkeypatch.setenv("GOVERNOR_MODE", "enforce")
    with pytest.raises(McpAuthError):
        authorize_tool(
            "search",
            "search",
            _bearer({"preferred_username": "bob", "scope": "openid"}),
        )
    principal = authorize_tool(
        "search",
        "search",
        _bearer(
            {
                "preferred_username": "bob",
                "scope": "intent:search",
            }
        ),
    )
    assert principal.user_space == "bob"
