"""Title: Config

Audit service configuration.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class AuditSettings:
    """Runtime settings for audit API, archiver, and sinks.

    Example:
        >>> from pathlib import Path
        >>> from thot.audit.config import AuditSettings
        >>> s = AuditSettings(
        ...     hot_store_url="sqlite:///tmp/hot.db",
        ...     worm_root=Path("/tmp/worm"),
        ...     subject_keys_path=Path("/tmp/keys.db"),
        ...     host="127.0.0.1", port=8093,
        ...     auth_enabled=False, dev_token=None, sink_mode="dual",
        ... )
        >>> s.port
        8093
    """

    hot_store_url: str | None
    worm_root: Path
    subject_keys_path: Path
    host: str
    port: int
    auth_enabled: bool
    dev_token: str | None
    sink_mode: str


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean environment variable.

    Example:
        >>> import os
        >>> from thot.audit.config import _env_bool
        >>> _ = os.environ.pop("AUDIT_TEST_BOOL", None)
        >>> _env_bool("AUDIT_TEST_BOOL", False)
        False
        >>> os.environ["AUDIT_TEST_BOOL"] = "on"
        >>> _env_bool("AUDIT_TEST_BOOL", False)
        True
        >>> del os.environ["AUDIT_TEST_BOOL"]
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def audit_settings() -> AuditSettings:
    """Load audit settings once per process.

    Returns:
        Cached ``AuditSettings`` instance.

    Example:
        >>> from thot.audit.config import audit_settings
        >>> audit_settings.cache_clear()
        >>> s = audit_settings()
        >>> s.port > 0
        True
    """
    from thot.core.TkeirPaths import repo_root

    workspace_env = os.getenv("TKEIR_WORKSPACE") or os.getenv("WORKSPACE")
    host_root = (
        Path(workspace_env).expanduser().resolve() / "audit"
        if workspace_env
        else Path(repo_root()) / "workspace" / "audit"
    )
    # Containers / production set AUDIT_* explicitly (see Dockerfile.tkeir-audit).
    # Host Make defaults to workspace/audit — avoid requiring /var/tkeir.
    worm_root = Path(os.getenv("AUDIT_WORM_ROOT", str(host_root / "worm")))
    keys_path = Path(
        os.getenv(
            "AUDIT_SUBJECT_KEYS_PATH",
            str(host_root / "subject_keys.db"),
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
