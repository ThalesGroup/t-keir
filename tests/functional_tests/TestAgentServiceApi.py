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
    payload = agents.json()
    assert isinstance(payload.get("agents"), list)
    assert isinstance(payload.get("catalog"), list)

    wiki = agent_client.get("/agent/agents", params={"wiki": "true"})
    assert wiki.status_code == 200
    wiki_body = wiki.json()
    assert wiki_body.get("catalog")
    assert all(e.get("has_wiki_prompt") for e in wiki_body["catalog"])

    templates = agent_client.get("/agent/templates")
    assert templates.status_code == 200
    names = templates.json().get("templates") or []
    assert "otan_sitrep" in names or "synthesis_note" in names

    workflows = agent_client.get("/agent/workflows")
    assert workflows.status_code == 200
    wfs = workflows.json().get("workflows") or []
    assert isinstance(wfs, list)
    assert "rag_with_wiki" in wfs
    assert "llm_wiki" in wfs


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
