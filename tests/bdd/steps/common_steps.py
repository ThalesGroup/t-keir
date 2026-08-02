"""Shared Behave steps (offline harness + multi-service HTTP helpers)."""

from __future__ import annotations

import json
import re
from io import BytesIO

from behave import given, then, when


def _store_response(context, response) -> None:
    context.last_response = response
    try:
        context.last_json = response.json()
    except Exception:
        context.last_json = None


@given("the offline harness is ready")
def step_offline_ready(context) -> None:
    assert context.offline_ready is True


@then("the offline harness reports ready")
def step_offline_reports_ready(context) -> None:
    assert context.offline_ready is True
    assert context.session is not None


@given("the RAG service is available")
def step_rag_available(context) -> None:
    assert context.rag_up, f"RAG down at {context.rag_url}"


@given("the ingest service is available")
def step_ingest_available(context) -> None:
    assert context.ingest_up, f"ingest down at {context.ingest_url}"


@given("the agent service is available")
def step_agent_available(context) -> None:
    assert context.agent_up, f"agent down at {context.agent_url}"


@given("the governor service is available")
def step_governor_available(context) -> None:
    assert context.governor_up, f"governor down at {context.governor_url}"


@given("the OKF service is available")
def step_okf_available(context) -> None:
    assert context.okf_up, f"OKF down at {context.okf_url}"


@given("the audit service is available")
def step_audit_available(context) -> None:
    assert context.audit_up, f"audit down at {context.audit_url}"


@when('I GET "{path}"')
def step_get_rag(context, path: str) -> None:
    _store_response(context, context.session.get(f"{context.rag_url}{path}", timeout=10))


@when('I GET "{path}" on ingest')
def step_get_ingest(context, path: str) -> None:
    _store_response(
        context, context.session.get(f"{context.ingest_url}{path}", timeout=10)
    )


@when('I GET "{path}" on agent')
def step_get_agent(context, path: str) -> None:
    _store_response(
        context, context.session.get(f"{context.agent_url}{path}", timeout=10)
    )


@when('I GET "{path}" on governor')
def step_get_governor(context, path: str) -> None:
    _store_response(
        context,
        context.session.get(f"{context.governor_url}{path}", timeout=10),
    )


@when('I GET "{path}" on okf')
def step_get_okf(context, path: str) -> None:
    _store_response(
        context, context.session.get(f"{context.okf_url}{path}", timeout=10)
    )


@when('I GET "{path}" on audit')
def step_get_audit(context, path: str) -> None:
    _store_response(
        context, context.session.get(f"{context.audit_url}{path}", timeout=10)
    )


@when('I POST "{path}" with JSON:')
def step_post_rag_json(context, path: str) -> None:
    payload = json.loads(context.text or "{}")
    _store_response(
        context,
        context.session.post(
            f"{context.rag_url}{path}", json=payload, timeout=60
        ),
    )


@when('I POST "{path}" on ingest with JSON:')
def step_post_ingest_json(context, path: str) -> None:
    payload = json.loads(context.text or "{}")
    _store_response(
        context,
        context.session.post(
            f"{context.ingest_url}{path}", json=payload, timeout=60
        ),
    )


@when('I POST "{path}" on agent with JSON:')
def step_post_agent_json(context, path: str) -> None:
    payload = json.loads(context.text or "{}")
    _store_response(
        context,
        context.session.post(
            f"{context.agent_url}{path}", json=payload, timeout=30
        ),
    )


@when('I POST "{path}" on governor with JSON:')
def step_post_governor_json(context, path: str) -> None:
    payload = json.loads(context.text or "{}")
    _store_response(
        context,
        context.session.post(
            f"{context.governor_url}{path}", json=payload, timeout=30
        ),
    )


@when("I upload a tiny text document to ingest")
def step_upload_tiny_document(context) -> None:
    files = {
        "file": ("bdd-smoke.txt", BytesIO(b"BDD smoke document.\n"), "text/plain")
    }
    response = context.session.post(
        f"{context.ingest_url}/ingest/document",
        files=files,
        timeout=60,
    )
    _store_response(context, response)
    if isinstance(context.last_json, dict):
        context.last_ingest_id = context.last_json.get("ingest_id")


@when("I GET the last ingest job status")
def step_get_last_ingest_status(context) -> None:
    assert context.last_ingest_id, "no ingest_id from prior step"
    _store_response(
        context,
        context.session.get(
            f"{context.ingest_url}/ingest/status/{context.last_ingest_id}",
            timeout=30,
        ),
    )


@when('I upload workspace file "{relative_path}" without indexing')
def step_workspace_upload(context, relative_path: str) -> None:
    files = {
        "file": (
            relative_path.split("/")[-1],
            BytesIO(b"# BDD workspace smoke\n"),
            "text/markdown",
        )
    }
    data = {"path": relative_path, "index": "false"}
    _store_response(
        context,
        context.session.post(
            f"{context.ingest_url}/workspace/upload",
            files=files,
            data=data,
            timeout=60,
        ),
    )


@then("the response status is {code:d}")
def step_status_eq(context, code: int) -> None:
    assert context.last_response is not None
    assert context.last_response.status_code == code, (
        f"expected {code}, got {context.last_response.status_code}: "
        f"{context.last_response.text[:300]}"
    )


@then("the response status is one of {codes}")
def step_status_one_of(context, codes: str) -> None:
    expected = {int(part.strip()) for part in codes.split(",")}
    assert context.last_response is not None
    assert context.last_response.status_code in expected, (
        f"expected one of {sorted(expected)}, "
        f"got {context.last_response.status_code}: "
        f"{context.last_response.text[:300]}"
    )


@then('the JSON field "{field}" equals "{value}"')
def step_json_field_eq(context, field: str, value: str) -> None:
    assert isinstance(context.last_json, dict)
    assert str(context.last_json.get(field)) == value


@then('the JSON body has field "{field}"')
def step_json_has_field(context, field: str) -> None:
    assert isinstance(context.last_json, dict), context.last_json
    assert field in context.last_json, sorted(context.last_json.keys())


@then("the JSON body has fields:")
def step_json_has_fields(context) -> None:
    assert isinstance(context.last_json, dict)
    for row in context.table:
        field = row["field"]
        assert field in context.last_json, (
            f"missing {field!r} in {sorted(context.last_json.keys())}"
        )


@then('the JSON field "{field}" is a list')
def step_json_field_list(context, field: str) -> None:
    assert isinstance(context.last_json, dict)
    assert isinstance(context.last_json.get(field), list)


@then('the JSON field "{field}" matches "{pattern}"')
def step_json_field_matches(context, field: str, pattern: str) -> None:
    assert isinstance(context.last_json, dict)
    value = str(context.last_json.get(field, ""))
    assert re.fullmatch(pattern, value), f"{value!r} !~ {pattern!r}"


@then("the ingest status is terminal or in-flight")
def step_ingest_status_lifecycle(context) -> None:
    assert isinstance(context.last_json, dict)
    status = str(context.last_json.get("status", "")).lower()
    assert status in {
        "pending",
        "running",
        "succeeded",
        "failed",
        "noop",
    }, status
