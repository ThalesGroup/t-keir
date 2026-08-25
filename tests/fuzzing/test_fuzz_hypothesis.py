"""Hypothesis property-based fuzz for pure T-KEIR helpers."""

from __future__ import annotations

import re

import pytest
from hypothesis import given, settings, strategies as st

from thot.action.models import sha256_hex
from thot.tools.ingest.user_workspace import sanitize_relative_path

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

# Exclude "." / ".." — sanitize_relative_path treats those as empty/traversal.
SAFE_SEGMENT = st.from_regex(r"[A-Za-z0-9._@+=\-]{1,24}", fullmatch=True).filter(
    lambda s: s not in {".", ".."}
)


@settings(max_examples=500, deadline=None)
@given(payload=st.binary(min_size=0, max_size=4096))
def test_sha256_hex_is_stable_digest(payload: bytes) -> None:
    digest = sha256_hex(payload)
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert sha256_hex(payload) == digest


@settings(max_examples=500, deadline=None)
@given(segments=st.lists(SAFE_SEGMENT, min_size=1, max_size=6))
def test_sanitize_relative_path_roundtrip(segments: list[str]) -> None:
    relative = "/".join(segments)
    cleaned = sanitize_relative_path(relative, allow_empty=False)
    assert cleaned
    assert ".." not in cleaned.split("/")
    assert cleaned == cleaned.strip("/")


@settings(max_examples=300, deadline=None)
@given(
    left=SAFE_SEGMENT,
    right=SAFE_SEGMENT,
)
def test_sanitize_relative_path_rejects_dotdot(left: str, right: str) -> None:
    with pytest.raises(ValueError):
        sanitize_relative_path(f"{left}/../{right}", allow_empty=False)
