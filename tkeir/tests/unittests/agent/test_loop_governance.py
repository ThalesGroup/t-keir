"""Title: Loop governance

Agent loop: budgets, kill switch, multitenancy, grounded output.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from thot.agent.guard import AgentGuard
from thot.agent.loop import AgentLoop
from thot.agent.models import AgentSpec, BudgetLimits, RunState, StopCondition
from thot.agent.runs import RunStore
from thot.agent.toolbox import ToolRegistry
from thot.mcp.authz import McpPrincipal
from thot.mcp.handlers import McpHandlers


class ScriptedLlm:
    """Deterministic LLM stub returning a queue of replies."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls = 0

    async def generate(self, prompt, *, system=None, temperature=0.1) -> str:
        self.calls += 1
        if not self.replies:
            raise RuntimeError("no scripted replies left")
        return self.replies.pop(0)


class RecordingBackend:
    def __init__(self) -> None:
        self.spaces: list[str] = []

    async def hybrid_search(self, query, *, hits, user_space, language=None):
        self.spaces.append(user_space)
        return {
            "query": query,
            "user_space": user_space,
            "chunks": [
                {
                    "chunk_id": "chunk-1",
                    "parent_doc_id": "doc-1",
                    "text_raw": "T-KEIR is a RAG platform",
                    "user_space": user_space,
                }
            ],
        }

    async def rag_query(self, query, **kw):
        return await self.hybrid_search(
            query, hits=kw.get("hits", 8), user_space=kw["user_space"]
        )

    async def get_document(self, **kw):
        self.spaces.append(kw["user_space"])
        return {"user_space": kw["user_space"], "fields": {}}

    async def ontology_from_query(self, query, **kw):
        self.spaces.append(kw["user_space"])
        return {
            "user_space": kw["user_space"],
            "summary": "",
            "document_ids": [],
            "triple_count": 0,
        }

    async def okf_bundle_list(self, *, user_space):
        self.spaces.append(user_space)
        return {"user_space": user_space, "bundles": []}

    async def okf_bundle_get(self, *, user_space, bundle_id, concept_id=None):
        self.spaces.append(user_space)
        return {"user_space": user_space, "bundle_id": bundle_id}


def _spec(**kwargs: object) -> AgentSpec:
    base: dict[str, object] = {
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


def test_loop_search_then_final_grounded(tmp_path: Path):
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
    loop = AgentLoop(store=store, guard=guard, llm=llm, toolbox=toolbox)
    out = asyncio.run(loop.run(state, _spec()))
    assert out.status == "succeeded"
    assert out.result is not None
    assert out.result.findings[0].chunk_ids == ["chunk-1"]
    assert backend.spaces == ["alice"]
    assert len(store.list_steps(out.run_id)) >= 2


def test_loop_ignores_client_user_space_in_tool_args(tmp_path: Path):
    store = RunStore(tmp_path)
    store.ensure_layout()
    guard = AgentGuard(tmp_path / "gov")
    backend = RecordingBackend()
    toolbox = ToolRegistry(["search"], handlers=McpHandlers(backend=backend))
    llm = ScriptedLlm(
        [
            '```json\n{"tool":"search","arguments":{"query":"q","user_space":"eve"}}\n```',
            '```json\n{"final":true,"findings":[{"claim":"c","chunk_ids":["chunk-1"]}],"unfilled":[]}\n```',
        ]
    )
    state = RunState(goal="g", user_space="bob", correlation_id="b" * 32)
    store.write_state(state)
    out = asyncio.run(
        AgentLoop(store=store, guard=guard, llm=llm, toolbox=toolbox).run(
            state, _spec()
        )
    )
    assert backend.spaces == ["bob"]
    assert out.status == "succeeded"


def test_kill_switch_stops_run(tmp_path: Path):
    store = RunStore(tmp_path)
    store.ensure_layout()
    guard = AgentGuard(tmp_path / "gov")
    guard.flags.set_kill("agents", active=True, reason="drill", actor="test")
    llm = ScriptedLlm(
        ['```json\n{"tool":"search","arguments":{"query":"x"}}\n```']
    )
    toolbox = ToolRegistry(
        ["search"], handlers=McpHandlers(backend=RecordingBackend())
    )
    state = RunState(goal="g", user_space="dev@tkeir", correlation_id="c" * 32)
    store.write_state(state)
    out = asyncio.run(
        AgentLoop(store=store, guard=guard, llm=llm, toolbox=toolbox).run(
            state, _spec()
        )
    )
    assert out.status == "killed"
    assert llm.calls == 0 or out.error


def test_budget_blocks_in_enforce(tmp_path: Path):
    store = RunStore(tmp_path)
    store.ensure_layout()
    guard = AgentGuard(tmp_path / "gov")
    guard.mode = "enforce"
    llm = ScriptedLlm(
        [
            '```json\n{"tool":"search","arguments":{"query":"1"}}\n```',
            '```json\n{"tool":"search","arguments":{"query":"2"}}\n```',
        ]
    )
    toolbox = ToolRegistry(
        ["search"], handlers=McpHandlers(backend=RecordingBackend())
    )
    state = RunState(goal="g", user_space="dev@tkeir", correlation_id="d" * 32)
    # Pretend we already exhausted tool_calls
    state.usage.tool_calls = 1
    store.write_state(state)
    spec = _spec(
        budgets=BudgetLimits(tool_calls=1, llm_tokens=99999, wall_seconds=60)
    )
    out = asyncio.run(
        AgentLoop(store=store, guard=guard, llm=llm, toolbox=toolbox).run(
            state, spec
        )
    )
    assert out.status == "blocked"
    assert guard.approvals.list_pending()


def test_ungrounded_claims_become_unfilled(tmp_path: Path):
    store = RunStore(tmp_path)
    store.ensure_layout()
    guard = AgentGuard(tmp_path / "gov")
    llm = ScriptedLlm(
        [
            '```json\n{"final":true,"findings":[{"claim":"hallucination","chunk_ids":[]}],"unfilled":[]}\n```'
        ]
    )
    toolbox = ToolRegistry(
        ["search"], handlers=McpHandlers(backend=RecordingBackend())
    )
    state = RunState(goal="g", user_space="dev@tkeir", correlation_id="e" * 32)
    store.write_state(state)
    out = asyncio.run(
        AgentLoop(store=store, guard=guard, llm=llm, toolbox=toolbox).run(
            state, _spec()
        )
    )
    assert out.status == "succeeded"
    assert out.result is not None
    assert out.result.findings == []
    assert out.result.unfilled


def test_toolbox_rejects_cross_tenant_result():
    class EvilBackend(RecordingBackend):
        async def hybrid_search(
            self, query, *, hits, user_space, language=None
        ):
            return {
                "query": query,
                "user_space": "other",
                "chunks": [],
            }

    reg = ToolRegistry(["search"], handlers=McpHandlers(backend=EvilBackend()))
    with pytest.raises(PermissionError):
        asyncio.run(
            reg.invoke(
                "search",
                {"query": "q"},
                principal=McpPrincipal(user_space="alice"),
            )
        )
