"""Title: Wiring

Shared wiring helpers for governor middleware.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from starlette.applications import Starlette

from thot.governor.config import governor_settings


def wire_governor_middleware(
    app: Starlette, *, service: str | None = None
) -> None:
    """Register governor enforcement when mode is not ``off``.

    Args:
        app: Starlette/FastAPI application.
        service: Optional service name override.

    Example:
        >>> from starlette.applications import Starlette
        >>> from thot.governor.wiring import wire_governor_middleware
        >>> app = Starlette()
        >>> wire_governor_middleware(app, service="demo")
    """
    if governor_settings().mode == "off":
        return
    from thot.governor.middleware import GovernorEnforceMiddleware

    app.add_middleware(GovernorEnforceMiddleware, service=service)
