"""Title: Installer

Unit tests for tkeir-installer plan JSON shape (SPIRE for agents).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
INSTALLER = ROOT / "scripts" / "installer"
sys.path.insert(0, str(INSTALLER))

import tkeir_installer as installer  # noqa: E402


def test_maturity_and_plan_json(monkeypatch, capsys):
    caps = [
        installer.Capability(
            name="Prometheus Operator",
            present=False,
            detail="not found",
            action="install",
        ),
        installer.Capability(
            name="cert-manager",
            present=False,
            detail="not found",
            action="install",
        ),
        installer.Capability(
            name="Kubeflow Pipelines",
            present=False,
            detail="not found",
            action="install",
        ),
        installer.Capability(
            name="Kyverno",
            present=False,
            detail="not found",
            action="install",
        ),
        installer.Capability(
            name="IdP / OIDC issuer",
            present=False,
            detail="unset",
            action="deploy Keycloak",
        ),
        installer.Capability(
            name="GPU (nvidia.com/gpu)",
            present=False,
            detail="none",
            action="ollama",
        ),
        installer.Capability(
            name="SPIRE",
            present=False,
            detail="absent (install for agents — ADR-0008)",
            action="install SPIRE (agents profile)",
        ),
    ]
    monkeypatch.setattr(installer, "detect", lambda _kc: caps)
    monkeypatch.setattr(
        installer.shutil, "which", lambda _n: "/usr/bin/kubectl"
    )
    rc = installer.cmd_plan(SimpleNamespace(kubeconfig=None, output="json"))
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["spire"] == "optional-for-agents"
    assert "maturity" in payload
    assert any(c["name"] == "SPIRE" for c in payload["capabilities"])


def test_apply_dry_run_prints_helm(capsys):
    rc = installer.cmd_apply(
        SimpleNamespace(
            profile="k8s-dev",
            release="tkeir",
            namespace="tkeir",
            dry_run=True,
        )
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "helm upgrade --install" in out
    assert "values-dev.yaml" in out


def test_detect_marks_spire_for_agents():
    with patch.object(installer, "_kubectl") as kubectl:
        kubectl.return_value = SimpleNamespace(
            returncode=1, stdout="", stderr="not found"
        )
        caps = installer.detect(None)
    spire = next(c for c in caps if c.name == "SPIRE")
    assert spire.present is False
    assert "ADR-0008" in spire.detail or "agents" in spire.action.lower()
