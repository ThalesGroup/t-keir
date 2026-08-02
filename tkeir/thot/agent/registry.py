"""Title: Registry

Load and validate agent YAML specs from ``tkeir/configs/agents/`` and
dataset packs (``datasets/<pack>/agents/``).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from thot.agent.models import AgentSpec
from thot.core.TkeirPaths import configs_dir, repo_root

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand_env(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return os.getenv(match.group(1), match.group(0))

    return _ENV_PATTERN.sub(repl, value)


def agents_dir() -> Path:
    """Return the core agents configuration directory.

    Example:
        >>> from thot.agent.registry import agents_dir
        >>> agents_dir().name
        'agents'
    """
    return Path(configs_dir()) / "agents"


def agent_config_dirs() -> list[Path]:
    """Return search roots for agent YAML (core configs + dataset packs).

    Dataset-specific agents live under ``datasets/<pack>/agents/`` (for
    example OSINT persona agents under ``datasets/osint/agents/``). Docker
    images may also ship packs under ``<package>/packs/<pack>/agents/``.

    Example:
        >>> from thot.agent.registry import agent_config_dirs
        >>> any(p.name == "agents" for p in agent_config_dirs())
        True
    """
    from thot.core.TkeirPaths import package_root

    roots: list[Path] = [agents_dir()]
    for base in (
        Path(repo_root()) / "datasets",
        Path(package_root()) / "packs",
    ):
        if not base.is_dir():
            continue
        for pack in sorted(base.iterdir()):
            if not pack.is_dir() or pack.name.startswith("."):
                continue
            candidate = pack / "agents"
            if candidate.is_dir():
                roots.append(candidate)
    extra = os.getenv("TKEIR_AGENT_CONFIG_DIRS", "").strip()
    if extra:
        for part in extra.split(os.pathsep):
            path = Path(part).expanduser()
            if path.is_dir():
                roots.append(path)
    # Preserve order, drop duplicates.
    seen: set[Path] = set()
    unique: list[Path] = []
    for root in roots:
        key = root.resolve()
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def resolve_agent_path(name: str, *, directory: Path | None = None) -> Path:
    """Resolve ``<name>.yaml`` across agent config roots."""
    if directory is not None:
        path = Path(directory) / f"{name}.yaml"
        if path.is_file():
            return path
        raise FileNotFoundError(f"agent spec not found: {path}")
    for root in agent_config_dirs():
        path = root / f"{name}.yaml"
        if path.is_file():
            return path
    searched = ", ".join(str(p) for p in agent_config_dirs())
    raise FileNotFoundError(
        f"agent spec not found: {name}.yaml (searched: {searched})"
    )


def load_agent_spec(name: str, *, directory: Path | None = None) -> AgentSpec:
    """Load ``<name>.yaml`` into an :class:`AgentSpec`.

    Example:
        >>> from thot.agent.registry import load_agent_spec
        >>> spec = load_agent_spec("researcher")
        >>> spec.name
        'researcher'
        >>> "search" in spec.tools
        True
    """
    path = resolve_agent_path(name, directory=directory)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"agent spec must be a mapping: {path}")
    if isinstance(raw.get("system_prompt"), str):
        raw["system_prompt"] = _expand_env(raw["system_prompt"])
    if isinstance(raw.get("wiki_merge_system_prompt"), str):
        raw["wiki_merge_system_prompt"] = _expand_env(
            raw["wiki_merge_system_prompt"]
        )
    if isinstance(raw.get("wiki_structured_facts_seed"), str):
        raw["wiki_structured_facts_seed"] = _expand_env(
            raw["wiki_structured_facts_seed"]
        )
    if isinstance(raw.get("model"), str):
        raw["model"] = _expand_env(raw["model"])
    raw.setdefault("name", name)
    return AgentSpec.model_validate(raw)


def list_agent_names(*, directory: Path | None = None) -> list[str]:
    """List available agent YAML stems (core + dataset packs).

    Example:
        >>> from thot.agent.registry import list_agent_names
        >>> "researcher" in list_agent_names()
        True
    """
    if directory is not None:
        root = Path(directory)
        if not root.is_dir():
            return []
        return sorted(p.stem for p in root.glob("*.yaml"))
    names: set[str] = set()
    for root in agent_config_dirs():
        if not root.is_dir():
            continue
        names.update(p.stem for p in root.glob("*.yaml"))
    return sorted(names)
