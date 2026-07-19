"""Unit tests for audit hot store, WORM, verify, and API."""

from __future__ import annotations

import base64
import json
import sqlite3
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from thot.action.models import (
    ActionRecord,
    ActorInfo,
    IntentInfo,
    new_action_id,
)
from thot.action.sink import InMemoryActionSink, reset_action_sink_for_tests
from thot.audit.archiver import archive_unarchived
from thot.audit.config import audit_settings
from thot.audit.hot_store import _SCHEMA, SqliteHotStore
from thot.audit.privacy import SubjectKeyStore
from thot.audit.report import load_report
from thot.audit.sink_bridge import CompositeActionSink, HotStoreActionSink
from thot.audit.verify import verify_hot_chain, verify_store
from thot.audit.worm_store import WormSegmentStore


@pytest.fixture
def audit_paths(monkeypatch, tmp_path):
    audit_settings.cache_clear()
    root = tmp_path
    hot_path = root / "hot.db"
    worm_root = root / "worm"
    keys_path = root / "keys.db"
    monkeypatch.setenv("AUDIT_HOT_STORE_URL", f"sqlite:///{hot_path}")
    monkeypatch.setenv("AUDIT_WORM_ROOT", str(worm_root))
    monkeypatch.setenv("AUDIT_SUBJECT_KEYS_PATH", str(keys_path))
    monkeypatch.setenv("AUDIT_AUTH_ENABLED", "false")
    monkeypatch.setenv("AUDIT_SINK_MODE", "dual")
    audit_settings.cache_clear()
    reset_action_sink_for_tests()
    yield root
    audit_settings.cache_clear()
    reset_action_sink_for_tests()


def _make_postgres_store(monkeypatch, tmp_path: Path):
    """PostgresHotStore with mocked psycopg backed by SQLite."""
    db_path = tmp_path / "pg_sim.db"
    sq = sqlite3.connect(str(db_path), check_same_thread=False)
    sq.row_factory = sqlite3.Row
    sq.executescript(_SCHEMA)

    class _CursorWrapper:
        def __init__(self, cur):
            self._cur = cur

        def execute(self, sql, params=None):
            self._cur.execute(sql.replace("%s", "?"), params or ())

        def executemany(self, sql, params):
            self._cur.executemany(sql.replace("%s", "?"), params)

        def fetchone(self):
            return self._cur.fetchone()

        def fetchall(self):
            return self._cur.fetchall()

    class _CursorContext:
        def __enter__(self):
            return _CursorWrapper(sq.cursor())

        def __exit__(self, *_args):
            pass

    class _FakeConn:
        autocommit = True

        def cursor(self):
            return _CursorContext()

        def close(self):
            sq.close()

    fake_psycopg = types.ModuleType("psycopg")
    setattr(fake_psycopg, "connect", lambda _dsn: _FakeConn())
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    monkeypatch.setattr(
        "thot.audit.hot_store.PostgresHotStore._ensure_schema",
        lambda self: None,
    )
    from thot.audit.hot_store import PostgresHotStore

    return PostgresHotStore("postgres://audit:audit@localhost/audit")


def _sample_record(cid: str) -> ActionRecord:
    return ActionRecord(
        action_id=new_action_id(),
        correlation_id=cid,
        actor=ActorInfo(type="service", id="tkeir-api"),
        intent=IntentInfo(declared="search"),
    )


def test_hot_store_chain_and_query(audit_paths):
    store = SqliteHotStore(audit_paths / "hot.db")
    cid = "a" * 32
    store.append(_sample_record(cid))
    store.append(_sample_record(cid))
    assert store.count() == 2
    records = store.get_by_correlation(cid)
    assert len(records) == 2
    report = verify_hot_chain(store.iter_all())
    assert report.ok is True
    store.close()


def test_worm_segment_write_and_verify(audit_paths):
    worm = WormSegmentStore(audit_paths / "worm")
    records = [_sample_record("b" * 32)]
    seg = new_action_id()
    uri = worm.write_segment(seg, records)
    assert uri.startswith("worm://")
    loaded = worm.read_segment(seg)
    assert len(loaded) == 1
    with pytest.raises(FileExistsError):
        worm.write_segment(seg, records)


