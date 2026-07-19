"""Governor service configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

GovernorMode = Literal["off", "observe", "enforce"]


@dataclass(frozen=True)
class GovernorSettings:
    """Runtime settings for governor API and enforcement hooks."""

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
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_mode() -> GovernorMode:
    raw = os.getenv("GOVERNOR_MODE", os.getenv("governor.mode", "observe"))
    mode = raw.strip().lower()
    if mode in {"off", "observe", "enforce"}:
        return mode  # type: ignore[return-value]
    return "observe"


@lru_cache(maxsize=1)
def governor_settings() -> GovernorSettings:
    """Load governor settings once per process."""
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
