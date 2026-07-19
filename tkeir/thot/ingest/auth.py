"""Authorization helpers for ingest endpoints."""

from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import Header, HTTPException

from thot.ingest.config import ingest_settings
from thot.tools.search.user_space import (
    DEV_USER_SPACE,
    resolve_vespa_user_space,
    user_space_from_claims,
)

INGEST_SCOPE = "intent:ingest"


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


def _token_has_ingest_scope(payload: dict[str, Any]) -> bool:
    scope = payload.get("scope")
    if isinstance(scope, str) and INGEST_SCOPE in scope.split():
        return True
    scopes = payload.get("scp")
    if isinstance(scopes, list) and INGEST_SCOPE in scopes:
        return True
    resource_access = payload.get("resource_access")
    if isinstance(resource_access, dict):
        for client in resource_access.values():
            if not isinstance(client, dict):
                continue
            roles = client.get("roles")
            if isinstance(roles, list) and "ingest" in roles:
                return True
    return False


def verify_ingest_authorization(authorization: str | None) -> str:
    """Validate bearer token or return the Keycloak / dev user-space.

    When auth is disabled, returns ``dev@tkeir`` (or ``VESPA_USER_SPACE``).
    When a Keycloak access token is presented, returns preferred_username,
    email, or ``sub`` for Vespa streaming isolation.

    Returns:
        Actor / Vespa user-space string when authorized.

    Example:
        >>> from thot.ingest.auth import verify_ingest_authorization
        >>> verify_ingest_authorization(None)  # auth disabled by default
        'dev@tkeir'
    """
    settings = ingest_settings()
    if not settings.auth_enabled:
        return resolve_vespa_user_space(authorization)

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    if settings.dev_token and token == settings.dev_token:
        return DEV_USER_SPACE

    try:
        payload = _decode_jwt_payload(token)
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    if not _token_has_ingest_scope(payload):
        raise HTTPException(
            status_code=403,
            detail=f"Missing required scope {INGEST_SCOPE}",
        )
    space = user_space_from_claims(payload)
    if space:
        return space
    sub = payload.get("sub")
    return str(sub) if sub else "authenticated"


async def require_ingest_auth(
    authorization: str | None = Header(default=None),
) -> str:
    """FastAPI dependency wrapping :func:`verify_ingest_authorization`.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(require_ingest_auth)
        True
    """
    return verify_ingest_authorization(authorization)