def test_archive_flow(audit_paths):
    store = SqliteHotStore(audit_paths / "hot.db")
    worm = WormSegmentStore(audit_paths / "worm")
    store.append(_sample_record("c" * 32))
    segment_id = archive_unarchived(store, worm)
    assert segment_id is not None
    assert len(worm.list_segments()) == 1
    assert store.unarchived(limit=10) == []
    report = verify_store(store, worm)
    assert report.ok is True
    store.close()


def test_composite_sink_writes_hot(audit_paths):
    store = SqliteHotStore(audit_paths / "hot.db")
    memory = InMemoryActionSink()
    composite = CompositeActionSink(memory, HotStoreActionSink(store))
    composite.append(_sample_record("d" * 32))
    assert store.count() == 1
    assert len(memory) == 1
    store.close()


def test_subject_forget(audit_paths):
    keys = SubjectKeyStore(audit_paths / "keys.db")
    pseudo = keys.pseudonym("user-123")
    assert keys.pseudonym("user-123") == pseudo
    assert keys.forget("user-123") is True
    assert keys.forget("user-123") is False
    keys.close()


def test_audit_api_report(audit_paths):
    from thot.audit import app as audit_app

    store = SqliteHotStore(audit_paths / "hot.db")
    cid = "e" * 32
    store.append(_sample_record(cid))
    store.close()

    with TestClient(audit_app.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        report = client.get(f"/audit/report?correlation_id={cid}")
        assert report.status_code == 200
        body = report.json()
        assert body["correlation_id"] == cid
        assert body["action_count"] == 1
        verify = client.get("/audit/verify")
        assert verify.status_code == 200
        assert verify.json()["ok"] is True


def test_load_report_empty(audit_paths):
    store = SqliteHotStore(audit_paths / "hot.db")
    report = load_report(store, "f" * 32)
    assert report["action_count"] == 0
    store.close()


def test_default_action_sink_dual(audit_paths, monkeypatch):
    from thot.action.sink import default_action_sink

    sink = default_action_sink()
    sink.append(_sample_record("1" * 32))
    store = SqliteHotStore(audit_paths / "hot.db")
    assert store.count() == 1
    store.close()


def test_audit_auth_scope(audit_paths, monkeypatch):
    import base64
    import json

    audit_settings.cache_clear()
    monkeypatch.setenv("AUDIT_AUTH_ENABLED", "true")
    audit_settings.cache_clear()
    from thot.audit.auth import verify_audit_authorization

    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"scope": "intent:audit.read", "sub": "aud-1"}).encode()
        )
        .decode()
        .rstrip("=")
    )
    token = f"header.{payload}.sig"
    assert verify_audit_authorization(f"Bearer {token}") == "aud-1"


def test_cli_report_json(audit_paths):
    from thot.audit.cli import main as cli_main

    store = SqliteHotStore(audit_paths / "hot.db")
    cid = "2" * 32
    store.append(_sample_record(cid))
    store.close()
    with pytest.raises(SystemExit) as exc:
        cli_main(["report", "--correlation-id", cid, "--format", "json"])
    assert exc.value.code == 0


def test_cli_verify_and_archive(audit_paths):
    from thot.audit.cli import main as cli_main

    store = SqliteHotStore(audit_paths / "hot.db")
    store.append(_sample_record("3" * 32))
    store.close()
    with pytest.raises(SystemExit) as exc:
        cli_main(["verify"])
    assert exc.value.code == 0
    with pytest.raises(SystemExit) as exc2:
        cli_main(["archive"])
    assert exc2.value.code == 0


def test_render_html_report(audit_paths):
    from thot.audit.report import build_report, render_html

    store = SqliteHotStore(audit_paths / "hot.db")
    cid = "4" * 32
    store.append(_sample_record(cid))
    report = build_report(store.get_by_correlation(cid), correlation_id=cid)
    html = render_html(report)
    assert cid in html
    store.close()


def test_verify_detects_tamper(audit_paths):
    store = SqliteHotStore(audit_paths / "hot.db")
    store.append(_sample_record("5" * 32))
    records = store.iter_all()
    records[0].evidence.record_hash = "0" * 64
    report = verify_hot_chain(records)
    assert report.ok is False
    store.close()


def test_open_hot_store_invalid():
    from thot.audit.hot_store import open_hot_store

    with pytest.raises(ValueError):
        open_hot_store("ftp://bad")


