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
