"""Unit tests for governor flags, policy, API, and enforcement."""

from __future__ import annotations

import base64
import json
import sys
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from thot.action.sink import InMemoryActionSink, reset_action_sink_for_tests
from thot.governor.approvals import ApprovalQueue
from thot.governor.budgets import BudgetStore
from thot.governor.config import governor_settings
from thot.governor.flags import RuntimeFlagsStore
from thot.governor.middleware import GovernorEnforceMiddleware
from thot.governor.policy import PolicyEvaluator


@pytest.fixture
def governor_paths(monkeypatch, tmp_path):
    governor_settings.cache_clear()
    root = tmp_path
    monkeypatch.setenv("GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("GOVERNOR_STATE_ROOT", str(root))
    monkeypatch.setenv("GOVERNOR_FLAGS_PATH", str(root / "flags.json"))
    monkeypatch.setenv("GOVERNOR_BUDGET_DB", str(root / "budgets.db"))
    monkeypatch.setenv("GOVERNOR_APPROVALS_PATH", str(root / "approvals.json"))
    monkeypatch.setenv("GOVERNOR_AUTH_ENABLED", "false")
    governor_settings.cache_clear()
    reset_action_sink_for_tests()
    yield root
    governor_settings.cache_clear()
    reset_action_sink_for_tests()


def _evaluator(root) -> PolicyEvaluator:
    settings = governor_settings()
    return PolicyEvaluator(
        settings,
        RuntimeFlagsStore(settings.flags_path),
        BudgetStore(settings.budget_db_path, settings),
        ApprovalQueue(settings.approvals_path),
    )


def test_kill_switch_blocks_ingest(governor_paths):
    settings = governor_settings()
    flags = RuntimeFlagsStore(settings.flags_path)
    flags.set_kill("ingest", active=True, reason="test", actor="ops")
    evaluator = _evaluator(governor_paths)
    decision = evaluator.evaluate_http(
        method="POST",
        path="/ingest/document",
        authorization=None,
        service="tkeir-ingest",
    )
    assert decision.result == "deny"
    assert "kill:ingest" in decision.rules_fired


def test_budget_block_in_enforce(governor_paths, monkeypatch):
    settings = governor_settings()
    budgets = BudgetStore(settings.budget_db_path, settings)
    budgets.consume("tkeir-ingest", "docs", 10000, limit=10000)
    evaluator = _evaluator(governor_paths)
    decision = evaluator.evaluate_http(
        method="POST",
        path="/ingest/document",
        authorization=None,
        service="tkeir-ingest",
    )
    assert decision.result == "deny"
    assert "budget.exhausted" in decision.rules_fired
    budgets.close()


def test_admin_override_allows(governor_paths):
    settings = governor_settings()
    flags = RuntimeFlagsStore(settings.flags_path)
    flags.set_kill("all", active=True, reason="global", actor="ops")
    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {"scope": "intent:admin.override", "sub": "admin-1"}
            ).encode()
        )
        .decode()
        .rstrip("=")
    )
    token = f"x.{payload}.y"
    evaluator = _evaluator(governor_paths)
    decision = evaluator.evaluate_http(
        method="POST",
        path="/ingest/document",
        authorization=f"Bearer {token}",
        service="tkeir-ingest",
    )
    assert decision.result == "allow"
    assert "admin.override" in decision.rules_fired


def test_governor_api_kill_and_flags(governor_paths):
    from thot.governor import app as governor_app

    with TestClient(governor_app.app) as client:
        assert client.get("/health").status_code == 200
        flags = client.get("/governor/flags")
        assert flags.status_code == 200
        kill = client.post(
            "/governor/kill",
            json={"scope": "inference", "active": True, "reason": "drill"},
        )
        assert kill.status_code == 200
        body = kill.json()
        assert body["scopes"]["inference"]["active"] is True
        budgets = client.get("/governor/budgets")
        assert budgets.status_code == 200
        assert len(budgets.json()["items"]) == 2


def test_enforce_middleware_blocks(governor_paths):
    sink = InMemoryActionSink()
    settings = governor_settings()
    evaluator = PolicyEvaluator(
        settings,
        RuntimeFlagsStore(settings.flags_path),
        BudgetStore(settings.budget_db_path, settings),
        ApprovalQueue(settings.approvals_path),
    )
    evaluator.flags.set_kill(
        "inference", active=True, reason="test", actor="cli"
    )

    app = FastAPI()

    @app.post("/rag/query")
    async def query():
        return {"ok": True}

    app.add_middleware(
        GovernorEnforceMiddleware, sink=sink, evaluator=evaluator
    )

    with TestClient(app) as client:
        response = client.post("/rag/query", json={"query": "hello"})
        assert response.status_code == 403
        assert len(sink) == 1
        assert sink.list_by_correlation("") == [] or len(sink) == 1


