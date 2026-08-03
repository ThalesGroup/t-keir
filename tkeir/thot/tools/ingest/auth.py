"""Title: Auth

Authorization helpers for ingest endpoints.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import Header, HTTPException

from thot.tools.ingest.config import ingest_settings
from thot.tools.search.user_space import (
    DEV_USER_SPACE,
    resolve_vespa_user_space,
    user_space_from_claims,
)

INGEST_SCOPE = "intent:ingest"
ADMIN_ROLES = frozenset({"c2-admin", "tkeir-admin"})
VALID_INDEX_TARGETS = frozenset({"global", "user", "both"})


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode the payload segment of a JWT without signature verification.

    Example:
        >>> import base64, json
        >>> payload = {"sub": "user1", "scope": "intent:ingest"}
        >>> raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        >>> _decode_jwt_payload(f"hdr.{raw}.sig")["sub"]
        'user1'
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


def _token_has_ingest_scope(payload: dict[str, Any]) -> bool:
    """Return True when the JWT payload grants ingest scope.

    Example:
        >>> _token_has_ingest_scope({"scope": "openid intent:ingest"})
        True
    """
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


def _roles_from_payload(payload: dict[str, Any]) -> frozenset[str]:
    """Extract realm and client roles from a JWT payload.

    Example:
        >>> _roles_from_payload({"realm_access": {"roles": ["c2-admin"]}})
        frozenset({'c2-admin'})
    """
    roles: set[str] = set()
    realm = payload.get("realm_access")
    if isinstance(realm, dict):
        raw = realm.get("roles")
        if isinstance(raw, list):
            roles.update(str(r) for r in raw if r)
    # Mis-nested Keycloak claim sometimes seen as a literal key.
    dotted = payload.get("realm_access.roles")
    if isinstance(dotted, list):
        roles.update(str(r) for r in dotted if r)
    resource_access = payload.get("resource_access")
    if isinstance(resource_access, dict):
        for client in resource_access.values():
            if not isinstance(client, dict):
                continue
            raw = client.get("roles")
            if isinstance(raw, list):
                roles.update(str(r) for r in raw if r)
    return frozenset(roles)


def roles_from_authorization(authorization: str | None) -> frozenset[str]:
    """Extract realm/client roles from a Bearer access token (empty if none).

    Example:
        >>> from thot.tools.ingest.auth import roles_from_authorization
        >>> roles_from_authorization(None)
        frozenset()
    """
    if not authorization or not authorization.startswith("Bearer "):
        return frozenset()
    token = authorization.removeprefix("Bearer ").strip()
    settings = ingest_settings()
    if settings.dev_token and token == settings.dev_token:
        return frozenset(ADMIN_ROLES)
    try:
        payload = _decode_jwt_payload(token)
    except (ValueError, json.JSONDecodeError):
        return frozenset()
    return _roles_from_payload(payload)


def is_ingest_admin(authorization: str | None) -> bool:
    """True when the caller has an admin ingest role (or auth is disabled).

    When ``INGEST_AUTH_ENABLED`` is false (local demos), global corpus tools
    remain usable; personal ``/workspace/*`` endpoints still force ``user``.
    

    Example:
        >>> from thot.tools.ingest.auth import is_ingest_admin
        >>> is_ingest_admin(None)
        True
    """
    settings = ingest_settings()
    if not settings.auth_enabled:
        return True
    return bool(ADMIN_ROLES & roles_from_authorization(authorization))


def resolve_allowed_index_target(
    requested: str | None,
    *,
    authorization: str | None,
    default: str = "user",
    admin_default: str = "global",
    require_admin_for_global: bool = True,
) -> str:
    """Resolve ``index_target`` under the personal-vs-global policy.

    - Non-admin (auth on): forced to ``user``; ``global``/``both`` → 403.
    - Admin (or auth off): may choose ``global`` / ``user`` / ``both``.
    - ``require_admin_for_global``: when True and auth on, non-admins may not
      select a shared index (used by ``/ingest/json-records``).
    

    Example:
        >>> from thot.tools.ingest.auth import resolve_allowed_index_target
        >>> resolve_allowed_index_target("user", authorization=None)
        'user'
    """
    raw = (requested or "").strip().lower() or None
    admin = is_ingest_admin(authorization)
    settings = ingest_settings()

    if settings.auth_enabled and require_admin_for_global and not admin:
        if raw in {"global", "both"}:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Non-admin principals may only ingest into their personal "
                    "Vespa user streaming index (index_target=user)"
                ),
            )
        target = "user"
    elif admin:
        target = raw or admin_default
    else:
        target = raw or default

    if target not in VALID_INDEX_TARGETS:
        raise HTTPException(
            status_code=400,
            detail="index_target must be global|user|both",
        )
    if settings.auth_enabled and not admin and target != "user":
        raise HTTPException(
            status_code=403,
            detail=(
                "Non-admin principals may only ingest into their personal "
                "Vespa user streaming index (index_target=user)"
            ),
        )
    return target


def require_admin_ingest(
    authorization: str | None = Header(default=None),
) -> str:
    """Require an admin role for global corpus ingest endpoints.

    Example:
        >>> from thot.tools.ingest.auth import require_admin_ingest
        >>> callable(require_admin_ingest)
        True
    """
    actor = verify_ingest_authorization(authorization)
    if not is_ingest_admin(authorization):
        raise HTTPException(
            status_code=403,
            detail="Admin role (c2-admin or tkeir-admin) required",
        )
    return actor


def verify_ingest_authorization(authorization: str | None) -> str:
    """Validate bearer token or return the Keycloak / dev user-space.

    When auth is disabled, returns ``dev@tkeir`` (or ``VESPA_USER_SPACE``).
    When a Keycloak access token is presented, returns preferred_username,
    email, or ``sub`` for Vespa streaming isolation.

    Returns:
        Actor / Vespa user-space string when authorized.

    Example:
        >>> from thot.tools.ingest.auth import verify_ingest_authorization
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
