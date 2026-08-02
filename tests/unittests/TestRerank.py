"""Title: Rerank

Tests for Vespa hit reranking helpers.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio

from thot.tools.search.rerank import (
    hit_text_for_rerank,
    rerank_vespa_children,
)


def test_hit_text_for_rerank_prefers_text_raw():
    assert (
        hit_text_for_rerank({"text_raw": "chunk", "title": "title"}) == "chunk"
    )


def test_rerank_vespa_children_reorders_by_score():
    class _Stub:
        async def rerank(self, query, documents, *, top_n=None, strategy=None):
            del query, top_n, strategy
            return [
                {"index": 1, "relevance_score": 0.8},
                {"index": 0, "relevance_score": 0.2},
            ]

    children = [
        {"fields": {"text_raw": "a"}, "relevance": 1.0},
        {"fields": {"text_raw": "b"}, "relevance": 0.5},
    ]
    out = asyncio.run(rerank_vespa_children(_Stub(), "q", children, top_n=2))
    assert [child["fields"]["text_raw"] for child in out] == ["b", "a"]
    assert out[0]["relevance"] == 0.8
