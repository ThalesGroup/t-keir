"""Unit tests for ColBERT rerank (search) and hybrid retrieve (eval)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from thot.tools.eval.hybrid_retrieve import rrf_fuse_runs
from thot.tools.search.rerank import colbert_late_interaction, colbert_rerank


class TestRrfFuseRuns(unittest.TestCase):
    def test_prefers_docs_ranked_high_in_both(self) -> None:
        bge = {"q1": {"a": 0.9, "b": 0.8, "c": 0.1}}
        bm25 = {"q1": {"a": 0.5, "c": 0.9, "d": 0.4}}
        fused = rrf_fuse_runs(bge, bm25, k=60, top_k=10)
        ranked = list(fused["q1"].keys())
        self.assertEqual(ranked[0], "a")
        self.assertIn("b", fused["q1"])
        self.assertIn("c", fused["q1"])
        self.assertIn("d", fused["q1"])

    def test_empty_runs(self) -> None:
        self.assertEqual(rrf_fuse_runs(), {})


class TestColbertLateInteraction(unittest.TestCase):
    def test_identical_tokens_score_high(self) -> None:
        vecs = np.eye(3, dtype=np.float32)
        score = colbert_late_interaction(vecs, vecs)
        self.assertGreater(score, 0.9)

    def test_orthogonal_tokens_score_low(self) -> None:
        q = np.array([[1.0, 0.0]], dtype=np.float32)
        d = np.array([[0.0, 1.0]], dtype=np.float32)
        score = colbert_late_interaction(q, d)
        self.assertLess(score, 0.1)


class TestColbertRerankSingleQuery(unittest.TestCase):
    def test_falls_back_when_disabled(self) -> None:
        candidates = [
            ("a", "alpha text", 0.2),
            ("b", "beta text", 0.9),
        ]
        with patch(
            "thot.tools.search.rerank.colbert_settings",
            return_value={
                "enabled": False,
                "top_m": 40,
                "first_stage_weight": 0.55,
                "colbert_weight": 0.45,
                "tail_weight": 0.15,
                "batch_size": 8,
                "rrf_k": 60,
                "pool": 100,
            },
        ):
            ranked = colbert_rerank("query", candidates, top_k=2)
        self.assertEqual([doc_id for doc_id, _ in ranked], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