def test_sqlite_query_filters_and_prev_hash(audit_paths):
    store = SqliteHotStore(audit_paths / "hot.db")
    cid = "6" * 32
    record = _sample_record(cid)
    store.append(record)
    assert store.prev_hash
    hits = store.query(
        correlation_id=cid,
        actor_id=record.actor.id,
        occurred_from="1970-01-01T00:00:00.000Z",
        occurred_to="2999-01-01T00:00:00.000Z",
        limit=10,
        offset=0,
    )
    assert len(hits) == 1
    store.mark_archived([], worm_segment="worm://x", archived_at="now")
    store.close()


def test_postgres_hot_store(monkeypatch, tmp_path):
    store = _make_postgres_store(monkeypatch, tmp_path)
    cid = "7" * 32
    store.append(_sample_record(cid))
    store.append(_sample_record(cid))
    assert store.count() == 2
    assert len(store.get_by_correlation(cid)) == 2
    assert len(store.query(correlation_id=cid, limit=5)) == 2
    assert store.prev_hash
    worm = WormSegmentStore(tmp_path / "worm")
    segment_id = archive_unarchived(store, worm)
    assert segment_id is not None
    store.mark_archived([], worm_segment="worm://noop", archived_at="now")
    store.close()


def test_postgres_import_error(monkeypatch):
    import builtins

    monkeypatch.delitem(sys.modules, "psycopg", raising=False)
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "psycopg":
            raise ImportError("no psycopg")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    from thot.audit.hot_store import PostgresHotStore

    with pytest.raises(RuntimeError, match="psycopg is required"):
        PostgresHotStore("postgres://localhost/db")


def test_open_hot_store_file_scheme(audit_paths):
    from thot.audit.hot_store import open_hot_store

    store = open_hot_store(f"file://{audit_paths / 'file.db'}")
    assert store is not None
    store.append(_sample_record("8" * 32))
    store.close()


def test_worm_errors_and_anchor(audit_paths):
    worm = WormSegmentStore(audit_paths / "worm")
    with pytest.raises(ValueError):
        worm.write_segment(new_action_id(), [])
    with pytest.raises(FileNotFoundError):
        worm.read_segment("missing")
    seg = new_action_id()
    worm.write_segment(seg, [_sample_record("9" * 32)])
    worm.sha_path(seg).write_text("deadbeef  fake\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        worm.read_segment(seg)
    anchor = worm.write_anchor(record_hash="abc", segment_id=seg)
    assert anchor.is_file()


def test_verify_worm_segment_failure(audit_paths):
    worm = WormSegmentStore(audit_paths / "worm")
    seg = new_action_id()
    worm.write_segment(seg, [_sample_record("a" * 32)])
    worm.sha_path(seg).write_text("bad  fake\n")
    store = SqliteHotStore(audit_paths / "hot.db")
    store.append(_sample_record("a" * 32))
    report = verify_store(store, worm)
    assert report.ok is False
    assert report.worm_segments_checked == 0
    store.close()


def test_verify_prev_hash_mismatch(audit_paths):
    store = SqliteHotStore(audit_paths / "hot.db")
    store.append(_sample_record("b" * 32))
    records = store.iter_all()
    records[0].evidence.prev_hash = "dead"
    report = verify_hot_chain(records)
    assert report.ok is False
    store.close()


def test_composite_sink_hot_failure(audit_paths):
    store = SqliteHotStore(audit_paths / "hot.db")
    memory = InMemoryActionSink()
    hot = HotStoreActionSink(store)
    composite = CompositeActionSink(memory, hot)

    def _boom(_record):
        raise RuntimeError("hot down")

    hot.append = _boom
    composite.append(_sample_record("c" * 32))
    assert len(memory) == 1
    assert composite.prev_hash == hot.prev_hash
    store.close()


def test_composite_sink_memory_prev_hash(audit_paths):
    memory = InMemoryActionSink()
    composite = CompositeActionSink(memory, None)
    composite.append(_sample_record("d" * 32))
    assert composite.prev_hash == memory.prev_hash


def test_audit_auth_branches(monkeypatch):
    audit_settings.cache_clear()
    monkeypatch.setenv("AUDIT_AUTH_ENABLED", "true")
    monkeypatch.setenv("AUDIT_DEV_TOKEN", "dev-secret")
    audit_settings.cache_clear()
    from thot.audit.auth import verify_audit_authorization

    with pytest.raises(HTTPException) as missing:
        verify_audit_authorization(None)
    assert missing.value.status_code == 401

    assert verify_audit_authorization("Bearer dev-secret") == "dev-token"

    with pytest.raises(HTTPException) as bad:
        verify_audit_authorization("Bearer not-a-jwt")
    assert bad.value.status_code == 401

    scp_payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {"scp": ["intent:audit.read"], "sub": "scp-user"}
            ).encode()
        )
        .decode()
        .rstrip("=")
    )
    assert (
        verify_audit_authorization(f"Bearer x.{scp_payload}.y") == "scp-user"
    )

    roles_payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {
                    "resource_access": {"tkeir": {"roles": ["auditor"]}},
                    "sub": "role-user",
                }
            ).encode()
        )
        .decode()
        .rstrip("=")
    )
    assert (
        verify_audit_authorization(f"Bearer x.{roles_payload}.y")
        == "role-user"
    )

    denied_payload = (
        base64.urlsafe_b64encode(
            json.dumps({"scope": "intent:search", "sub": "nope"}).encode()
        )
        .decode()
        .rstrip("=")
    )
    with pytest.raises(HTTPException) as denied:
        verify_audit_authorization(f"Bearer x.{denied_payload}.y")
    assert denied.value.status_code == 403

    audit_settings.cache_clear()
    monkeypatch.delenv("AUDIT_AUTH_ENABLED", raising=False)
    audit_settings.cache_clear()
    assert verify_audit_authorization(None) == "anonymous"


