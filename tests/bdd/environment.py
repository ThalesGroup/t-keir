"""Behave environment hooks for T-KEIR BDD suites."""

from __future__ import annotations

import os

import requests

RAG_URL = os.environ.get(
    "RAG_URL", os.environ.get("RAG_URL_TEST", "http://localhost:8090")
).rstrip("/")
INGEST_URL = os.environ.get(
    "INGEST_URL", os.environ.get("INGEST_URL_TEST", "http://localhost:8091")
).rstrip("/")
AGENT_URL = os.environ.get(
    "AGENT_URL", os.environ.get("AGENT_URL_TEST", "http://localhost:8092")
).rstrip("/")
AUDIT_URL = os.environ.get(
    "AUDIT_URL", os.environ.get("AUDIT_URL_TEST", "http://localhost:8093")
).rstrip("/")
GOVERNOR_URL = os.environ.get(
    "GOVERNOR_URL",
    os.environ.get("GOVERNOR_URL_TEST", "http://localhost:8094"),
).rstrip("/")
OKF_URL = os.environ.get(
    "OKF_URL", os.environ.get("OKF_URL_TEST", "http://localhost:8095")
).rstrip("/")

_SERVICE_URL_ATTR = {
    "rag": "rag_url",
    "ingest": "ingest_url",
    "agent": "agent_url",
    "audit": "audit_url",
    "governor": "governor_url",
    "okf": "okf_url",
}


def _reachable(url: str, timeout: float = 2.0) -> bool:
    try:
        response = requests.get(f"{url}/health", timeout=timeout)
        return response.status_code < 500
    except requests.RequestException:
        return False


def before_all(context) -> None:
    context.rag_url = RAG_URL
    context.ingest_url = INGEST_URL
    context.agent_url = AGENT_URL
    context.audit_url = AUDIT_URL
    context.governor_url = GOVERNOR_URL
    context.okf_url = OKF_URL
    context.session = requests.Session()
    context.session.headers.update({"Accept": "application/json"})
    context.offline_ready = True
    context.last_response = None
    context.last_json = None
    context.last_ingest_id = None
    context.rag_up = _reachable(RAG_URL)
    context.ingest_up = _reachable(INGEST_URL)
    context.agent_up = _reachable(AGENT_URL)
    context.audit_up = _reachable(AUDIT_URL)
    context.governor_up = _reachable(GOVERNOR_URL)
    context.okf_up = _reachable(OKF_URL)


def _required_services(scenario) -> set[str]:
    tags = set(scenario.effective_tags)
    required: set[str] = set()
    for name in _SERVICE_URL_ATTR:
        if name in tags:
            required.add(name)
    text = " ".join(
        [scenario.name or ""] + [step.name for step in scenario.steps]
    ).lower()
    if "ingest" in text or "workspace" in text:
        required.add("ingest")
    if "governor" in text:
        required.add("governor")
    if "agent" in text:
        required.add("agent")
    if "okf" in text:
        required.add("okf")
    if "audit" in text:
        required.add("audit")
    if "rag" in text or "/search" in text or "/rag/" in text:
        required.add("rag")
    if not required:
        required.add("rag")
    return required


def before_scenario(context, scenario) -> None:
    tags = set(scenario.effective_tags)
    if "live" not in tags:
        return
    for service in _required_services(scenario):
        up_attr = f"{service}_up"
        url_attr = _SERVICE_URL_ATTR[service]
        if not getattr(context, up_attr, False):
            scenario.skip(
                f"{service} unreachable at {getattr(context, url_attr)}/health"
            )
            return
