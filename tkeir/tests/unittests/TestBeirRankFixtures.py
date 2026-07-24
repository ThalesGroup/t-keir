"""Title: Corpus-independent ranking fixtures + lexical fusion checks

Loads synthetic cases from ``tests/fixtures/beir_rank/cases.yaml`` (no BEIR
download) and verifies distinctive lexical scoring ranks gold above
hard-negatives for the smoke failure patterns.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from thot.tools.search.fusion import normalize_scores, weighted_fusion
from thot.tools.search.lexical_signal import (
    lexical_overlap_score,
    score_documents,
    token_stems,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "beir_rank"
CASES_PATH = FIXTURE_DIR / "cases.yaml"


def _load_cases() -> list[dict]:
    data = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    return list(data["cases"])


def _rank(query: str, documents: list[dict], top_k: int) -> list[str]:
    scores = score_documents(query, documents)
    # Simulate a weak competing signal that prefers long distractors (like CE
    # over-weighting topical text) — lexical fusion must still win.
    distractor_bias = {
        str(doc["_id"]): (
            0.2
            if doc.get("role") == "gold"
            else min(1.0, 0.35 + 0.01 * len(str(doc.get("text") or "")))
        )
        for doc in documents
    }
    fused = weighted_fusion(
        {
            "lexical_overlap": normalize_scores(scores),
            "cross_encoder": normalize_scores(distractor_bias),
        },
        {"lexical_overlap": 0.65, "cross_encoder": 0.35},
    )
    ordered = sorted(fused, key=fused.get, reverse=True)  # type: ignore[arg-type]
    return ordered[: max(1, top_k)]


def _check_assert(case: dict, ranked: list[str]) -> None:
    gold = {
        str(doc["_id"])
        for doc in case["documents"]
        if doc.get("role") == "gold"
    }
    hard = {
        str(doc["_id"])
        for doc in case["documents"]
        if doc.get("role") == "hard_negative"
    }
    assertion = case["assert"]
    top_k = int(case.get("top_k") or 3)
    if assertion == "gold_in_top_k":
        assert gold <= set(ranked[:top_k]), (
            f"{case['id']}: gold {gold} not in top-{top_k} {ranked}"
        )
    elif assertion == "gold_ranks_above_hard_negative":
        gold_rank = min(
            (ranked.index(g) for g in gold if g in ranked), default=10**9
        )
        hard_rank = min(
            (ranked.index(h) for h in hard if h in ranked), default=10**9
        )
        assert gold_rank < hard_rank, (
            f"{case['id']}: gold_rank={gold_rank} hard_rank={hard_rank} "
            f"ranked={ranked}"
        )
    elif assertion == "gold_rank_le_top_k":
        gold_rank = min(
            (ranked.index(g) + 1 for g in gold if g in ranked), default=10**9
        )
        assert gold_rank <= top_k, (
            f"{case['id']}: gold_rank={gold_rank} > top_k={top_k} ranked={ranked}"
        )
    else:
        raise AssertionError(f"unknown assert {assertion!r} in {case['id']}")


def test_cases_are_corpus_independent():
    cases = _load_cases()
    assert len(cases) >= 8
    for case in cases:
        assert case.get("pattern"), case["id"]
        for doc in case["documents"]:
            doc_id = str(doc["_id"])
            # No BEIR numeric / test-* corpus ids.
            assert not doc_id.isdigit(), case["id"]
            assert not doc_id.startswith("test-"), case["id"]
            assert "beir:" not in doc_id


def test_scientific_alias_stems():
    assert "foxo" in token_stems("foxo3a")
    assert "p150" in token_stems("p150n")
    assert "p150" in token_stems("p150glued")
    score = lexical_overlap_score(
        "FoxO3a activation",
        title="FOXO transcription factors",
        body="FOXO3 under oxidative stress",
    )
    assert score >= 0.4


def test_lexical_ranking_satisfies_fixture_asserts():
    for case in _load_cases():
        ranked = _rank(
            case["query"]["text"],
            case["documents"],
            int(case.get("top_k") or 3),
        )
        _check_assert(case, ranked)


def test_perf_budgets_fixture():
    path = FIXTURE_DIR / "perf_budgets.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    codes = {row["issue"] for row in data["budgets"]}
    assert "slow_stage_cross_encoder" in codes
    assert "slow_stage_ontology" in codes