def test_audit_api_endpoints(audit_paths):
    from thot.audit import app as audit_app

    store = SqliteHotStore(audit_paths / "hot.db")
    cid = "f" * 32
    store.append(_sample_record(cid))
    store.close()

    with TestClient(audit_app.app) as client:
        assert client.get("/ready").status_code == 200
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert metrics.headers["content-type"].startswith("text/plain")
        actions = client.get("/audit/actions", params={"correlation_id": cid})
        assert actions.status_code == 200
        assert actions.json()["total"] == 1
        html = client.get(f"/audit/report?correlation_id={cid}&format=html")
        assert html.status_code == 200
        assert cid in html.text
        archive = client.post("/audit/archive")
        assert archive.status_code == 200
        assert archive.json()["segment_id"]


def test_audit_api_no_hot_store(monkeypatch, tmp_path):
    audit_settings.cache_clear()
    monkeypatch.delenv("AUDIT_HOT_STORE_URL", raising=False)
    monkeypatch.setenv("AUDIT_WORM_ROOT", str(tmp_path / "worm"))
    monkeypatch.setenv("AUDIT_SUBJECT_KEYS_PATH", str(tmp_path / "keys.db"))
    audit_settings.cache_clear()
    from thot.audit import app as audit_app

    with TestClient(audit_app.app) as client:
        assert client.get("/health").status_code == 503
        assert client.get("/audit/report?correlation_id=x").status_code == 503


def test_cli_summary_forget_and_no_hot(monkeypatch, audit_paths):
    from thot.audit.cli import main as cli_main

    store = SqliteHotStore(audit_paths / "hot.db")
    store.append(_sample_record("0" * 32))
    store.close()
    with pytest.raises(SystemExit) as exc:
        cli_main(["summary", "--last", "24h"])
    assert exc.value.code == 0

    keys = SubjectKeyStore(audit_paths / "keys.db")
    keys.pseudonym("cli-subject")
    keys.close()
    with pytest.raises(SystemExit) as ok:
        cli_main(["forget", "--subject", "cli-subject"])
    assert ok.value.code == 0
    with pytest.raises(SystemExit) as fail:
        cli_main(["forget", "--subject", "missing-subject"])
    assert fail.value.code == 1

    audit_settings.cache_clear()
    monkeypatch.delenv("AUDIT_HOT_STORE_URL", raising=False)
    audit_settings.cache_clear()
    with pytest.raises(SystemExit) as no_hot:
        cli_main(["verify"])
    assert no_hot.value.code == 1


def test_cli_report_html(audit_paths):
    from thot.audit.cli import main as cli_main

    store = SqliteHotStore(audit_paths / "hot.db")
    cid = "1" * 32
    store.append(_sample_record(cid))
    store.close()
    with pytest.raises(SystemExit) as exc:
        cli_main(["report", "--correlation-id", cid, "--format", "html"])
    assert exc.value.code == 0


