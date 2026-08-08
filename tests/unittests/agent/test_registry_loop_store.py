"""Title: Registry loop store

Unit tests for agent registry, parse, safety, and run store.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
from pathlib import Path

from thot.agent.loop import parse_agent_message
from thot.agent.models import RunState, StepRecord
from thot.agent.registry import list_agent_names, load_agent_spec
from thot.agent.runs import RunStore
from thot.agent.safety import assert_tool_allowlisted, wrap_untrusted


def test_load_researcher_spec():
    spec = load_agent_spec("researcher")
    assert spec.name == "researcher"
    assert "search" in spec.tools
    assert spec.stop.max_steps >= 1
    assert "researcher" in list_agent_names()


def test_load_persona_agent_specs():
    for persona in (
        "j2_analyst",
        "moc_watch",
        "j2x_humint",
        "ctf_commander",
        "admin",
    ):
        for role in ("analyser", "reviewer", "writer"):
            name = f"{persona}_{role}"
            assert name in list_agent_names()
            spec = load_agent_spec(name)
            assert spec.name == name
            assert spec.output_contract == "grounded_findings_v1"
            if role == "analyser":
                assert "search" in spec.tools and "rag_query" in spec.tools
            else:
                assert spec.tools == []


def test_osint_dataset_agent_pack_discovered():
    from thot.agent.registry import agent_config_dirs, resolve_agent_path
    from thot.agent.workflows import (
        resolve_workflow_path,
        workflow_config_dirs,
    )

    assert any(
        p.as_posix().endswith("datasets/osint/agents")
        for p in agent_config_dirs()
    )
    assert any(
        p.as_posix().endswith("datasets/osint/workflows")
        for p in workflow_config_dirs()
    )
    assert "osint" in resolve_agent_path("j2_analyst_analyser").as_posix()
    assert "osint" in resolve_workflow_path("persona_j2_analyst").as_posix()


def test_enterprise_dataset_agent_pack_discovered():
    from thot.agent.registry import agent_config_dirs, resolve_agent_path
    from thot.agent.workflows import (
        resolve_workflow_path,
        workflow_config_dirs,
    )

    assert any(
        p.as_posix().endswith("datasets/enterprise/agents")
        for p in agent_config_dirs()
    )
    assert any(
        p.as_posix().endswith("datasets/enterprise/workflows")
        for p in workflow_config_dirs()
    )
    assert "enterprise" in resolve_agent_path("ceo_analyser").as_posix()
    assert "enterprise" in resolve_workflow_path("persona_ceo").as_posix()


def test_parse_tool_and_final():
    tool = parse_agent_message(
        '```json\n{"tool": "search", "arguments": {"query": "x"}}\n```'
    )
    assert tool["tool"] == "search"
    final = parse_agent_message(
        json.dumps(
            {
                "final": True,
                "findings": [
                    {"claim": "c", "chunk_ids": ["c1"], "confidence": 0.5}
                ],
                "unfilled": [],
            }
        )
    )
    assert final["final"] is True


def test_parse_nested_findings_json_fence():
    """Balanced extraction must keep the full findings array, not stop at first '}'."""
    message = """Here is the review:
```json
{
  "final": true,
  "findings": [
    {"claim": "Vessel IMO is 9385260.", "chunk_ids": ["a/1"], "document_ids": [], "confidence": 0.9},
    {"claim": "Flag is Panama.", "chunk_ids": ["a/2"], "document_ids": [], "confidence": 0.8},
    {"claim": "Built in 2005 by Hyundai Mipo Dockyard Co., Ltd.", "chunk_ids": ["a/3"], "document_ids": [], "confidence": 0.9}
  ],
  "unfilled": [],
  "notes": "llm_wiki_reviewer"
}
```
"""
    parsed = parse_agent_message(message)
    assert parsed["final"] is True
    assert len(parsed["findings"]) == 3
    assert "Ltd." in parsed["findings"][2]["claim"]


def test_wrap_untrusted_and_allowlist():
    text = wrap_untrusted({"a": 1}, source="search")
    assert "<untrusted" in text
    assert_tool_allowlisted("search", ["search"])
    try:
        assert_tool_allowlisted("delete", ["search"])
        assert False
    except PermissionError:
        pass


def test_run_store_roundtrip(tmp_path: Path):
    store = RunStore(tmp_path)
    store.ensure_layout()
    state = RunState(goal="find X", user_space="alice")
    store.write_state(state)
    step = StepRecord(step_index=0, thought_excerpt="hi")
    store.write_step(state.run_id, step)
    loaded = store.read_state(state.run_id)
    assert loaded is not None
    assert loaded.goal == "find X"
    assert store.list_steps(state.run_id)[0].step_index == 0
    store.append_blackboard(state.run_id, {"note": "n"})
    cancelled = store.request_cancel(state.run_id)
    assert cancelled is not None
    assert cancelled.cancel_requested is True
