"""Title: Conftest

Shared pytest fixtures for T-KEIR tests.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(TESTS_DIR, ".."))
TKEIR_DIR = os.path.join(REPO_ROOT, "tkeir")
if TKEIR_DIR not in sys.path:
    sys.path.insert(0, TKEIR_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


@pytest.fixture(scope="session")
def tkeir_root() -> str:
    return TKEIR_DIR


@pytest.fixture(scope="session")
def repo_root() -> str:
    return REPO_ROOT


@pytest.fixture(scope="module")
def pdf_bytes() -> bytes:
    fixture = os.path.join(TESTS_DIR, "fixtures", "converter_test2.pdf")
    with open(fixture, "rb") as handle:
        return handle.read()
