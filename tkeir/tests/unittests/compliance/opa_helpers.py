"""Helpers for EU compliance OPA policy unit tests."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
POLICIES = REPO_ROOT / "compliance" / "opa" / "policies"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

OPA = shutil.which("opa")
requires_opa = pytest.mark.skipif(OPA is None, reason="opa not found on PATH")


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def eval_summary(package: str, input_data: dict[str, Any]) -> dict[str, Any]:
    assert OPA is not None
    proc = subprocess.run(
        [
            OPA,
            "eval",
            "--v0-compatible",
            "--format",
            "json",
            "--data",
            str(POLICIES),
            "--stdin-input",
            f"data.{package}.summary",
        ],
        input=json.dumps(input_data),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(f"opa eval failed: {proc.stderr}\n{proc.stdout}")
    blob = json.loads(proc.stdout)
    return blob["result"][0]["expressions"][0]["value"]


def articles_of(items: list[dict[str, Any]]) -> set[str]:
    return {str(i.get("article")) for i in items}
