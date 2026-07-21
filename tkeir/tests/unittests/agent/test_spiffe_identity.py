"""Unit tests for agent SPIFFE identity (ADR-0008)."""

from __future__ import annotations

import time
from pathlib import Path

from thot.agent.guard import AgentGuard
from thot.agent.models import AgentSpec, RunState
from thot.agent.spiffe import (
    is_allowed_agent_spiffe_id,
    resolve_agent_spiffe_id,
    sanitize_agent_segment,
    spiffe_enforce,
    synthesize_dev_spiffe_id,
)


def test_sanitize_and_synthesize(monkeypatch):
    monkeypatch.delenv("SPIFFE_TRUST_DOMAIN", raising=False)
    assert sanitize_agent_segment("Researcher / v1") == "Researcher-v1"
    assert synthesize_dev_spiffe_id("researcher") == (
        "spiffe://tkeir.local/agent/researcher"
    )


def test_resolve_dev_mode(monkeypatch):
    monkeypatch.setenv("SPIFFE_MODE", "dev")
    monkeypatch.delenv("SPIFFE_ID", raising=False)
    monkeypatch.delenv("SPIFFE_ID_FILE", raising=False)
    assert resolve_agent_spiffe_id("writer") == (
        "spiffe://tkeir.local/agent/writer"
    )


def test_resolve_explicit_env(monkeypatch):
    monkeypatch.setenv("SPIFFE_MODE", "workload")
    monkeypatch.setenv("SPIFFE_ID", "spiffe://tkeir.local/agent/tkeir-agent")
    assert resolve_agent_spiffe_id("ignored") == (
        "spiffe://tkeir.local/agent/tkeir-agent"
    )


def test_allow_list(monkeypatch):
    monkeypatch.delenv("SPIFFE_AGENT_ID_PREFIX", raising=False)
    monkeypatch.delenv("SPIFFE_TRUST_DOMAIN", raising=False)
    assert is_allowed_agent_spiffe_id("spiffe://tkeir.local/agent/researcher")
    assert not is_allowed_agent_spiffe_id("spiffe://evil/agent/x")
    assert not is_allowed_agent_spiffe_id(None)


def test_enforce_flag(monkeypatch):
    monkeypatch.setenv("SPIFFE_ENFORCE", "true")
    monkeypatch.setenv("SPIFFE_MODE", "dev")
    assert spiffe_enforce() is True
    monkeypatch.setenv("SPIFFE_ENFORCE", "false")
    monkeypatch.setenv("GOVERNOR_MODE", "enforce")
    assert spiffe_enforce() is False


def test_guard_emit_sets_spiffe_id(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SPIFFE_MODE", "dev")
    monkeypatch.delenv("SPIFFE_ID", raising=False)
    monkeypatch.setenv("SPIFFE_ENFORCE", "false")
    guard = AgentGuard(tmp_path)
    state = RunState(
        agent="researcher",
        goal="g",
        user_space="demo-user",
        correlation_id="a" * 32,
    )
    record = guard.emit(kind="agent.plan", state=state)
    assert record.actor.spiffe_id == "spiffe://tkeir.local/agent/researcher"
    assert state.spiffe_id == record.actor.spiffe_id


def test_guard_denies_missing_spiffe_when_enforced(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("SPIFFE_MODE", "workload")
    monkeypatch.setenv("SPIFFE_ENFORCE", "true")
    monkeypatch.delenv("SPIFFE_ID", raising=False)
    monkeypatch.setenv("SPIFFE_ID_FILE", str(tmp_path / "missing"))
    monkeypatch.delenv("SPIFFE_ENDPOINT_SOCKET", raising=False)
    guard = AgentGuard(tmp_path, mode="enforce")
    state = RunState(
        agent="researcher",
        goal="g",
        user_space="demo-user",
        correlation_id="b" * 32,
        spiffe_id=None,
    )
    decision = guard.check_step(
        state, AgentSpec(name="researcher"), wall_started=time.monotonic()
    )
    assert decision.result == "deny"
    assert "SPIFFE" in decision.message
