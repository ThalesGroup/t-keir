"""Title: Config

Ingest service settings from environment variables.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from thot.core.TkeirPaths import configs_dir


@dataclass(frozen=True)
class IngestSettings:
    """Runtime configuration for the ingest service and CLI."""

    root: Path
    workspace_root: Path
    auth_enabled: bool
    dev_token: str | None
    pipeline_config_path: Path
    index_enabled: bool
    host: str
    port: int
    # Cap concurrent NLP pipeline+index jobs (spaCy is memory-heavy; >1 often OOMs).
    max_concurrency: int
    # Exit the ingest process on the first failed job (fast debug loops).
    stop_on_failed: bool


def _env_bool(name: str, default: bool) -> bool:
    """Parse a truthy environment variable.

    Example:
        >>> _env_bool("MISSING_VAR_FOR_DOCTEST", True)
        True
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def ingest_settings() -> IngestSettings:
    """Load ingest settings once per process.

    Example:
        >>> from thot.tools.ingest.config import ingest_settings
        >>> settings = ingest_settings()
        >>> settings.port > 0
        True
    """
    from thot.core.TkeirPaths import repo_root

    default_pipeline = Path(configs_dir()) / "pipeline.yaml"
    pipeline_path = Path(
        os.getenv("INGEST_PIPELINE_CONFIG", str(default_pipeline))
    )
    root = Path(os.getenv("INGEST_ROOT", "/var/tkeir/ingest"))
    workspace_env = os.getenv("TKEIR_WORKSPACE") or os.getenv("WORKSPACE")
    workspace_root = (
        Path(workspace_env).expanduser()
        if workspace_env
        else Path(repo_root()) / "workspace"
    )
    max_concurrency = max(1, int(os.getenv("INGEST_MAX_CONCURRENCY", "1")))
    return IngestSettings(
        root=root,
        workspace_root=workspace_root.resolve(),
        auth_enabled=_env_bool("INGEST_AUTH_ENABLED", False),
        dev_token=os.getenv("INGEST_DEV_TOKEN") or None,
        pipeline_config_path=pipeline_path,
        index_enabled=_env_bool("INGEST_INDEX_ENABLED", True),
        host=os.getenv("INGEST_HOST", "0.0.0.0"),
        port=int(os.getenv("INGEST_PORT", "8091")),
        max_concurrency=max_concurrency,
        stop_on_failed=_env_bool("INGEST_STOP_ON_FAILED", False),
    )
