"""Title: Action Layer

Unit tests for ActionRecord, correlation, middleware, and logging.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from thot.action.correlation import (
    CORRELATION_HEADER,
    TRACEPARENT_HEADER,
    TraceContext,
    correlation_from_headers,
    current_correlation_id,
    generate_trace_id,
    parse_traceparent,
    reset_trace_context,
    set_trace_context,
)
from thot.action.middleware import ActionCorrelationMiddleware, intent_for_path
from thot.action.models import ActionRecord, new_action_id, sha256_hex
from thot.action.readiness import probe_provider, readiness_report
from thot.action.sink import InMemoryActionSink, default_action_sink
from thot.core.LlmWrapper import Provider, WrapperConfig
from thot.core.StructuredLogging import (
    JsonLogFormatter,
    configure_json_logging,
)
from thot.core.ThotMetrics import ThotMetrics


def test_new_action_id_is_ulid_shape():
    aid = new_action_id()
    assert len(aid) == 26
    assert aid.isalnum()


def test_generate_trace_id_is_32_hex():
    tid = generate_trace_id()
    assert len(tid) == 32
    int(tid, 16)


def test_parse_traceparent_valid():
    tp = f"00-{'ab' * 16}-{'cd' * 8}-01"
    ctx = parse_traceparent(tp)
    assert ctx is not None
    assert ctx.correlation_id == "ab" * 16
    assert ctx.parent_span_id == "cd" * 8
    assert ctx.sampled is True


def test_parse_traceparent_rejects_invalid():
    assert parse_traceparent(None) is None
    assert parse_traceparent("not-a-traceparent") is None
    assert parse_traceparent(f"00-{'0' * 32}-{'cd' * 8}-01") is None


def test_correlation_from_headers_prefers_traceparent():
    tp = f"00-{'11' * 16}-{'22' * 8}-01"
    ctx = correlation_from_headers(tp, "ff" * 16)
    assert ctx.correlation_id == "11" * 16


def test_correlation_from_x_header():
    ctx = correlation_from_headers(None, "ee" * 16)
    assert ctx.correlation_id == "ee" * 16


def test_action_record_seal_hash_chain():
    first = ActionRecord(correlation_id="a" * 32).seal("")
    assert len(first.evidence.record_hash) == 64
    second = ActionRecord(correlation_id="b" * 32).seal(
        first.evidence.record_hash
    )
    assert second.evidence.prev_hash == first.evidence.record_hash
    assert second.evidence.record_hash != first.evidence.record_hash


def test_action_schema_file_exists():
    schema = (
        Path(__file__).resolve().parents[2]
        / "thot"
        / "action"
        / "schemas"
        / "action.v1.json"
    )
    assert schema.is_file()
    data = json.loads(schema.read_text(encoding="utf-8"))
    assert data["properties"]["schema"]["const"] == "tkeir.action.v1"


def test_intent_for_path():
    assert intent_for_path("/rag/query") == "search"
    assert intent_for_path("/search") == "search"


def test_middleware_sets_correlation_and_records():
    sink = InMemoryActionSink()
    app = FastAPI()
    app.add_middleware(ActionCorrelationMiddleware, sink=sink)

    @app.get("/ping")
    def ping():
        assert current_correlation_id() is not None
        return {"ok": True}

    client = TestClient(app)
    cid = "aa" * 16
    response = client.get("/ping", headers={CORRELATION_HEADER: cid})
    assert response.status_code == 200
    assert response.headers[CORRELATION_HEADER] == cid
    assert TRACEPARENT_HEADER in response.headers
    assert len(sink) == 1
    records = sink.list_by_correlation(cid)
    assert len(records) == 1
    assert records[0].intent.declared == "search"
    assert records[0].evidence.record_hash


def test_middleware_respects_traceparent():
    sink = InMemoryActionSink()
    app = FastAPI()
    app.add_middleware(ActionCorrelationMiddleware, sink=sink)

    @app.post("/rag/query")
    def query():
        return {"answer": "x"}

    tp = f"00-{'be' * 16}-{'af' * 8}-01"
    client = TestClient(app)
    response = client.post("/rag/query", json={"query": "hi"})
    assert response.headers[CORRELATION_HEADER]
    response = client.post(
        "/rag/query",
        json={"query": "hi"},
        headers={TRACEPARENT_HEADER: tp},
    )
    assert response.headers[CORRELATION_HEADER] == "be" * 16
    assert sink.list_by_correlation("be" * 16)


def test_middleware_skips_probe_paths():
    sink = InMemoryActionSink()
    app = FastAPI()
    app.add_middleware(ActionCorrelationMiddleware, sink=sink)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert CORRELATION_HEADER in response.headers
    assert len(sink) == 0


def test_json_log_formatter_fields():
    fmt = JsonLogFormatter()
    rec = logging.LogRecord(
        "tkeir", logging.INFO, __file__, 1, "hello", (), None
    )
    rec.service = "unit"
    rec.correlation_id = "c" * 32
    rec.action_id = new_action_id()
    rec.actor = "tester"
    payload = json.loads(fmt.format(rec))
    assert payload["msg"] == "hello"
    assert payload["service"] == "unit"
    assert payload["correlation_id"] == "c" * 32
    assert "ts" in payload
    assert "level" in payload


def test_configure_json_logging_idempotent():
    log = configure_json_logging(service="unit-test")
    configure_json_logging(service="unit-test")
    markers = [getattr(h, "_tkeir_marker", None) for h in log.handlers]
    assert markers.count("tkeir-json-handler") == 1


def test_probe_provider_ollama_ok():
    cfg = WrapperConfig.from_env(file_models={})
    assert cfg.provider is Provider.OLLAMA

    class FakeResponse:
        def raise_for_status(self):
            return None

    client = AsyncMock()
    client.get = AsyncMock(return_value=FakeResponse())
    ok, detail = asyncio.run(probe_provider(config=cfg, client=client))
    assert ok is True
    assert "ollama" in detail
    client.get.assert_awaited()


def test_probe_provider_failure():
    cfg = WrapperConfig.from_env(file_models={})
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
    ok, detail = asyncio.run(probe_provider(config=cfg, client=client))
    assert ok is False
    assert detail


def test_readiness_report_not_ready(monkeypatch):
    async def _fake_probe(*_args, **_kwargs):
        return True, "mocked"

    monkeypatch.setattr(
        "thot.action.readiness.probe_provider",
        _fake_probe,
    )
    report = asyncio.run(readiness_report(vespa_ok=False, llm=None))
    assert report["status"] == "not_ready"
    assert report["checks"]["vespa"]["ok"] is False
    assert report["checks"]["provider"]["ok"] is True


def test_sha256_hex_stable():
    assert sha256_hex("x") == sha256_hex(b"x")


def test_contextvar_reset():
    ctx = TraceContext(correlation_id="dd" * 16, action_id=new_action_id())
    token = set_trace_context(ctx)
    assert current_correlation_id() == "dd" * 16
    reset_trace_context(token)
    assert current_correlation_id() is None


def test_default_sink_singleton():
    assert default_action_sink() is default_action_sink()


def test_probe_provider_openai_and_vllm():
    class FakeResponse:
        def raise_for_status(self):
            return None

    client = AsyncMock()
    client.get = AsyncMock(return_value=FakeResponse())

    openai_cfg = WrapperConfig.from_env(
        file_models={
            "provider": "openai",
            "embedding_model": "x",
            "llm_model": "y",
        }
    )
    # from_env may still read PROVIDER from env — build via replace
    from dataclasses import replace

    openai_cfg = replace(
        WrapperConfig.from_env(file_models={}),
        provider=Provider.OPENAI,
        openai_api_key="sk-test",
    )
    ok, detail = asyncio.run(probe_provider(config=openai_cfg, client=client))
    assert ok is True
    assert "openai" in detail

    vllm_cfg = replace(openai_cfg, provider=Provider.VLLM)
    ok, detail = asyncio.run(probe_provider(config=vllm_cfg, client=client))
    assert ok is True
    assert "vllm" in detail


def test_sink_clear_and_prev_hash():
    sink = InMemoryActionSink(maxlen=10)
    sink.append(ActionRecord(correlation_id="a" * 32))
    assert sink.prev_hash
    assert len(sink) == 1
    sink.clear()
    assert len(sink) == 0
    assert sink.prev_hash == ""


def test_current_action_id_bound():
    from thot.action.correlation import current_action_id

    ctx = TraceContext(correlation_id="cc" * 16, action_id=new_action_id())
    token = set_trace_context(ctx)
    assert current_action_id() == ctx.action_id
    reset_trace_context(token)
    assert current_action_id() is None


def test_log_structured_emits_json(capsys):
    from thot.core.StructuredLogging import log_structured

    configure_json_logging(service="cap-test")
    log_structured(
        "info",
        "structured-line",
        service="cap-test",
        path="/p",
        http_status=200,
    )
    captured = capsys.readouterr().out
    assert "structured-line" in captured
    line = [ln for ln in captured.splitlines() if "structured-line" in ln][-1]
    payload = json.loads(line)
    assert payload["service"] == "cap-test"
    assert payload["path"] == "/p"


def test_metrics_payload_bytes():
    ThotMetrics.create_counter(
        short_name="action_test",
        function_name="action_test_total",
        counter_description="test",
    )
    payload = ThotMetrics.generateMetricsResponse()
    assert isinstance(payload, (bytes, bytearray))
