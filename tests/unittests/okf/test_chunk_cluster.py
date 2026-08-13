"""Unit tests for hash-bag helpers used by wiki chunk clustering."""

from __future__ import annotations

from thot.okf.chunk_cluster import (
    _chunk_text,
    _cosine,
    _hash_bag_vector,
    _l2_normalize,
)


def test_chunk_text_joins_fields():
    text = _chunk_text(
        {"title": "Quake", "text_raw": "Magnitude 5.8", "information": "AFAD"}
    )
    assert "Quake" in text
    assert "5.8" in text
    assert "AFAD" in text
    assert _chunk_text({}) == "empty"


def test_l2_normalize_and_cosine():
    v = _l2_normalize([3.0, 4.0])
    assert abs(sum(x * x for x in v) - 1.0) < 1e-6
    assert _cosine(v, v) > 0.99
    assert _cosine([1.0, 0.0], [0.0, 1.0]) < 0.1


def test_hash_bag_stable():
    a = _hash_bag_vector("earthquake near Izmir Turkey")
    b = _hash_bag_vector("earthquake near Izmir Turkey")
    assert a == b
    assert len(a) == 256