def test_archive_empty_batch(audit_paths):
    store = SqliteHotStore(audit_paths / "hot.db")
    worm = WormSegmentStore(audit_paths / "worm")
    assert archive_unarchived(store, worm) is None
    store.close()


def test_sink_modes(audit_paths, monkeypatch):
    from thot.action.sink import default_action_sink

    reset_action_sink_for_tests()
    audit_settings.cache_clear()
    monkeypatch.setenv("AUDIT_SINK_MODE", "hot")
    audit_settings.cache_clear()
    hot_only = default_action_sink()
    hot_only.append(_sample_record("2" * 32))
    store = SqliteHotStore(audit_paths / "hot.db")
    assert store.count() == 1
    store.close()

    reset_action_sink_for_tests()
    audit_settings.cache_clear()
    monkeypatch.setenv("AUDIT_SINK_MODE", "memory")
    audit_settings.cache_clear()
    memory_only = default_action_sink()
    memory_only.append(_sample_record("3" * 32))
    store = SqliteHotStore(audit_paths / "hot.db")
    assert store.count() == 1
    store.close()


def test_audit_app_main_cli_and_server(audit_paths, monkeypatch):
    from thot.audit import app as audit_app

    with patch("thot.audit.cli.main") as cli_main:
        monkeypatch.setattr(sys, "argv", ["tkeir-audit", "verify"])
        audit_app.main()
        cli_main.assert_called_once()

    with patch("uvicorn.run") as uvicorn_run:
        monkeypatch.setattr(sys, "argv", ["tkeir-audit"])
        audit_app.main()
        uvicorn_run.assert_called_once()


def test_audit_settings_defaults(monkeypatch):
    audit_settings.cache_clear()
    monkeypatch.delenv("AUDIT_HOT_STORE_URL", raising=False)
    monkeypatch.delenv("AUDIT_SINK_MODE", raising=False)
    settings = audit_settings()
    assert settings.sink_mode == "memory"
    assert settings.auth_enabled is False

    audit_settings.cache_clear()
    monkeypatch.setenv("AUDIT_AUTH_ENABLED", "yes")
    settings = audit_settings()
    assert settings.auth_enabled is True


def test_s3_settings_and_put_object(monkeypatch):
    from thot.audit.s3_put import put_object, s3_settings_from_env

    monkeypatch.delenv("AUDIT_WORM_S3_ENDPOINT", raising=False)
    assert s3_settings_from_env() is None

    monkeypatch.setenv("AUDIT_WORM_S3_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("AUDIT_WORM_S3_BUCKET", "tkeir-worm")
    cfg = s3_settings_from_env()
    assert cfg is not None
    assert cfg["bucket"] == "tkeir-worm"

    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    with patch(
        "thot.audit.s3_put.urllib.request.urlopen", return_value=FakeResp()
    ):
        uri = put_object(
            endpoint="http://minio:9000",
            bucket="tkeir-worm",
            key="segments/seg-1.jsonl.gz",
            body=b"gzip-bytes",
            access_key="minioadmin",
            secret_key="minioadmin",
        )
    assert uri == "s3://tkeir-worm/segments/seg-1.jsonl.gz"


def test_worm_mirrors_when_s3_configured(audit_paths, monkeypatch):
    monkeypatch.setenv("AUDIT_WORM_S3_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("AUDIT_WORM_S3_OBJECT_LOCK", "0")
    calls: list[str] = []

    def fake_mirror(**kwargs):
        calls.append(kwargs["segment_id"])
        return f"s3://tkeir-worm/segments/{kwargs['segment_id']}.jsonl.gz"

    with patch(
        "thot.audit.s3_put.mirror_worm_segment", side_effect=fake_mirror
    ):
        worm = WormSegmentStore(audit_paths / "worm-s3")
        worm.write_segment("seg-mirror", [_sample_record("a" * 32)])
    assert calls == ["seg-mirror"]


def test_cli_incident(audit_paths):
    from thot.audit.cli import main as cli_main

    store = SqliteHotStore(audit_paths / "hot.db")
    store.append(_sample_record("b" * 32))
    store.close()
    with pytest.raises(SystemExit) as exc:
        cli_main(["incident", "--kind", "72h"])
    assert exc.value.code == 0
