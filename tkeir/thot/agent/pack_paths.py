"""Title: Dataset pack path discovery for agents / workflows.

Shared search roots under ``datasets/<pack>/`` and ``packs/<pack>/``, with
``TKEIR_AGENT_USECASE`` (and aliases) preferred so colliding stems resolve to
the active usecase.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os
from pathlib import Path

from thot.agent.orchestrator_config import resolve_usecase
from thot.core.TkeirPaths import package_root, repo_root


def dataset_pack_subdir_dirs(subdir: str) -> list[Path]:
    """Return ``datasets/*/`` and ``packs/*/`` subdirs named ``subdir``.

    Preferred usecase pack (``resolve_usecase()``) is listed first so
    first-match loaders pick the active pack on name collisions
    (e.g. ``wiki_writer``, ``llm_wiki``).

    Args:
        subdir: ``agents`` or ``workflows``.

    Returns:
        Ordered unique directory paths that exist.

    Example:
        >>> from thot.agent.pack_paths import dataset_pack_subdir_dirs
        >>> dirs = dataset_pack_subdir_dirs("agents")
        >>> any(p.name == "agents" for p in dirs)
        True
    """
    selected = resolve_usecase()
    found: list[tuple[str, Path]] = []
    for base in (
        Path(repo_root()) / "datasets",
        Path(package_root()) / "packs",
    ):
        if not base.is_dir():
            continue
        for pack in sorted(base.iterdir()):
            if not pack.is_dir() or pack.name.startswith("."):
                continue
            candidate = pack / subdir
            if candidate.is_dir():
                found.append((pack.name, candidate))

    preferred: list[Path] = []
    others: list[Path] = []
    for name, path in found:
        if selected and name == selected:
            preferred.append(path)
        else:
            others.append(path)
    return preferred + others


def extra_config_dirs_from_env(env_key: str) -> list[Path]:
    """Parse ``os.pathsep``-separated directories from an environment variable.

    Example:
        >>> import os
        >>> from thot.agent.pack_paths import extra_config_dirs_from_env
        >>> os.environ["TKEIR_TEST_DIRS"] = "/tmp"
        >>> isinstance(extra_config_dirs_from_env("TKEIR_TEST_DIRS"), list)
        True
        >>> del os.environ["TKEIR_TEST_DIRS"]
    """
    extra = os.getenv(env_key, "").strip()
    if not extra:
        return []
    out: list[Path] = []
    for part in extra.split(os.pathsep):
        path = Path(part).expanduser()
        if path.is_dir():
            out.append(path)
    return out


def dedupe_paths(paths: list[Path]) -> list[Path]:
    """Preserve order while dropping duplicate resolved paths.

    Example:
        >>> from pathlib import Path
        >>> from thot.agent.pack_paths import dedupe_paths
        >>> len(dedupe_paths([Path("/tmp"), Path("/tmp")])) <= 2
        True
    """
    seen: set[Path] = set()
    unique: list[Path] = []
    for root in paths:
        key = root.resolve()
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique
