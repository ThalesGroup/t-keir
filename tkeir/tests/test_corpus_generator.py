"""Title: Corpus generator

Tests for the T-KEIR NATO + Enterprise corpus generator and ingest script.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
GEN = ROOT / "tools" / "corpus" / "generate_tkeir_corpus.py"
ING = ROOT / "tools" / "corpus" / "ingest_corpus.py"


def _gen(*args: str) -> None:
    subprocess.run([sys.executable, str(GEN), *args, "--quiet"], check=True)


def _ing(*args: str) -> None:
    subprocess.run([sys.executable, str(ING), *args, "--quiet"], check=True)


def test_generate_osint_corpus(tmp_path: pathlib.Path) -> None:
    _gen(
        "--output",
        str(tmp_path),
        "--count-osint",
        "20",
        "--count-enterprise",
        "0",
        "--seed",
        "7",
    )
    m = json.loads(
        (tmp_path / "corpus_nato" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert m["count_generated"] == 20
    assert len(list((tmp_path / "corpus_nato" / "ontologies").iterdir())) >= 6


def test_generate_enterprise_corpus(tmp_path: pathlib.Path) -> None:
    _gen(
        "--output",
        str(tmp_path),
        "--count-osint",
        "0",
        "--count-enterprise",
        "10",
        "--seed",
        "7",
    )
    m = json.loads(
        (tmp_path / "corpus_enterprise" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert m["count_generated"] == 10


def test_osint_topic_ids(tmp_path: pathlib.Path) -> None:
    _gen(
        "--output",
        str(tmp_path),
        "--count-osint",
        "40",
        "--count-enterprise",
        "0",
        "--seed",
        "7",
    )
    m = json.loads(
        (tmp_path / "corpus_nato" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    topics = {d["topic_id"] for d in m["documents"]}
    assert {"situational_awareness", "intelligence", "operations"} <= topics


def test_enterprise_topic_ids(tmp_path: pathlib.Path) -> None:
    _gen(
        "--output",
        str(tmp_path),
        "--count-osint",
        "0",
        "--count-enterprise",
        "40",
        "--seed",
        "7",
    )
    m = json.loads(
        (tmp_path / "corpus_enterprise" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    topics = {d["topic_id"] for d in m["documents"]}
    assert {"quality", "projects", "engineering"} <= topics


def test_user_space_assignments(tmp_path: pathlib.Path) -> None:
    _gen(
        "--output",
        str(tmp_path),
        "--count-osint",
        "10",
        "--count-enterprise",
        "5",
        "--seed",
        "7",
    )
    osint = json.loads(
        (tmp_path / "corpus_nato" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )["documents"]
    ent = json.loads(
        (tmp_path / "corpus_enterprise" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )["documents"]
    assert all(d["user_space"] == "demo-user" for d in osint)
    assert all(d["user_space"] == "demo-admin" for d in ent)


def test_corpus_field_present(tmp_path: pathlib.Path) -> None:
    _gen(
        "--output",
        str(tmp_path),
        "--count-osint",
        "5",
        "--count-enterprise",
        "3",
        "--seed",
        "7",
    )
    osint = json.loads(
        (tmp_path / "corpus_nato" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )["documents"]
    ent = json.loads(
        (tmp_path / "corpus_enterprise" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )["documents"]
    assert all(d["corpus"] == "osint" for d in osint)
    assert all(d["corpus"] == "enterprise" for d in ent)


def test_format_heterogeneity(tmp_path: pathlib.Path) -> None:
    _gen(
        "--output",
        str(tmp_path),
        "--count-osint",
        "60",
        "--count-enterprise",
        "20",
        "--seed",
        "7",
    )
    m = json.loads(
        (tmp_path / "corpus_nato" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    fmts = {d["format"] for d in m["documents"]}
    assert {"txt", "md", "html", "json"} <= fmts


def test_determinism(tmp_path: pathlib.Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    for out in (a, b):
        _gen(
            "--output",
            str(out),
            "--count-osint",
            "10",
            "--count-enterprise",
            "5",
            "--seed",
            "42",
        )
    da = json.loads(
        (a / "corpus_nato" / "manifest.json").read_text(encoding="utf-8")
    )["documents"]
    db = json.loads(
        (b / "corpus_nato" / "manifest.json").read_text(encoding="utf-8")
    )["documents"]
    assert [d["id"] for d in da] == [d["id"] for d in db]
    assert [d["title"] for d in da] == [d["title"] for d in db]


def test_ontologies_parse(tmp_path: pathlib.Path) -> None:
    from rdflib import Graph

    _gen("--output", str(tmp_path), "--only-ontologies")
    ont = tmp_path / "corpus_nato" / "ontologies"
    for f in sorted(ont.glob("*.owl")):
        g = Graph()
        g.parse(f, format="xml")
        assert len(g) > 50, f"{f.name}: only {len(g)} triples"
    for f in sorted(ont.glob("*.ttl")):
        g = Graph()
        g.parse(f, format="turtle")
        assert len(g) > 20, f"{f.name}: only {len(g)} triples"


def test_offline_download_safe(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TKEIR_CORPUS_OFFLINE", "1")
    _gen("--output", str(tmp_path), "--only-ontologies", "--download")
    assert (
        tmp_path / "corpus_nato" / "ontologies" / "c2sim_core.owl"
    ).exists()


def test_ingest_dry_run_both(tmp_path: pathlib.Path) -> None:
    _gen(
        "--output",
        str(tmp_path),
        "--count-osint",
        "10",
        "--count-enterprise",
        "5",
        "--seed",
        "7",
    )
    report = tmp_path / "report.json"
    _ing(
        "--corpus-dir",
        str(tmp_path),
        "--dry-run",
        "--output-report",
        str(report),
    )
    r = json.loads(report.read_text(encoding="utf-8"))
    assert r["total"] == 15
    assert r["sent"] == 0
    assert set(r["by_corpus"].keys()) == {"osint", "enterprise"}
    assert set(r["by_user_space"].keys()) == {"demo-user", "demo-admin"}


def test_ingest_filter_osint_only(tmp_path: pathlib.Path) -> None:
    _gen(
        "--output",
        str(tmp_path),
        "--count-osint",
        "10",
        "--count-enterprise",
        "5",
        "--seed",
        "7",
    )
    report = tmp_path / "r_osint.json"
    _ing(
        "--corpus-dir",
        str(tmp_path),
        "--corpus",
        "osint",
        "--dry-run",
        "--output-report",
        str(report),
    )
    r = json.loads(report.read_text(encoding="utf-8"))
    assert r["total"] == 10
    assert "enterprise" not in r["by_corpus"]


def test_ingest_filter_topic(tmp_path: pathlib.Path) -> None:
    _gen(
        "--output",
        str(tmp_path),
        "--count-osint",
        "40",
        "--count-enterprise",
        "0",
        "--seed",
        "7",
    )
    report = tmp_path / "r_topic.json"
    _ing(
        "--corpus-dir",
        str(tmp_path),
        "--topics",
        "intelligence",
        "--dry-run",
        "--output-report",
        str(report),
    )
    r = json.loads(report.read_text(encoding="utf-8"))
    assert set(r["by_topic"].keys()) == {"intelligence"}


def test_ingest_print_web_guide(tmp_path: pathlib.Path) -> None:
    _gen(
        "--output",
        str(tmp_path),
        "--count-osint",
        "5",
        "--count-enterprise",
        "3",
        "--seed",
        "7",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(ING),
            "--corpus-dir",
            str(tmp_path),
            "--print-web-guide",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "demo-user" in result.stdout
    assert "demo-admin" in result.stdout
    assert (
        "AcmeSystems" in result.stdout or "enterprise" in result.stdout.lower()
    )
