# -*- coding: utf-8 -*-
"""Shared pytest fixtures for T-KEIR tests."""

from __future__ import annotations

import os
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
TKEIR_DIR = os.path.abspath(os.path.join(TESTS_DIR, ".."))
if TKEIR_DIR not in sys.path:
    sys.path.insert(0, TKEIR_DIR)


@pytest.fixture(scope="session")
def tkeir_root() -> str:
    return TKEIR_DIR


@pytest.fixture(scope="module")
def pdf_bytes() -> bytes:
    fixture = os.path.join(TESTS_DIR, "fixtures", "converter_test2.pdf")
    with open(fixture, "rb") as handle:
        return handle.read()
