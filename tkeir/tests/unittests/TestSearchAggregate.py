"""Title: Search Aggregate

Tests for chunk→document score aggregation.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.tools.search.search_aggregate import (
    aggregate_chunks_to_documents,
    document_score_from_chunks,
)


def test_document_score_from_chunks_single_hit():
    assert round(document_score_from_chunks([0.8]), 6) == 0.834657


def test_aggregate_chunks_to_documents_orders_by_score():
    docs = aggregate_chunks_to_documents(
        [
            {
                "document_id": "d1",
                "chunk_id": "c1",
                "score": 0.5,
                "title": "One",
            },
            {
                "document_id": "d2",
                "chunk_id": "c2",
                "score": 0.9,
                "title": "Two",
            },
            {
                "document_id": "d1",
                "chunk_id": "c3",
                "score": 0.4,
            },
        ]
    )
    assert [doc.document_id for doc in docs] == ["d2", "d1"]
    assert docs[0].hit_count == 1
    assert docs[1].hit_count == 2
    assert docs[1].chunk_ids == ["c1", "c3"]
    assert docs[1].title == "One"
