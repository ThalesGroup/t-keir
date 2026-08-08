"""Title: Unit tests for library Agent / AgentSet.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from thot.agent.agent import Agent, AgentSet
from thot.agent.models import AgentSpec


def test_agent_from_spec_and_catalog() -> None:
    agent = Agent.from_spec(
        AgentSpec(name="demo", role="Demo", tools=["search"])
    )
    assert agent.name == "demo"
    assert agent.role == "Demo"
    assert agent.tools == ["search"]
    assert agent.is_wiki_prompt is False
    entry = agent.catalog_entry()
    assert entry["name"] == "demo"
    assert entry["has_wiki_prompt"] is False


def test_agent_load_researcher() -> None:
    agent = Agent.load("researcher")
    assert agent.name == "researcher"
    assert "search" in agent.tools
    assert agent.config_path.name == "researcher.yaml"


def test_agent_set_from_dirs_and_filter(tmp_path: Path) -> None:
    cfg = tmp_path / "agents"
    cfg.mkdir()
    (cfg / "alpha.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "alpha",
                "role": "A",
                "tools": ["search"],
                "system_prompt": "be alpha",
            }
        ),
        encoding="utf-8",
    )
    (cfg / "beta.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "beta",
                "role": "B",
                "tools": [],
                "wiki_merge_system_prompt": "merge",
            }
        ),
        encoding="utf-8",
    )
    full = AgentSet.from_config_dirs([cfg])
    assert set(full.names()) == {"alpha", "beta"}
    assert full.get("alpha").role == "A"
    filtered = AgentSet.from_config_dirs([cfg], names=["beta"])
    assert filtered.names() == ["beta"]
    assert filtered.get("beta").is_wiki_prompt is True
    wiki = filtered.catalog(wiki_only=True)
    assert len(wiki) == 1 and wiki[0]["name"] == "beta"
