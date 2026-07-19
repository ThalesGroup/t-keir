"""Governor action tokens — constrained JWT-like tokens with revocation."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


@dataclass(frozen=True)
class ActionToken:
    """Constrained action token (HMAC-signed, TTL ≤ 300s by default)."""

    jti: str
    actor_id: str
    intent: str
    audience: str
    max_budget: float
    expires_at: int
    issued_at: int
    constraints: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        """Serialize token claims for signing.

        Example:
            >>> token = ActionToken(
            ...     jti="j1", actor_id="u1", intent="search", audience="tkeir-action",
            ...     max_budget=1.0, expires_at=100, issued_at=1, constraints={},
            ... )
            >>> token.to_payload()["sub"]
            'u1'
        """
        return {
            "jti": self.jti,
            "sub": self.actor_id,
            "intent": self.intent,
            "aud": self.audience,
            "max_budget": self.max_budget,
            "exp": self.expires_at,
            "iat": self.issued_at,
            "constraints": self.constraints,
        }


class ActionTokenService:
    """Mint and verify action tokens; maintain a local revocation list."""

    def __init__(
        self,
        *,
        secret: bytes | None = None,
        revoke_path: Path | None = None,
        default_ttl: int = 300,
    ) -> None:
        self._secret = secret or os.getenv(
            "GOVERNOR_TOKEN_SECRET",
            "dev-governor-token-secret-change-me",
        ).encode("utf-8")
        self._ttl = max(1, min(default_ttl, 300))
        self._path = revoke_path or Path(
            os.getenv(
                "GOVERNOR_REVOKE_PATH", "/var/tkeir/governor/revoked.json"
            )
        )
        self._lock = threading.Lock()
        self._revoked: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._revoked = set(data.get("jtis", []))
        except (OSError, ValueError, TypeError):
            self._revoked = set()

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "jtis": sorted(self._revoked),
            "updated_at": int(time.time()),
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self._path)

    def mint(
        self,
        *,
        actor_id: str,
        intent: str,
        audience: str = "tkeir-action",
        max_budget: float = 0.0,
        constraints: dict[str, Any] | None = None,
        ttl: int | None = None,
        jti: str | None = None,
    ) -> tuple[str, ActionToken]:
        """Mint a constrained action token (HMAC-signed, TTL capped at 300s).

        Args:
            actor_id: Subject / service identity.
            intent: Declared intent (e.g. ``search``).
            audience: Token audience claim.
            max_budget: Optional budget ceiling encoded in the token.
            constraints: Extra opaque constraints.
            ttl: Lifetime in seconds (clamped to 1..300).
            jti: Optional fixed token id (tests).

        Returns:
            Tuple of compact ``body.sig`` string and ActionToken.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.tokens import ActionTokenService
            >>> with tempfile.TemporaryDirectory() as td:
            ...     svc = ActionTokenService(
            ...         secret=b"doctest-secret",
            ...         revoke_path=Path(td) / "revoked.json",
            ...     )
            ...     compact, token = svc.mint(
            ...         actor_id="demo", intent="search", ttl=60, jti="fixed-jti"
            ...     )
            ...     verified = svc.verify(compact)
            ...     verified.jti == "fixed-jti" and verified.intent == "search"
            True
        """
        now = int(time.time())
        ttl_s = self._ttl if ttl is None else max(1, min(ttl, 300))
        token_jti = jti or _b64url(os.urandom(16))
        token = ActionToken(
            jti=token_jti,
            actor_id=actor_id,
            intent=intent,
            audience=audience,
            max_budget=max_budget,
            expires_at=now + ttl_s,
            issued_at=now,
            constraints=constraints or {},
        )
        body = _b64url(
            json.dumps(
                token.to_payload(), separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
        )
        sig = _b64url(
            hmac.new(
                self._secret, body.encode("ascii"), hashlib.sha256
            ).digest()
        )
        return f"{body}.{sig}", token

    def verify(self, compact: str) -> ActionToken:
        """Verify signature, expiry, and revocation.

        Args:
            compact: Token string ``body.signature``.

        Returns:
            Parsed ActionToken when valid.

        Raises:
            ValueError: On malformed, bad signature, revoked, or expired tokens.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.tokens import ActionTokenService
            >>> with tempfile.TemporaryDirectory() as td:
            ...     svc = ActionTokenService(
            ...         secret=b"doctest-secret",
            ...         revoke_path=Path(td) / "revoked.json",
            ...     )
            ...     compact, _ = svc.mint(actor_id="demo", intent="search", jti="v1")
            ...     svc.verify(compact).actor_id
            'demo'
        """
        try:
            body, sig = compact.split(".", 1)
        except ValueError as exc:
            raise ValueError("malformed action token") from exc
        expect = _b64url(
            hmac.new(
                self._secret, body.encode("ascii"), hashlib.sha256
            ).digest()
        )
        if not hmac.compare_digest(expect, sig):
            raise ValueError("invalid action token signature")
        payload = json.loads(_b64url_decode(body))
        jti = str(payload.get("jti") or "")
        with self._lock:
            if jti in self._revoked:
                raise ValueError("action token revoked")
        exp = int(payload.get("exp") or 0)
        if exp < int(time.time()):
            raise ValueError("action token expired")
        return ActionToken(
            jti=jti,
            actor_id=str(payload.get("sub") or ""),
            intent=str(payload.get("intent") or ""),
            audience=str(payload.get("aud") or ""),
            max_budget=float(payload.get("max_budget") or 0),
            expires_at=exp,
            issued_at=int(payload.get("iat") or 0),
            constraints=dict(payload.get("constraints") or {}),
        )

    def revoke(
        self, *, jti: str | None = None, actor_id: str | None = None
    ) -> list[str]:
        """Revoke by jti and/or mark actor for future checks.

        Args:
            jti: Token id to revoke.
            actor_id: Optional actor sentinel ``actor:<id>``.

        Returns:
            List of revoked keys written to the revoke store.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.tokens import ActionTokenService
            >>> with tempfile.TemporaryDirectory() as td:
            ...     svc = ActionTokenService(
            ...         secret=b"doctest-secret",
            ...         revoke_path=Path(td) / "revoked.json",
            ...     )
            ...     compact, tok = svc.mint(actor_id="demo", intent="search", jti="r1")
            ...     revoked = svc.revoke(jti=tok.jti)
            ...     "r1" in revoked and svc.is_revoked("r1")
            True
        """
        revoked: list[str] = []
        with self._lock:
            if jti:
                self._revoked.add(jti)
                revoked.append(jti)
            self._persist()
        # actor-wide revocation is recorded as a sentinel key for auditors
        if actor_id:
            sentinel = f"actor:{actor_id}"
            with self._lock:
                self._revoked.add(sentinel)
                revoked.append(sentinel)
                self._persist()
        return revoked

    def is_revoked(self, jti: str) -> bool:
        """Return True when ``jti`` is on the local revoke list."""
        with self._lock:
            return jti in self._revoked
