"""Title: Publish

Unit tests for approval-gated agent publish (Phase E).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from pathlib import Path

from thot.agent.models import GroundedFinding, GroundedFindings, RunState
from thot.agent.publish import ORIGIN_AGENT_GENERATED, publish_run
from thot.agent.runs import RunStore
from thot.governor.approvals import ApprovalQueue


def test_publish_enforce_awaits_then_publishes(tmp_path: Path):
    store = RunStore(tmp_path)
    store.ensure_layout()
    approvals = ApprovalQueue(tmp_path / "approvals.json")
    state = RunState(
        goal="Profile Acme",
        user_space="alice",
        correlation_id="c" * 32,
        status="succeeded",
        compose_result={
            "markdown": "# Acme\n\nGrounded note.\n",
            "citations_map": {"executive_summary": ["chunk-1"]},
        },
    )
    store.write_state(state)

    first = publish_run(
        store=store,
        guard_approvals=approvals,
        state=state,
        mode="enforce",
    )
    assert first["status"] == "awaiting_approval"
    approval_id = first["approval_id"]
    pending = approvals.get(approval_id)
    assert pending is not None
    assert pending.status == "pending"

    approvals.decide(approval_id, status="approved")
    second = publish_run(
        store=store,
        guard_approvals=approvals,
        state=state,
        approval_id=approval_id,
        mode="enforce",
    )
    assert second["status"] == "published"
    assert second["origin"] == ORIGIN_AGENT_GENERATED
    assert Path(second["markdown_path"]).is_file()
    assert "Acme" in Path(second["markdown_path"]).read_text(encoding="utf-8")


def test_publish_rejects_non_succeeded(tmp_path: Path):
    store = RunStore(tmp_path)
    store.ensure_layout()
    approvals = ApprovalQueue(tmp_path / "approvals.json")
    state = RunState(
        goal="g",
        user_space="alice",
        correlation_id="d" * 32,
        status="running",
        result=GroundedFindings(
            findings=[GroundedFinding(claim="x", chunk_ids=["c1"])]
        ),
    )
    out = publish_run(
        store=store, guard_approvals=approvals, state=state, mode="observe"
    )
    assert out["status"] == "rejected"
