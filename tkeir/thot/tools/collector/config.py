"""Title: Collector service configuration.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from thot.tools.ingest.user_workspace import workspace_root


@dataclass(frozen=True)
class CollectorSettings:
    """Runtime settings for ``tkeir-collector``.

    Example:
        >>> from thot.tools.collector.config import CollectorSettings, collector_settings
        >>> isinstance(collector_settings(), CollectorSettings)
        True
    """

    host: str
    port: int
    searxng_url: str
    workspace: Path
    max_results: int
    fetch_timeout_s: float
    user_agent: str
    simhash_max_hamming: int
    batch_concurrency: int


def collector_settings() -> CollectorSettings:
    """Load collector settings from the environment.

    Returns:
        Immutable :class:`CollectorSettings`.

    Example:
        >>> from thot.tools.collector.config import collector_settings
        >>> s = collector_settings()
        >>> s.port > 0
        True
    """
    return CollectorSettings(
        host=os.getenv("COLLECTOR_HOST", "0.0.0.0"),
        port=int(os.getenv("COLLECTOR_PORT", "8096")),
        searxng_url=os.getenv("SEARXNG_URL", "http://127.0.0.1:8888").rstrip(
            "/"
        ),
        workspace=workspace_root(),
        max_results=max(1, int(os.getenv("COLLECTOR_MAX_RESULTS", "5"))),
        fetch_timeout_s=float(os.getenv("COLLECTOR_FETCH_TIMEOUT_S", "30")),
        user_agent=os.getenv(
            "COLLECTOR_USER_AGENT",
            "tkeir-collector/2.0 (+https://github.com/ThalesGroup/t-keir)",
        ),
        simhash_max_hamming=max(
            0, int(os.getenv("COLLECTOR_SIMHASH_MAX_HAMMING", "3"))
        ),
        batch_concurrency=max(
            1, int(os.getenv("COLLECTOR_BATCH_CONCURRENCY", "4"))
        ),
    )


def searxng_workspace_dirs(root: Path | None = None) -> tuple[Path, Path]:
    """Return ``(config_dir, data_dir)`` under the workspace for SearXNG volumes.

    Example:
        >>> from pathlib import Path
        >>> from thot.tools.collector.config import searxng_workspace_dirs
        >>> cfg, data = searxng_workspace_dirs(Path("/tmp/ws"))
        >>> cfg.as_posix().endswith("searxng/config")
        True
        >>> data.as_posix().endswith("searxng/data")
        True
    """
    base = Path(root) if root is not None else workspace_root()
    return base / "searxng" / "config", base / "searxng" / "data"


def bundled_searxng_settings() -> Path:
    """Path to the tracked SearXNG settings under ``tkeir/resources/searxng/``.

    Example:
        >>> from thot.tools.collector.config import bundled_searxng_settings
        >>> bundled_searxng_settings().name
        'settings.yml'
        >>> 'resources' in bundled_searxng_settings().as_posix()
        True
    """
    from thot.core.TkeirPaths import package_root

    return Path(package_root()) / "resources" / "searxng" / "settings.yml"