def test_approval_queue(governor_paths):
    settings = governor_settings()
    queue = ApprovalQueue(settings.approvals_path)
    item = queue.enqueue(
        correlation_id="a" * 32,
        actor_id="user",
        intent="ingest",
        reason="scope missing",
    )
    pending = queue.list_pending()
    assert len(pending) == 1
    updated = queue.decide(item.approval_id, status="approved")
    assert updated is not None
    assert updated.status == "approved"
    assert queue.list_pending() == []


def test_governor_client_local_flags(governor_paths):
    from thot.governor.client import GovernorClient

    settings = governor_settings()
    RuntimeFlagsStore(settings.flags_path).set_kill(
        "index", active=True, reason="cli", actor="test"
    )
    client = GovernorClient(
        flags_path=settings.flags_path, base_url="http://invalid"
    )
    assert client.is_scope_killed("index") is True
    with pytest.raises(RuntimeError, match="kill switch"):
        client.assert_scope_active("index")


def test_cli_flags_and_kill(governor_paths):
    from thot.governor.cli import main as cli_main

    with pytest.raises(SystemExit) as exc:
        cli_main(["flags"])
    assert exc.value.code == 0
    with pytest.raises(SystemExit) as kill_exc:
        cli_main(
            ["kill", "--scope", "ingest", "--active", "true", "--reason", "t"]
        )
    assert kill_exc.value.code == 0


def test_auth_admin_scope(governor_paths, monkeypatch):
    governor_settings.cache_clear()
    monkeypatch.setenv("GOVERNOR_AUTH_ENABLED", "true")
    governor_settings.cache_clear()
    from thot.governor.auth import verify_admin_authorization

    with pytest.raises(HTTPException) as missing:
        verify_admin_authorization(None)
    assert missing.value.status_code == 401

    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {"scope": "intent:admin.override", "sub": "adm"}
            ).encode()
        )
        .decode()
        .rstrip("=")
    )
    assert verify_admin_authorization(f"Bearer x.{payload}.y") == "adm"


def test_observe_mode_does_not_block(governor_paths, monkeypatch):
    governor_settings.cache_clear()
    monkeypatch.setenv("GOVERNOR_MODE", "observe")
    governor_settings.cache_clear()
    evaluator = _evaluator(governor_paths)
    evaluator.flags.set_kill("ingest", active=True, reason="x", actor="y")
    decision = evaluator.evaluate_http(
        method="POST",
        path="/ingest/document",
        authorization=None,
        service="tkeir-ingest",
    )
    assert decision.result == "deny"

    sink = InMemoryActionSink()
    app = FastAPI()

    @app.post("/ingest/document")
    async def ingest():
        return {"ok": True}

    app.add_middleware(
        GovernorEnforceMiddleware, sink=sink, evaluator=evaluator
    )
    with TestClient(app) as client:
        response = client.post("/ingest/document", json={})
        assert response.status_code == 200


def test_scope_mismatch_escalates_in_observe(governor_paths, monkeypatch):
    governor_settings.cache_clear()
    monkeypatch.setenv("GOVERNOR_MODE", "observe")
    governor_settings.cache_clear()
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"scope": "intent:search", "sub": "user-1"}).encode()
        )
        .decode()
        .rstrip("=")
    )
    decision = _evaluator(governor_paths).evaluate_http(
        method="POST",
        path="/ingest/document",
        authorization=f"Bearer x.{payload}.y",
        service="tkeir-ingest",
    )
    assert decision.result == "escalate"
    assert "scope.mismatch" in decision.rules_fired


def test_governor_approvals_and_rollback(governor_paths):
    from thot.governor import app as governor_app

    settings = governor_settings()
    item = ApprovalQueue(settings.approvals_path).enqueue(
        correlation_id="b" * 32,
        actor_id="u",
        intent="ingest",
        reason="test",
    )
    with TestClient(governor_app.app) as client:
        listed = client.get("/governor/approvals")
        assert listed.status_code == 200
        assert len(listed.json()) >= 1
        approved = client.post(
            f"/governor/approvals/{item.approval_id}/approve",
            json={"note": "ok"},
        )
        assert approved.status_code == 200
        rollback = client.post("/governor/rollback", json={"run_id": "run-1"})
        assert rollback.status_code == 200
        missing = client.post(
            "/governor/approvals/does-not-exist/deny",
            json={"note": "nope"},
        )
        assert missing.status_code == 404


