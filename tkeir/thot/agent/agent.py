"""Title: Identified T-KEIR agent (library).

An :class:`Agent` is a loaded YAML persona/runtime role — clearly distinct from
the HTTP tool surface in ``thot.tools.agent``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from thot.agent.models import AgentSpec
from thot.agent.registry import (
    agent_config_dirs,
    load_agent_spec,
    resolve_agent_path,
)


@dataclass(frozen=True)
class Agent:
    """One identified agent loaded from a configuration YAML.

    This is the library object used by :class:`~thot.agent.loop.AgentLoop` and
    the orchestrator. The HTTP service (`thot.tools.agent`) hosts a set of
    these agents; it is not itself an agent.

    Example:
        >>> from thot.agent.agent import Agent
        >>> agent = Agent.load("researcher")
        >>> agent.name
        'researcher'
        >>> agent.is_wiki_prompt in (True, False)
        True
    """

    spec: AgentSpec
    config_path: Path
    config_dir: Path

    @property
    def name(self) -> str:
        """Stable registry key (YAML stem / ``spec.name``).

        Example:
            >>> from thot.agent.agent import Agent
            >>> Agent.load("researcher").name
            'researcher'
        """
        return self.spec.name

    @property
    def role(self) -> str:
        """Human-readable role label from the agent YAML.

        Example:
            >>> from thot.agent.agent import Agent
            >>> from thot.agent.models import AgentSpec
            >>> Agent.from_spec(AgentSpec(name="demo")).role
            'demo'
        """
        return self.spec.role or self.spec.name

    @property
    def tools(self) -> list[str]:
        """MCP / tool names this agent may call.

        Example:
            >>> from thot.agent.agent import Agent
            >>> isinstance(Agent.load("researcher").tools, list)
            True
        """
        return list(self.spec.tools or [])

    @property
    def output_contract(self) -> str:
        """Grounded output schema name.

        Example:
            >>> from thot.agent.agent import Agent
            >>> from thot.agent.models import AgentSpec
            >>> Agent.from_spec(AgentSpec(name="demo")).output_contract
            'grounded_findings_v1'
        """
        return self.spec.output_contract

    @property
    def is_wiki_prompt(self) -> bool:
        """True when this agent supplies OKF wiki seed / merge prompts.

        Example:
            >>> from thot.agent.agent import Agent
            >>> Agent.load("researcher").is_wiki_prompt in (True, False)
            True
        """
        name = self.name
        return bool(
            (self.spec.wiki_merge_system_prompt or "").strip()
            or (self.spec.wiki_structured_facts_seed or "").strip()
            or self.spec.wiki_information_priority_keys
            or name.endswith("_prompt")
            or name == "okf_wiki_prompt"
        )

    @classmethod
    def from_spec(
        cls,
        spec: AgentSpec,
        *,
        config_path: Path | None = None,
        config_dir: Path | None = None,
    ) -> Agent:
        """Wrap an already-validated :class:`AgentSpec`.

        Example:
            >>> from thot.agent.agent import Agent
            >>> from thot.agent.models import AgentSpec
            >>> a = Agent.from_spec(AgentSpec(name="demo"))
            >>> a.name
            'demo'
        """
        path = Path(config_path) if config_path else Path(f"{spec.name}.yaml")
        directory = Path(config_dir) if config_dir else path.parent
        return cls(spec=spec, config_path=path, config_dir=directory)

    @classmethod
    def load(
        cls,
        name: str,
        *,
        directory: Path | None = None,
        directories: Sequence[Path] | None = None,
    ) -> Agent:
        """Load one agent by name from ``directory`` or ``directories``.

        Args:
            name: Agent YAML stem.
            directory: Single config root (preferred when set).
            directories: Ordered search roots when ``directory`` is omitted.

        Returns:
            Identified :class:`Agent`.

        Raises:
            FileNotFoundError: When no matching YAML exists.

        Example:
            >>> from thot.agent.agent import Agent
            >>> Agent.load("researcher").spec.tools  # doctest: +ELLIPSIS
            [...]
        """
        if directory is not None:
            path = resolve_agent_path(name, directory=directory)
            spec = load_agent_spec(name, directory=directory)
            return cls(spec=spec, config_path=path, config_dir=Path(directory))
        if directories:
            for root in directories:
                candidate = Path(root) / f"{name}.yaml"
                if candidate.is_file():
                    spec = load_agent_spec(name, directory=Path(root))
                    return cls(
                        spec=spec,
                        config_path=candidate,
                        config_dir=Path(root),
                    )
            searched = ", ".join(str(p) for p in directories)
            raise FileNotFoundError(
                f"agent spec not found: {name}.yaml (searched: {searched})"
            )
        path = resolve_agent_path(name)
        spec = load_agent_spec(name)
        return cls(spec=spec, config_path=path, config_dir=path.parent)

    def catalog_entry(self) -> dict[str, Any]:
        """Discovery metadata without full system prompts.

        Example:
            >>> from thot.agent.agent import Agent
            >>> entry = Agent.load("researcher").catalog_entry()
            >>> entry["name"] == "researcher" and "tools" in entry
            True
        """
        return {
            "name": self.name,
            "version": self.spec.version,
            "role": self.role,
            "tools": self.tools,
            "output_contract": self.output_contract,
            "has_wiki_prompt": self.is_wiki_prompt,
            "wiki_information_priority_keys": list(
                self.spec.wiki_information_priority_keys or []
            ),
            "config_path": str(self.config_path),
            "config_dir": str(self.config_dir),
        }


@dataclass
class AgentSet:
    """Ordered set of :class:`Agent` instances for one agent-service process.

    Built from one or more configuration directories (and optional name filter).
    Later directories win on name collisions.

    Example:
        >>> from thot.agent.agent import AgentSet
        >>> agents = AgentSet.from_config_dirs()
        >>> "researcher" in agents
        True
    """

    _by_name: dict[str, Agent] = field(default_factory=dict)
    config_dirs: list[Path] = field(default_factory=list)

    def __contains__(self, name: object) -> bool:
        """Return whether ``name`` is an agent in this set.

        Example:
            >>> from thot.agent.agent import AgentSet
            >>> "researcher" in AgentSet.from_config_dirs(names=["researcher"])
            True
        """
        return isinstance(name, str) and name in self._by_name

    def __len__(self) -> int:
        """Return the number of agents in this set.

        Example:
            >>> from thot.agent.agent import AgentSet
            >>> len(AgentSet.from_config_dirs(names=["researcher"]))
            1
        """
        return len(self._by_name)

    def get(self, name: str) -> Agent:
        """Return the agent named ``name``.

        Raises:
            KeyError: When the agent is not in this set.

        Example:
            >>> from thot.agent.agent import AgentSet
            >>> AgentSet.from_config_dirs(names=["researcher"]).get("researcher").name
            'researcher'
        """
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise KeyError(f"agent not in set: {name!r}") from exc

    def names(self) -> list[str]:
        """Sorted agent names in this set.

        Example:
            >>> from thot.agent.agent import AgentSet
            >>> AgentSet.from_config_dirs(names=["researcher"]).names()
            ['researcher']
        """
        return sorted(self._by_name)

    def agents(self) -> list[Agent]:
        """Agents in name order.

        Example:
            >>> from thot.agent.agent import AgentSet
            >>> AgentSet.from_config_dirs(names=["researcher"]).agents()[0].name
            'researcher'
        """
        return [self._by_name[n] for n in self.names()]

    def catalog(self, *, wiki_only: bool = False) -> list[dict[str, Any]]:
        """Catalog entries for discovery endpoints.

        Example:
            >>> from thot.agent.agent import AgentSet
            >>> entries = AgentSet.from_config_dirs(names=["researcher"]).catalog()
            >>> entries[0]["name"]
            'researcher'
        """
        out: list[dict[str, Any]] = []
        for agent in self.agents():
            entry = agent.catalog_entry()
            if wiki_only and not entry.get("has_wiki_prompt"):
                continue
            out.append(entry)
        return out

    def load_spec(self, name: str) -> AgentSpec:
        """Return the :class:`AgentSpec` for ``name`` (must be in this set).

        Example:
            >>> from thot.agent.agent import AgentSet
            >>> AgentSet.from_config_dirs(names=["researcher"]).load_spec("researcher").name
            'researcher'
        """
        return self.get(name).spec

    @classmethod
    def from_config_dirs(
        cls,
        directories: Sequence[Path | str] | None = None,
        *,
        names: Iterable[str] | None = None,
    ) -> AgentSet:
        """Load agents from configuration directories.

        Args:
            directories: Agent YAML roots. When ``None``, uses
                :func:`~thot.agent.registry.agent_config_dirs` (core + packs +
                ``TKEIR_AGENT_CONFIG_DIRS``).
            names: Optional allow-list of agent stems; others are ignored.

        Returns:
            Populated :class:`AgentSet`.

        Example:
            >>> from thot.agent.agent import AgentSet
            >>> AgentSet.from_config_dirs(names=["researcher"]).names()
            ['researcher']
        """
        roots = (
            [Path(p).expanduser() for p in directories]
            if directories is not None
            else list(agent_config_dirs())
        )
        allow = {n.strip() for n in names or [] if str(n).strip()} or None
        by_name: dict[str, Agent] = {}
        for root in roots:
            if not root.is_dir():
                continue
            for path in sorted(root.glob("*.yaml")):
                stem = path.stem
                if allow is not None and stem not in allow:
                    continue
                try:
                    agent = Agent.load(stem, directory=root)
                except (OSError, ValueError, FileNotFoundError):
                    continue
                # First match wins (same order as resolve_agent_path / usecase
                # preference). Later packs must not overwrite earlier specs.
                if agent.name in by_name:
                    continue
                by_name[agent.name] = agent
        return cls(_by_name=by_name, config_dirs=list(roots))

    @classmethod
    def from_default(
        cls,
        *,
        names: Iterable[str] | None = None,
        extra_dirs: Sequence[Path | str] | None = None,
    ) -> AgentSet:
        """Load the default config roots, optionally appending ``extra_dirs``.

        Example:
            >>> from thot.agent.agent import AgentSet
            >>> isinstance(AgentSet.from_default(), AgentSet)
            True
        """
        roots = list(agent_config_dirs())
        if extra_dirs:
            for part in extra_dirs:
                path = Path(part).expanduser()
                if path.is_dir() and path.resolve() not in {
                    r.resolve() for r in roots
                }:
                    roots.append(path)
        return cls.from_config_dirs(roots, names=names)
