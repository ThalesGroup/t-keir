"""Title: Auth

Authorization for governor admin APIs.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import Header, HTTPException

from thot.governor.config import governor_settings

ADMIN_SCOPE = "intent:admin.override"


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("invalid jwt")
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    raw = base64.urlsafe_b64decode(payload + padding)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("invalid jwt payload")
    return data


def _token_has_admin_scope(payload: dict[str, Any]) -> bool:
    scope = payload.get("scope")
    if isinstance(scope, str) and ADMIN_SCOPE in scope.split():
        return True
    scopes = payload.get("scp")
    if isinstance(scopes, list) and ADMIN_SCOPE in scopes:
        return True
    resource_access = payload.get("resource_access")
    if isinstance(resource_access, dict):
        for client in resource_access.values():
            if not isinstance(client, dict):
                continue
            roles = client.get("roles")
            if isinstance(roles, list) and "tkeir-admin" in roles:
                return True
    return False


def extract_bearer_payload(authorization: str | None) -> dict[str, Any] | None:
    """Return decoded JWT payload when a bearer token is present."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    settings = governor_settings()
    if settings.dev_token and token == settings.dev_token:
        return {"sub": "dev-token", "scope": ADMIN_SCOPE}
    try:
        return _decode_jwt_payload(token)
    except (ValueError, json.JSONDecodeError):
        return None


def verify_admin_authorization(authorization: str | None) -> str:
    """Validate bearer token for governor admin operations."""
    settings = governor_settings()
    if not settings.auth_enabled:
        return "anonymous"
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if settings.dev_token and token == settings.dev_token:
        return "dev-token"
    try:
        payload = _decode_jwt_payload(token)
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    if not _token_has_admin_scope(payload):
        raise HTTPException(
            status_code=403,
            detail=f"Missing required scope {ADMIN_SCOPE}",
        )
    sub = payload.get("sub")
    return str(sub) if sub else "authenticated"


async def require_admin_auth(
    authorization: str | None = Header(default=None),
) -> str:
    """FastAPI dependency for governor admin endpoints."""
    return verify_admin_authorization(authorization)
