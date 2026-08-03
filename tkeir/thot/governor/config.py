"""Title: Config

Governor service configuration.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

GovernorMode = Literal["off", "observe", "enforce"]


@dataclass(frozen=True)
class GovernorSettings:
    """Runtime settings for governor API and enforcement hooks.

    Example:
        >>> from thot.governor.config import GovernorSettings
        >>> from pathlib import Path
        >>> s = GovernorSettings(
        ...     mode="observe", host="127.0.0.1", port=8094,
        ...     flags_path=Path("/tmp/flags.json"),
        ...     budget_db_path=Path("/tmp/budgets.db"),
        ...     approvals_path=Path("/tmp/approvals.json"),
        ...     auth_enabled=False, dev_token=None,
        ...     default_doc_budget=10000.0, default_llm_token_budget=500000.0,
        ...     throttle_ratio=0.8,
        ... )
        >>> s.mode
        'observe'
    """

    mode: GovernorMode
    host: str
    port: int
    flags_path: Path
    budget_db_path: Path
    approvals_path: Path
    auth_enabled: bool
    dev_token: str | None
    default_doc_budget: float
    default_llm_token_budget: float
    throttle_ratio: float


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean environment variable.

    Args:
        name: Environment variable name.
        default: Value when unset.

    Returns:
        Parsed boolean.

    Example:
        >>> import os
        >>> from thot.governor.config import _env_bool
        >>> _ = os.environ.pop("GOV_TEST_BOOL", None)
        >>> _env_bool("GOV_TEST_BOOL", True)
        True
        >>> os.environ["GOV_TEST_BOOL"] = "yes"
        >>> _env_bool("GOV_TEST_BOOL", False)
        True
        >>> del os.environ["GOV_TEST_BOOL"]
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_mode() -> GovernorMode:
    """Read ``GOVERNOR_MODE`` (default ``observe``).

    Returns:
        Governor enforcement mode.

    Example:
        >>> import os
        >>> from thot.governor.config import _env_mode
        >>> _ = os.environ.pop("GOVERNOR_MODE", None)
        >>> _env_mode()
        'observe'
        >>> os.environ["GOVERNOR_MODE"] = "enforce"
        >>> _env_mode()
        'enforce'
        >>> del os.environ["GOVERNOR_MODE"]
    """
    raw = os.getenv("GOVERNOR_MODE", os.getenv("governor.mode", "observe"))
    mode = raw.strip().lower()
    if mode in {"off", "observe", "enforce"}:
        return mode  # type: ignore[return-value]
    return "observe"


@lru_cache(maxsize=1)
def governor_settings() -> GovernorSettings:
    """Load governor settings once per process.

    Returns:
        Cached ``GovernorSettings`` instance.

    Example:
        >>> from thot.governor.config import governor_settings
        >>> governor_settings.cache_clear()
        >>> s = governor_settings()
        >>> s.port > 0 and s.mode in {"off", "observe", "enforce"}
        True
    """
    root = Path(os.getenv("GOVERNOR_STATE_ROOT", "/var/tkeir/governor"))
    return GovernorSettings(
        mode=_env_mode(),
        host=os.getenv("GOVERNOR_HOST", "0.0.0.0"),
        port=int(os.getenv("GOVERNOR_PORT", "8094")),
        flags_path=Path(os.getenv("GOVERNOR_FLAGS_PATH", root / "flags.json")),
        budget_db_path=Path(
            os.getenv("GOVERNOR_BUDGET_DB", root / "budgets.db")
        ),
        approvals_path=Path(
            os.getenv("GOVERNOR_APPROVALS_PATH", root / "approvals.json")
        ),
        auth_enabled=_env_bool("GOVERNOR_AUTH_ENABLED", False),
        dev_token=os.getenv("GOVERNOR_DEV_TOKEN") or None,
        default_doc_budget=float(
            os.getenv("GOVERNOR_DEFAULT_DOC_BUDGET", "10000")
        ),
        default_llm_token_budget=float(
            os.getenv("GOVERNOR_DEFAULT_LLM_TOKEN_BUDGET", "500000")
        ),
        throttle_ratio=float(os.getenv("GOVERNOR_THROTTLE_RATIO", "0.8")),
    )
