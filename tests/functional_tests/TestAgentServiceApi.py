"""Functional HTTP contracts for the agent service (no LLM loop)."""

from __future__ import annotations


def test_agent_health_and_ready(agent_client):
    health = agent_client.get("/health")
    assert health.status_code == 200
    assert health.json()["service"] == "tkeir-agent"
    ready = agent_client.get("/ready")
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "ready"
    assert isinstance(body.get("agents"), list)
    assert isinstance(body.get("workflows"), list)


def test_agent_catalogues(agent_client):
    agents = agent_client.get("/agent/agents")
    assert agents.status_code == 200
    assert isinstance(agents.json().get("agents"), list)

    workflows = agent_client.get("/agent/workflows")
    assert workflows.status_code == 200
    assert isinstance(workflows.json().get("workflows"), list)


def test_create_run_requires_goal(agent_client):
    response = agent_client.post(
        "/agent/runs",
        json={"agent": "researcher"},
    )
    assert response.status_code == 422


def test_create_run_unknown_agent(agent_client):
    response = agent_client.post(
        "/agent/runs",
        json={"agent": "no-such-agent-xyz", "goal": "probe"},
    )
    assert response.status_code == 404


def test_get_and_cancel_missing_run(agent_client):
    missing = "no-such-run-id"
    assert agent_client.get(f"/agent/runs/{missing}").status_code == 404
    assert (
        agent_client.post(f"/agent/runs/{missing}/cancel").status_code == 404
    )