def test_middleware_escalate_queues_approval(governor_paths, monkeypatch):
    governor_settings.cache_clear()
    monkeypatch.setenv("GOVERNOR_MODE", "enforce")
    governor_settings.cache_clear()
    settings = governor_settings()
    evaluator = PolicyEvaluator(
        settings,
        RuntimeFlagsStore(settings.flags_path),
        BudgetStore(settings.budget_db_path, settings),
        ApprovalQueue(settings.approvals_path),
    )
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"scope": "intent:search", "sub": "user-2"}).encode()
        )
        .decode()
        .rstrip("=")
    )
    sink = InMemoryActionSink()
    app = FastAPI()

    @app.post("/ingest/document")
    async def ingest():
        return {"ok": True}

    app.add_middleware(
        GovernorEnforceMiddleware, sink=sink, evaluator=evaluator
    )
    with TestClient(app) as client:
        response = client.post(
            "/ingest/document",
            json={},
            headers={"authorization": f"Bearer x.{payload}.y"},
        )
        assert response.status_code == 403
        assert len(ApprovalQueue(settings.approvals_path).list_pending()) == 1


def test_cli_budgets_and_wiring(governor_paths, monkeypatch):
    from thot.governor.cli import main as cli_main

    with pytest.raises(SystemExit) as exc:
        cli_main(["budgets", "--actor", "tkeir-ingest"])
    assert exc.value.code == 0

    app = FastAPI()
    from thot.governor.wiring import wire_governor_middleware

    wire_governor_middleware(app, service="test")
    governor_settings.cache_clear()
    monkeypatch.setenv("GOVERNOR_MODE", "off")
    governor_settings.cache_clear()
    app2 = FastAPI()
    wire_governor_middleware(app2)


def test_client_http_flags(monkeypatch, governor_paths):
    from thot.governor.client import GovernorClient

    settings = governor_settings()
    flags_payload = RuntimeFlagsStore(settings.flags_path).snapshot()
    flags_payload.scopes["ingest"].active = True

    class FakeResp:
        def read(self):
            return json.dumps(
                flags_payload.model_dump(by_alias=True, mode="json")
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

    monkeypatch.setattr(
        "thot.governor.client.urlopen", lambda *_a, **_k: FakeResp()
    )
    client = GovernorClient(flags_path=settings.flags_path)
    assert client.is_scope_killed("ingest") is True


def test_governor_app_main(monkeypatch):
    from thot.governor import app as governor_app

    with patch("thot.governor.cli.main") as cli_main:
        monkeypatch.setattr(sys, "argv", ["tkeir-governor", "flags"])
        governor_app.main()
        cli_main.assert_called_once()

    with patch("uvicorn.run") as uvicorn_run:
        monkeypatch.setattr(sys, "argv", ["tkeir-governor"])
        governor_app.main()
        uvicorn_run.assert_called_once()


def test_consume_for_intent(governor_paths):
    settings = governor_settings()
    evaluator = _evaluator(governor_paths)
    from thot.governor.models import PolicyDecision

    decision = PolicyDecision(
        actor_id="tkeir-ingest", intent="ingest", result="allow"
    )
    evaluator.consume_for_intent(decision)
    budgets = BudgetStore(settings.budget_db_path, settings)
    snap = budgets.snapshot("tkeir-ingest", "docs", limit=10000)
    assert snap.consumed == 1.0
    budgets.close()


def test_action_token_mint_and_revoke(governor_paths, monkeypatch):
    from thot.governor.tokens import ActionTokenService

    monkeypatch.setenv("GOVERNOR_TOKEN_SECRET", "unit-test-secret")
    revoke_path = governor_paths / "revoked.json"
    service = ActionTokenService(
        secret=b"unit-test-secret",
        revoke_path=revoke_path,
    )
    compact, minted = service.mint(
        actor_id="tester",
        intent="search",
        ttl=60,
        constraints={"max_hits": 10},
    )
    assert compact
    assert minted.expires_at > minted.issued_at
    claims = service.verify(compact)
    assert claims.actor_id == "tester"
    assert claims.intent == "search"
    service.revoke(jti=minted.jti)
    with pytest.raises(ValueError, match="revoked"):
        service.verify(compact)


def test_governor_token_endpoints(governor_paths, monkeypatch):
    monkeypatch.setenv("GOVERNOR_TOKEN_SECRET", "unit-test-secret")
    governor_settings.cache_clear()
    from thot.governor import app as governor_app

    with TestClient(governor_app.app) as client:
        mint = client.post(
            "/governor/token",
            json={"intent": "search", "ttl": 30},
        )
        assert mint.status_code == 200
        body = mint.json()
        assert "token" in body
        assert "jti" in body
        revoke = client.post(
            "/governor/revoke",
            json={"jti": body["jti"], "reason": "unit"},
        )
        assert revoke.status_code == 200
        assert body["jti"] in revoke.json()["revoked"]
