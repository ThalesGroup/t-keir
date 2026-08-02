"""Functional HTTP contracts for governor flags / kill switch."""

from __future__ import annotations


def test_governor_health_ready_flags(governor_client):
    assert governor_client.get("/health").status_code == 200
    assert governor_client.get("/ready").status_code == 200
    flags = governor_client.get("/governor/flags")
    assert flags.status_code == 200
    body = flags.json()
    assert "scopes" in body


def test_governor_kill_toggle_ingest_scope(governor_client):
    kill = governor_client.post(
        "/governor/kill",
        json={
            "scope": "ingest",
            "active": True,
            "reason": "functional-smoke",
        },
    )
    assert kill.status_code == 200
    assert kill.json()["scopes"]["ingest"]["active"] is True

    clear = governor_client.post(
        "/governor/kill",
        json={
            "scope": "ingest",
            "active": False,
            "reason": "functional-smoke-clear",
        },
    )
    assert clear.status_code == 200
    assert clear.json()["scopes"]["ingest"]["active"] is False


def test_governor_budgets_list(governor_client):
    budgets = governor_client.get("/governor/budgets")
    assert budgets.status_code == 200
    assert isinstance(budgets.json().get("items"), list)
