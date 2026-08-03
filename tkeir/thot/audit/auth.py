"""Title: Auth

Authorization for audit read APIs.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import Header, HTTPException

from thot.audit.config import audit_settings

AUDIT_SCOPE = "intent:audit.read"


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode JWT payload segment without signature verification.

    Example:
        >>> import base64, json
        >>> from thot.audit.auth import _decode_jwt_payload
        >>> payload = {"sub": "u1", "scope": "intent:audit.read"}
        >>> body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        >>> _decode_jwt_payload(f"hdr.{body}.sig")["sub"]
        'u1'
    """
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


def _token_has_audit_scope(payload: dict[str, Any]) -> bool:
    """Return True when payload carries audit read scope.

    Example:
        >>> from thot.audit.auth import _token_has_audit_scope
        >>> _token_has_audit_scope({"scope": "intent:audit.read"})
        True
    """
    scope = payload.get("scope")
    if isinstance(scope, str) and AUDIT_SCOPE in scope.split():
        return True
    scopes = payload.get("scp")
    if isinstance(scopes, list) and AUDIT_SCOPE in scopes:
        return True
    resource_access = payload.get("resource_access")
    if isinstance(resource_access, dict):
        for client in resource_access.values():
            if not isinstance(client, dict):
                continue
            roles = client.get("roles")
            if isinstance(roles, list) and "auditor" in roles:
                return True
    return False


def verify_audit_authorization(authorization: str | None) -> str:
    """Validate bearer token for audit read operations.

    Example:
        >>> from thot.audit.config import audit_settings
        >>> from thot.audit.auth import verify_audit_authorization
        >>> audit_settings.cache_clear()
        >>> verify_audit_authorization(None)
        'anonymous'
    """
    settings = audit_settings()
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
    if not _token_has_audit_scope(payload):
        raise HTTPException(
            status_code=403,
            detail=f"Missing required scope {AUDIT_SCOPE}",
        )
    sub = payload.get("sub")
    return str(sub) if sub else "authenticated"


async def require_audit_auth(
    authorization: str | None = Header(default=None),
) -> str:
    """FastAPI dependency for audit endpoints.

    Example:
        >>> import inspect
        >>> from thot.audit.auth import require_audit_auth
        >>> inspect.iscoroutinefunction(require_audit_auth)
        True
    """
    return verify_audit_authorization(authorization)
