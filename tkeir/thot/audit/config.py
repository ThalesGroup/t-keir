"""Audit service configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class AuditSettings:
    """Runtime settings for audit API, archiver, and sinks."""

    hot_store_url: str | None
    worm_root: Path
    subject_keys_path: Path
    host: str
    port: int
    auth_enabled: bool
    dev_token: str | None
    sink_mode: str


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def audit_settings() -> AuditSettings:
    """Load audit settings once per process."""
    worm_root = Path(os.getenv("AUDIT_WORM_ROOT", "/var/tkeir/audit/worm"))
    keys_path = Path(
        os.getenv(
            "AUDIT_SUBJECT_KEYS_PATH", "/var/tkeir/audit/subject_keys.db"
        )
    )
    hot_url = os.getenv("AUDIT_HOT_STORE_URL") or None
    sink_mode = os.getenv("AUDIT_SINK_MODE", "dual" if hot_url else "memory")
    return AuditSettings(
        hot_store_url=hot_url,
        worm_root=worm_root,
        subject_keys_path=keys_path,
        host=os.getenv("AUDIT_HOST", "0.0.0.0"),
        port=int(os.getenv("AUDIT_PORT", "8093")),
        auth_enabled=_env_bool("AUDIT_AUTH_ENABLED", False),
        dev_token=os.getenv("AUDIT_DEV_TOKEN") or None,
        sink_mode=sink_mode,
    )
