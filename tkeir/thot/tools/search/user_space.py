"""Resolve Vespa streaming user-space from Keycloak identity.

In production, each authenticated principal gets an isolated Vespa group
(``streaming.groupname`` / ``g=<user_space>``). When auth is off (P0 / local
dev), the fixed principal ``dev@tkeir`` is used.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

DEV_USER_SPACE = "dev@tkeir"


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode a JWT payload without verifying the signature.

    Example:
        >>> import base64, json
        >>> body = base64.urlsafe_b64encode(
        ...     json.dumps({"preferred_username": "alice"}).encode()
        ... ).decode().rstrip("=")
        >>> decode_jwt_payload(f"h.{body}.s")["preferred_username"]
        'alice'
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


def user_space_from_claims(payload: dict[str, Any]) -> str | None:
    """Pick a stable user-space from Keycloak / OIDC claims.

    Preference: ``preferred_username`` → ``email`` → ``sub``.

    Example:
        >>> user_space_from_claims({"preferred_username": "demo-user"})
        'demo-user'
        >>> user_space_from_claims({"email": "alice@tkeir"})
        'alice@tkeir'
        >>> user_space_from_claims({}) is None
        True
    """
    for key in ("preferred_username", "email", "sub"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_vespa_user_space(
    authorization: str | None = None,
    *,
    fallback: str | None = None,
) -> str:
    """Resolve streaming group from Bearer JWT, else env / ``dev@tkeir``.

    Args:
        authorization: Optional ``Authorization`` header value.
        fallback: Explicit override (e.g. job-stored space).

    Returns:
        Normalized user-space string safe for Vespa group ids.

    Example:
        >>> resolve_vespa_user_space(None, fallback="dev@tkeir")
        'dev@tkeir'
        >>> import base64, json
        >>> body = base64.urlsafe_b64encode(
        ...     json.dumps({"preferred_username": "demo-user"}).encode()
        ... ).decode().rstrip("=")
        >>> resolve_vespa_user_space(f"Bearer x.{body}.y")
        'demo-user'
    """
    from thot.tools.search.vespa_client import normalize_user_space

    if fallback is not None and str(fallback).strip():
        return normalize_user_space(str(fallback).strip())

    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if token:
            try:
                claims = decode_jwt_payload(token)
            except (ValueError, json.JSONDecodeError):
                claims = {}
            from_claims = user_space_from_claims(claims)
            if from_claims:
                return normalize_user_space(from_claims)

    env = (os.getenv("VESPA_USER_SPACE") or "").strip()
    if env:
        return normalize_user_space(env)
    return normalize_user_space(DEV_USER_SPACE)
