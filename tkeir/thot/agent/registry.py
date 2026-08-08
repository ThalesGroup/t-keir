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
from thot.core.TkeirPaths import configs_dir

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand_env(value: str) -> str:
    """Expand ``${VAR}`` placeholders using the process environment.

    Args:
        value: String possibly containing ``${ENV_NAME}`` tokens.

    Returns:
        String with known variables substituted; unknown tokens left intact.

    Example:
        >>> import os
        >>> from thot.agent.registry import _expand_env
        >>> os.environ["TKEIR_TEST_VAR"] = "hello"
        >>> _expand_env("model=${TKEIR_TEST_VAR}")
        'model=hello'
        >>> _expand_env("x=${UNKNOWN_VAR_XYZ}")
        'x=${UNKNOWN_VAR_XYZ}'
        >>> del os.environ["TKEIR_TEST_VAR"]
    """

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
    When ``TKEIR_AGENT_USECASE`` (or aliases) is set, that pack is searched
    before other packs so colliding stems (e.g. ``wiki_writer``) resolve to
    the active usecase.

    Example:
        >>> from thot.agent.registry import agent_config_dirs
        >>> any(p.name == "agents" for p in agent_config_dirs())
        True
    """
    from thot.agent.pack_paths import (
        dataset_pack_subdir_dirs,
        dedupe_paths,
        extra_config_dirs_from_env,
    )

    roots: list[Path] = [
        agents_dir(),
        *dataset_pack_subdir_dirs("agents"),
        *extra_config_dirs_from_env("TKEIR_AGENT_CONFIG_DIRS"),
    ]
    return dedupe_paths(roots)


def resolve_agent_path(name: str, *, directory: Path | None = None) -> Path:
    """Resolve ``<name>.yaml`` across agent config roots.

    Args:
        name: Agent stem (without ``.yaml``).
        directory: Optional single root; raises if missing.

    Returns:
        Path to the agent YAML file.

    Raises:
        FileNotFoundError: When no matching spec exists.

    Example:
        >>> from thot.agent.registry import resolve_agent_path
        >>> resolve_agent_path("researcher").name
        'researcher.yaml'
    """
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


def agent_catalog_entry(name: str, *, directory: Path | None = None) -> dict:
    """Return catalog metadata for one agent (no full system prompts).

    Example:
        >>> from thot.agent.registry import agent_catalog_entry
        >>> entry = agent_catalog_entry("researcher")
        >>> entry["name"] == "researcher" and "tools" in entry
        True
    """
    spec = load_agent_spec(name, directory=directory)
    has_wiki = bool(
        (spec.wiki_merge_system_prompt or "").strip()
        or (spec.wiki_structured_facts_seed or "").strip()
        or spec.wiki_information_priority_keys
        or name.endswith("_prompt")
        or name == "okf_wiki_prompt"
    )
    return {
        "name": spec.name,
        "version": spec.version,
        "role": spec.role,
        "tools": list(spec.tools or []),
        "output_contract": spec.output_contract,
        "has_wiki_prompt": has_wiki,
        "wiki_information_priority_keys": list(
            spec.wiki_information_priority_keys or []
        ),
    }


def list_agent_catalog(
    *,
    directory: Path | None = None,
    wiki_only: bool = False,
) -> list[dict]:
    """List agent catalog entries for RAG/OKF/HMI discovery.

    Example:
        >>> from thot.agent.registry import list_agent_catalog
        >>> isinstance(list_agent_catalog(), list)
        True
    """
    out: list[dict] = []
    for name in list_agent_names(directory=directory):
        try:
            entry = agent_catalog_entry(name, directory=directory)
        except (OSError, ValueError, FileNotFoundError):
            continue
        if wiki_only and not entry.get("has_wiki_prompt"):
            continue
        out.append(entry)
    return out
