"""Shared wiring helpers for governor middleware."""

from __future__ import annotations

from starlette.applications import Starlette

from thot.governor.config import governor_settings


def wire_governor_middleware(
    app: Starlette, *, service: str | None = None
) -> None:
    """Register governor enforcement when mode is not ``off``."""
    if governor_settings().mode == "off":
        return
    from thot.governor.middleware import GovernorEnforceMiddleware

    app.add_middleware(GovernorEnforceMiddleware, service=service)
