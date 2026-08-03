"""Unit tests for agent path helpers and OKF v0.2 frontmatter."""

from __future__ import annotations

from thot.agent.paths import default_agent_root
from thot.okf.exporter import OKF_VERSION, render_frontmatter
from thot.okf.models import (
    OkfActorEvent,
    OkfConceptFrontmatter,
    OkfSourceEntry,
)


def test_default_agent_root_uses_workspace(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_ROOT", raising=False)
    monkeypatch.setenv("TKEIR_WORKSPACE", str(tmp_path))
    root = default_agent_root()
    assert root == (tmp_path / "agent").resolve()


def test_default_agent_root_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path / "custom-agent"))
    assert default_agent_root() == (tmp_path / "custom-agent").resolve()


def test_okf_version_is_v02():
    assert OKF_VERSION == "0.2"


def test_frontmatter_emits_spec_families():
    fm = OkfConceptFrontmatter(
        type="Document",
        title="Alpha",
        tkeir_doc_id="doc-alpha",
        tkeir_user_space="dev@tkeir",
        sources=[
            OkfSourceEntry(
                id="doc-alpha",
                resource="vespa://dev@tkeir/doc-alpha",
                title="Alpha",
            )
        ],
        generated=OkfActorEvent(by="process:tkeir-okf-export"),
    )
    text = render_frontmatter(fm)
    assert "type: Document" in text
    assert "tkeir_okf_version: '0.2'" in text or "tkeir_okf_version: 0.2" in text
    assert "generated:" in text
    assert "process:tkeir-okf-export" in text
    assert "sources:" in text
