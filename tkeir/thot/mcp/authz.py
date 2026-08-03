"""Title: MCP authorization: Bearer → user_space + intent/scope + OPA-style gate.

Phase A maps every read tool to ``intent:search``. ``user_space`` is never
taken from tool arguments — only from the authenticated principal.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from thot.tools.search.user_space import (
    DEV_USER_SPACE,
    decode_jwt_payload,
    resolve_vespa_user_space,
    user_space_from_claims,
)

SEARCH_SCOPE = "intent:search"


@dataclass
class McpPrincipal:
    """Authenticated caller for one MCP tool invocation."""

    user_space: str
    scopes: list[str] = field(default_factory=list)
    subject: str = "anonymous"
    auth_enabled: bool = False
    raw_authorization: str | None = None


class McpAuthError(PermissionError):
    """Raised when MCP authz denies a call."""

    def __init__(self, message: str, *, status_code: int = 403) -> None:
        """Create an authz error with HTTP status metadata.

        Example:
            >>> from thot.mcp.authz import McpAuthError
            >>> err = McpAuthError("denied", status_code=401)
            >>> err.status_code
            401
        """
        super().__init__(message)
        self.status_code = status_code


def _auth_enabled() -> bool:
    """Return whether MCP bearer auth is enabled via ``MCP_AUTH_ENABLED``.

    Example:
        >>> from thot.mcp.authz import _auth_enabled
        >>> isinstance(_auth_enabled(), bool)
        True
    """
    return os.getenv("MCP_AUTH_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _governor_mode() -> str:
    """Return OPA governor mode from ``GOVERNOR_MODE`` / ``MCP_GOVERNOR_MODE``.

    Example:
        >>> from thot.mcp.authz import _governor_mode
        >>> isinstance(_governor_mode(), str)
        True
    """
    return (
        os.getenv("GOVERNOR_MODE")
        or os.getenv("MCP_GOVERNOR_MODE")
        or "observe"
    ).lower()


def _scopes_from_payload(payload: dict[str, Any]) -> list[str]:
    """Extract OAuth scopes / roles from a decoded JWT payload.

    Example:
        >>> from thot.mcp.authz import _scopes_from_payload, SEARCH_SCOPE
        >>> _scopes_from_payload({"scope": "openid intent:search"})
        ['openid', 'intent:search']
        >>> SEARCH_SCOPE in _scopes_from_payload({
        ...     "resource_access": {"client": {"roles": ["search"]}},
        ... })
        True
    """
    scopes: list[str] = []
    raw = payload.get("scope")
    if isinstance(raw, str):
        scopes.extend(raw.split())
    scp = payload.get("scp")
    if isinstance(scp, list):
        scopes.extend(str(item) for item in scp)
    resource_access = payload.get("resource_access")
    if isinstance(resource_access, dict):
        for client in resource_access.values():
            if not isinstance(client, dict):
                continue
            roles = client.get("roles")
            if isinstance(roles, list) and "search" in roles:
                scopes.append(SEARCH_SCOPE)
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for scope in scopes:
        if scope not in seen:
            seen.add(scope)
            out.append(scope)
    return out


def resolve_principal(authorization: str | None = None) -> McpPrincipal:
    """Resolve the MCP caller from an optional Bearer token.

    When auth is disabled, returns ``dev@tkeir`` (or ``VESPA_USER_SPACE``).

    Example:
        >>> from thot.mcp.authz import resolve_principal
        >>> resolve_principal(None).user_space
        'dev@tkeir'
    """
    enabled = _auth_enabled()
    if not enabled:
        space = resolve_vespa_user_space(authorization)
        return McpPrincipal(
            user_space=space,
            scopes=[SEARCH_SCOPE],
            subject=space,
            auth_enabled=False,
            raw_authorization=authorization,
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise McpAuthError("Missing bearer token", status_code=401)

    token = authorization.removeprefix("Bearer ").strip()
    dev_token = (os.getenv("MCP_DEV_TOKEN") or "").strip()
    if dev_token and token == dev_token:
        return McpPrincipal(
            user_space=DEV_USER_SPACE,
            scopes=[SEARCH_SCOPE, "intent:admin.override"],
            subject=DEV_USER_SPACE,
            auth_enabled=True,
            raw_authorization=authorization,
        )

    try:
        payload = decode_jwt_payload(token)
    except (ValueError, Exception) as exc:
        raise McpAuthError("Invalid bearer token", status_code=401) from exc

    scopes = _scopes_from_payload(payload)
    space = user_space_from_claims(payload) or str(payload.get("sub") or "")
    if not space:
        raise McpAuthError(
            "Token missing preferred_username/email/sub", status_code=401
        )
    return McpPrincipal(
        user_space=resolve_vespa_user_space(None, fallback=space),
        scopes=scopes,
        subject=str(payload.get("sub") or space),
        auth_enabled=True,
        raw_authorization=authorization,
    )


def opa_allows_intent(
    *,
    intent: str,
    scopes: list[str],
    mode: str | None = None,
) -> tuple[bool, str]:
    """In-process intent↔scope check mirroring ``tkeir.intents`` Rego.

    Observe mode: missing scope is recorded but allowed (fail-open).
    Enforce mode: missing scope denies (fail-closed).

    Example:
        >>> from thot.mcp.authz import opa_allows_intent
        >>> opa_allows_intent(intent="search", scopes=["intent:search"], mode="enforce")
        (True, 'allow')
        >>> allowed, reason = opa_allows_intent(
        ...     intent="search", scopes=[], mode="enforce"
        ... )
        >>> allowed
        False
    """
    active_mode = (mode or _governor_mode()).lower()
    required = {
        "search": SEARCH_SCOPE,
        "ingest": "intent:ingest",
        "index": "intent:index",
        "delete": "intent:delete",
        "audit.read": "intent:audit.read",
    }.get(intent, SEARCH_SCOPE)

    if "intent:admin.override" in scopes or required in scopes:
        return True, "allow"

    if active_mode == "enforce":
        return False, f"missing scope {required} for intent {intent}"
    return True, f"observe-allow-missing-scope:{required}"


def authorize_tool(
    tool_name: str,
    intent: str,
    authorization: str | None = None,
) -> McpPrincipal:
    """Resolve principal and enforce intent/scope for ``tool_name``.

    Example:
        >>> from thot.mcp.authz import authorize_tool
        >>> p = authorize_tool("search", "search", None)
        >>> p.user_space
        'dev@tkeir'
    """
    principal = resolve_principal(authorization)
    allowed, reason = opa_allows_intent(
        intent=intent, scopes=principal.scopes, mode=_governor_mode()
    )
    if not allowed:
        raise McpAuthError(
            f"OPA deny for tool {tool_name}: {reason}",
            status_code=403,
        )
    return principal


def strip_tenant_overrides(arguments: dict[str, Any]) -> dict[str, Any]:
    """Remove any client-supplied tenant fields from tool arguments.

    Example:
        >>> from thot.mcp.authz import strip_tenant_overrides
        >>> strip_tenant_overrides({"query": "x", "user_space": "evil"})
        {'query': 'x'}
    """
    blocked = {
        "user_space",
        "streaming.groupname",
        "group",
        "vespa_user_space",
        "authorization",
    }
    return {k: v for k, v in arguments.items() if k not in blocked}
