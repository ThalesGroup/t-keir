"""Title: Dataset pack agents/workflows discovery and usecase preference.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from thot.agent.agent import AgentSet
from thot.agent.registry import (
    agent_config_dirs,
    list_agent_names,
    load_agent_spec,
    resolve_agent_path,
)
from thot.agent.workflows.loader import (
    list_workflow_names,
    load_workflow,
    resolve_workflow_path,
    workflow_config_dirs,
)
from thot.core.TkeirPaths import repo_root


def _pack_stems(pack: str, kind: str) -> list[str]:
    root = Path(repo_root()) / "datasets" / pack / kind
    assert root.is_dir(), f"missing pack dir {root}"
    return sorted(p.stem for p in root.glob("*.yaml"))


@pytest.mark.parametrize("pack", ["osint", "enterprise"])
def test_dataset_pack_agents_and_workflows_load(pack: str) -> None:
    agents = _pack_stems(pack, "agents")
    workflows = _pack_stems(pack, "workflows")
    assert agents, f"{pack} agents empty"
    assert workflows, f"{pack} workflows empty"

    listed_a = set(list_agent_names())
    listed_w = set(list_workflow_names())
    assert set(agents) <= listed_a
    assert set(workflows) <= listed_w

    assert any(
        p.as_posix().endswith(f"datasets/{pack}/agents")
        for p in agent_config_dirs()
    )
    assert any(
        p.as_posix().endswith(f"datasets/{pack}/workflows")
        for p in workflow_config_dirs()
    )

    for name in agents:
        spec = load_agent_spec(name)
        assert spec.name == name

    for name in workflows:
        wf = load_workflow(name)
        assert wf.name == name
        for step in wf.steps:
            if step.agent:
                load_agent_spec(step.agent)


@pytest.mark.parametrize(
    ("usecase", "unique_agent", "unique_workflow"),
    [
        ("osint", "j2_analyst_analyser", "persona_j2_analyst"),
        ("enterprise", "ceo_analyser", "persona_ceo"),
    ],
)
def test_usecase_prefers_pack_on_colliding_stems(
    monkeypatch: pytest.MonkeyPatch,
    usecase: str,
    unique_agent: str,
    unique_workflow: str,
) -> None:
    monkeypatch.setenv("TKEIR_AGENT_USECASE", usecase)
    wiki_path = resolve_agent_path("wiki_writer").as_posix()
    llm_path = resolve_workflow_path("llm_wiki").as_posix()
    assert f"datasets/{usecase}/" in wiki_path
    assert f"datasets/{usecase}/" in llm_path

    assert (
        f"datasets/{usecase}/" in resolve_agent_path(unique_agent).as_posix()
    )
    assert (
        f"datasets/{usecase}/"
        in resolve_workflow_path(unique_workflow).as_posix()
    )

    aset = AgentSet.from_default()
    assert unique_agent in aset.names()
    # AgentSet must match resolve (first / usecase preference).
    assert aset.get("wiki_writer").config_path is not None
    assert usecase in str(aset.get("wiki_writer").config_path)


def test_enterprise_persona_workflows() -> None:
    for persona in ("ceo", "cfo", "cto", "ciso", "cdo"):
        name = f"persona_{persona}"
        assert name in list_workflow_names()
        wf = load_workflow(name)
        assert [s.agent for s in wf.steps if s.agent] == [
            f"{persona}_analyser",
            f"{persona}_reviewer",
            f"{persona}_writer",
        ]
        assert any(s.compose is not None for s in wf.steps)


def test_osint_and_enterprise_briefs() -> None:
    otan = load_workflow("otan_c2_brief")
    assert any(s.agent == "wiki_writer" for s in otan.steps)
    ent = load_workflow("enterprise_brief")
    assert any(s.agent == "wiki_writer" for s in ent.steps)
    assert any(s.compose is not None for s in ent.steps)
