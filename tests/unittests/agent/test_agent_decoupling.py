"""Title: Unit tests for decoupled agent base / LLMAgent / wiki workflow.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from thot.agent.base import BaseAgent, BaseAgentGuard, DecisionEngine
from thot.agent.guard import AgentGuard
from thot.agent.llm_agent import LLMAgent, PassthroughDecisionEngine
from thot.agent.models import AgentSpec, BudgetLimits, RunState, StopCondition
from thot.agent.runs import RunStore
from thot.agent.toolbox import ToolRegistry
from thot.agent.workflows import (
    WikiGeneratorWorkflow,
    list_workflow_names,
    load_workflow,
)
from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow as WG
from thot.mcp.handlers import McpHandlers


class ScriptedLlm:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls = 0

    async def generate(self, prompt, *, system=None, temperature=0.1) -> str:
        self.calls += 1
        if not self.replies:
            raise RuntimeError(f"no scripted replies left (call={self.calls})")
        return self.replies.pop(0)


class RecordingBackend:
    def __init__(self) -> None:
        self.spaces: list[str] = []

    async def hybrid_search(
        self, query, *, hits, user_space, language=None, search_mode=None
    ):
        self.spaces.append(user_space)
        return {
            "query": query,
            "user_space": user_space,
            "search_mode": search_mode or "user",
            "chunks": [
                {
                    "chunk_id": "chunk-1",
                    "parent_doc_id": "doc-1",
                    "text_raw": "T-KEIR is a RAG platform.",
                    "user_space": user_space,
                }
            ],
        }

    async def rag_query(self, query, **kw):
        return await self.hybrid_search(
            query,
            hits=kw.get("hits", 8),
            user_space=kw["user_space"],
            search_mode=kw.get("search_mode"),
        )

    async def get_document(self, **kw):
        return {"user_space": kw["user_space"], "fields": {}}

    async def ontology_from_query(self, query, **kw):
        return {
            "user_space": kw["user_space"],
            "summary": "",
            "document_ids": [],
            "triple_count": 0,
        }

    async def okf_bundle_list(self, *, user_space):
        return {"bundles": []}

    async def okf_bundle_get(self, **kw):
        return {}

    async def workspace_wiki_list(self, *, user_space, path="wiki"):
        return {
            "user_space": user_space,
            "path": path,
            "files": [],
            "count": 0,
        }

    async def workspace_wiki_get(self, *, user_space, path):
        return {"user_space": user_space, "path": path, "markdown": ""}

    async def okf_wiki_put(self, *, user_space, bundle_id, markdown):
        return {
            "user_space": user_space,
            "bundle_id": bundle_id,
            "path": f"/tmp/{bundle_id}/wiki.md",
            "chars": len(markdown or ""),
            "ok": True,
        }


def _spec(**kwargs: Any) -> AgentSpec:
    base: dict[str, Any] = {
        "name": "researcher",
        "tools": ["search"],
        "budgets": BudgetLimits(
            llm_tokens=50000, tool_calls=10, wall_seconds=60
        ),
        "stop": StopCondition(max_steps=5),
        "system_prompt": "test",
    }
    base.update(kwargs)
    return AgentSpec.model_validate(base)


def test_base_abcs_and_guard_implements() -> None:
    assert DecisionEngine.__abstractmethods__
    assert BaseAgentGuard.__abstractmethods__
    assert BaseAgent.__abstractmethods__
    with tempfile.TemporaryDirectory() as td:
        g = AgentGuard(Path(td))
        assert isinstance(g, BaseAgentGuard)
        assert g.validate_identity(None) in (True, False)
        assert g.check_action_permission(RunState(goal="g"), {"type": "final"})


def test_guard_validate_identity_enforced(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SPIFFE_ENFORCE", "true")
    monkeypatch.setenv("SPIFFE_MODE", "dev")
    g = AgentGuard(tmp_path / "gov", mode="enforce")
    assert g.validate_identity(None) is False
    assert g.validate_identity("") is False
    # Dev-mode allow-listed prefix typically accepts agent ids.
    monkeypatch.setenv("SPIFFE_ENFORCE", "false")
    assert g.validate_identity(None) is True


def test_guard_blocks_action_when_killed(tmp_path: Path) -> None:
    g = AgentGuard(tmp_path / "gov")
    g.flags.set_kill("agents", active=True, reason="drill", actor="test")
    state = RunState(goal="g", user_space="dev@tkeir")
    assert (
        g.check_action_permission(state, {"type": "tool", "tool": "search"})
        is False
    )


def test_llm_agent_independent_of_wiki() -> None:
    """LLMAgent can be constructed without any wiki imports in its module."""
    import thot.agent.llm_agent as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "wiki_upsert" not in src
    assert "WikiGenerator" not in src
    assert "okf.iterative_wiki" not in src
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        agent = LLMAgent(
            store=RunStore(root),
            guard=AgentGuard(root / "gov"),
            llm=ScriptedLlm([]),
            spec=AgentSpec(name="demo"),
        )
        assert isinstance(agent, BaseAgent)
        assert (
            PassthroughDecisionEngine().predict_action(RunState(goal="x"))[
                "type"
            ]
            == "delegate_loop"
        )


def test_llm_agent_run_matches_agent_loop(tmp_path: Path, monkeypatch) -> None:
    """LLMAgent.run produces the same grounded outcome as AgentLoop."""
    monkeypatch.setenv("SPIFFE_ENFORCE", "false")
    store = RunStore(tmp_path)
    store.ensure_layout()
    guard = AgentGuard(tmp_path / "gov")
    backend = RecordingBackend()
    toolbox = ToolRegistry(["search"], handlers=McpHandlers(backend=backend))
    llm = ScriptedLlm(
        [
            '```json\n{"tool":"search","arguments":{"query":"tkeir"}}\n```',
            '```json\n{"final":true,"findings":[{"claim":"T-KEIR is a RAG platform","chunk_ids":["chunk-1"],"document_ids":["doc-1"],"confidence":0.9}],"unfilled":[]}\n```',
        ]
    )
    state = RunState(
        goal="What is T-KEIR?",
        user_space="alice",
        correlation_id="a" * 32,
        agent="researcher",
    )
    store.write_state(state)
    agent = LLMAgent(
        store=store, guard=guard, llm=llm, toolbox=toolbox, spec=_spec()
    )
    out = asyncio.run(agent.run(state, state=state, spec=_spec()))
    assert out.status == "succeeded"
    assert out.result is not None
    assert out.result.findings[0].chunk_ids == ["chunk-1"]
    assert backend.spaces == ["alice"]


def test_llm_agent_rejects_bad_identity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SPIFFE_ENFORCE", "true")
    store = RunStore(tmp_path)
    store.ensure_layout()
    guard = AgentGuard(tmp_path / "gov", mode="enforce")
    agent = LLMAgent(
        store=store,
        guard=guard,
        llm=ScriptedLlm([]),
        spec=_spec(),
    )
    state = RunState(goal="g", user_space="dev@tkeir", correlation_id="d" * 32)
    store.write_state(state)
    with pytest.raises(PermissionError, match="identity"):
        asyncio.run(
            agent.run(state, identity_context=None, state=state, spec=_spec())
        )


def test_wiki_workflow_resolve_and_llm_wiki_yaml() -> None:
    cfg = WG.resolve_wiki_prompt_config({})
    assert cfg["prompt_name"] == ""
    wf = load_workflow("llm_wiki")
    assert any(s.builtin == "wiki_upsert" for s in wf.steps)
    assert WikiGeneratorWorkflow is WG
    assert "rag_with_wiki" in list_workflow_names()


def test_wiki_generator_upsert_single_pass(
    tmp_path: Path, monkeypatch
) -> None:
    """WikiGeneratorWorkflow.run_upsert writes wiki.md without AgentLoop."""
    monkeypatch.setenv("TKEIR_WORKSPACE", str(tmp_path))
    monkeypatch.delenv("OKF_ROOT", raising=False)

    store = RunStore(tmp_path / "agent")
    store.ensure_layout()
    guard = AgentGuard(tmp_path / "gov")

    class WikiLlm:
        calls = 0

        async def generate(self, prompt, *, system=None, temperature=0.1):
            self.calls += 1
            return (
                "---\ntype: Wiki\ntitle: Port\n---\n# Port\n\n"
                "## Answer\n\nHarbour is open.\n\n## Evidence\n\n"
                "- AIS gap (chunk_id=c1)\n\n## Sources\n\n"
                "- chunk_id=`c1`\n"
            )

    llm = WikiLlm()
    wiki_wf = WikiGeneratorWorkflow(store=store, guard=guard, llm=llm)
    state = RunState(
        goal="Latakia Port",
        user_space="dev@tkeir",
        correlation_id="e" * 32,
        agent="supervisor",
        params={
            "query": "Latakia Port",
            "chunks": [
                {
                    "chunk_id": "c1",
                    "parent_doc_id": "d1",
                    "text_raw": "AIS disabled near Latakia harbour.",
                }
            ],
            "max_wiki_chunks": 2,
        },
    )
    store.write_state(state)
    out = asyncio.run(wiki_wf.run_upsert(state))
    assert out.status != "failed", out.error
    assert out.params.get("has_llm_wiki") == "true"
    assert "Harbour is open" in (out.params.get("wiki_markdown") or "")
    assert out.params.get("bundle_id")
    assert llm.calls == 1
    # Blackboard marks wiki_generator provenance (not orchestrator monolith).
    bb = store.blackboard_path(out.run_id)
    assert bb.is_file()
    text = bb.read_text(encoding="utf-8")
    assert "wiki_upsert" in text
    assert "wiki_generator" in text


def test_wiki_generator_skipped_when_use_wiki_false(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "agent")
    store.ensure_layout()
    guard = AgentGuard(tmp_path / "gov")
    wiki_wf = WikiGeneratorWorkflow(store=store, guard=guard, llm=MagicMock())
    state = RunState(
        goal="q",
        user_space="dev@tkeir",
        correlation_id="f" * 32,
        params={"use_wiki": False, "query": "q"},
    )
    store.write_state(state)
    out = asyncio.run(wiki_wf.run_upsert(state))
    assert out.params.get("has_llm_wiki") == "false"
    assert out.params.get("wiki_markdown") == ""


def test_orchestrator_delegates_wiki_upsert(
    tmp_path: Path, monkeypatch
) -> None:
    """Orchestrator builtin wiki_upsert uses WikiGeneratorWorkflow."""
    monkeypatch.setenv("TKEIR_WORKSPACE", str(tmp_path))
    monkeypatch.delenv("OKF_ROOT", raising=False)

    from thot.agent.models import WorkflowStep
    from thot.agent.orchestrator import Orchestrator

    store = RunStore(tmp_path / "agent")
    store.ensure_layout()
    guard = AgentGuard(tmp_path / "gov")

    class WikiLlm:
        async def generate(self, prompt, *, system=None, temperature=0.1):
            return "# T\n\n## Answer\n\nDelegated.\n\n## Sources\n\n- c1\n"

    orch = Orchestrator(store=store, guard=guard, llm=WikiLlm())
    assert isinstance(orch._wiki_workflow(), WikiGeneratorWorkflow)
    state = RunState(
        goal="topic",
        user_space="dev@tkeir",
        correlation_id="g" * 32,
        params={
            "query": "topic",
            "chunks": [
                {
                    "chunk_id": "c1",
                    "parent_doc_id": "d1",
                    "text_raw": "Fact about topic.",
                }
            ],
        },
    )
    store.write_state(state)
    step = WorkflowStep(id="wiki", builtin="wiki_upsert")
    out = asyncio.run(orch._run_wiki_upsert(state, step))
    assert out.params.get("has_llm_wiki") == "true"
    assert "Delegated" in (out.params.get("wiki_markdown") or "")


def test_public_package_exports() -> None:
    import thot.agent as pkg

    for name in (
        "Agent",
        "AgentSet",
        "BaseAgent",
        "BaseAgentGuard",
        "DecisionEngine",
        "LLMAgent",
        "WikiGeneratorWorkflow",
        "load_workflow",
        "list_workflow_names",
    ):
        assert hasattr(pkg, name), name
