"""Title: Corpus-independent ranking fixtures + stem checks.

Loads synthetic cases from ``tests/fixtures/beir_rank/cases.yaml`` (no BEIR
download). Fixture ranking uses a small local overlap scorer (not production
search) so gold/hard-negative patterns stay checked without bloating
``lexical_signal``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from thot.tools.search.fusion import normalize_scores, weighted_fusion
from thot.tools.search.lexical_signal import token_stems, tokenize

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "beir_rank"
CASES_PATH = FIXTURE_DIR / "cases.yaml"


def _load_cases() -> list[dict]:
    data = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    return list(data["cases"])


def _doc_stems(text: str) -> set[str]:
    out: set[str] = set()
    for tok in tokenize(text):
        out |= token_stems(tok)
    return out


def _stem_match(query_stem: str, doc_stems: set[str]) -> bool:
    if query_stem in doc_stems:
        return True
    if len(query_stem) < 4:
        return False
    for doc_stem in doc_stems:
        if len(doc_stem) < 4:
            continue
        if doc_stem.startswith(query_stem) or query_stem.startswith(doc_stem):
            return True
    return False


def _fixture_overlap(query: str, title: str, body: str) -> float:
    """Simple weighted stem coverage for fixture ranking only."""
    qstems: set[str] = set()
    for tok in tokenize(query):
        if len(tok) >= 3:
            qstems |= token_stems(tok)
    if not qstems:
        return 0.0
    doc = _doc_stems(f"{title} {body}")
    if not doc:
        return 0.0
    num = 0.0
    den = 0.0
    for stem in qstems:
        weight = 1.0 + 0.08 * max(0, len(stem) - 5)
        den += weight
        if _stem_match(stem, doc):
            num += weight
    return num / den if den else 0.0


def _rare_factors(query: str, documents: list[dict]) -> dict[str, float]:
    """Relative long-stem gate for fixture ranking (test-only)."""
    rare = [
        stem
        for tok in tokenize(query)
        for stem in token_stems(tok)
        if len(stem) >= 6
    ]
    rare = list(dict.fromkeys(rare))
    if not rare:
        return {str(doc["_id"]): 1.0 for doc in documents}
    hit_counts: dict[str, int] = {}
    for doc in documents:
        doc_id = str(doc["_id"])
        doc_stems = _doc_stems(
            f"{doc.get('title') or ''} {doc.get('text') or ''}"
        )
        hit_counts[doc_id] = sum(
            1 for stem in rare if _stem_match(stem, doc_stems)
        )
    if not any(hit_counts.values()):
        return {doc_id: 1.0 for doc_id in hit_counts}
    out: dict[str, float] = {}
    for doc_id, hits in hit_counts.items():
        if hits == 0:
            out[doc_id] = 0.55
        else:
            out[doc_id] = 1.0 + 0.55 * (hits / len(rare))
    return out


def _near_copy_factor(query: str, doc_text: str) -> float:
    """Demote near-copies of long document-as-query inputs (fixture-only)."""
    qtoks = set(tokenize(query))
    if len(qtoks) < 32:
        return 1.0
    dtoks = set(tokenize(doc_text))
    if not qtoks or not dtoks:
        return 1.0
    jac = len(qtoks & dtoks) / len(qtoks | dtoks)
    contain = max(
        len(qtoks & dtoks) / len(qtoks),
        len(qtoks & dtoks) / len(dtoks),
    )
    if jac >= 0.55 or contain >= 0.85:
        return 0.04
    if jac >= 0.43 or contain >= 0.70:
        return 0.25
    if jac >= 0.35:
        return 0.55
    return 1.0


def _score_documents(query: str, documents: list[dict]) -> dict[str, float]:
    rare = _rare_factors(query, documents)
    scores: dict[str, float] = {}
    for doc in documents:
        doc_id = str(doc.get("_id") or "")
        if not doc_id:
            continue
        title = str(doc.get("title") or "")
        body = str(doc.get("text") or "")
        score = _fixture_overlap(query, title, body)
        score *= rare.get(doc_id, 1.0)
        score *= _near_copy_factor(query, f"{title} {body}".strip())
        scores[doc_id] = score
    return scores


def _rank(query: str, documents: list[dict], top_k: int) -> list[str]:
    scores = _score_documents(query, documents)
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
        assert gold <= set(
            ranked[:top_k]
        ), f"{case['id']}: gold {gold} not in top-{top_k} {ranked}"
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
        assert (
            gold_rank <= top_k
        ), f"{case['id']}: gold_rank={gold_rank} > top_k={top_k} ranked={ranked}"
    else:
        raise AssertionError(f"unknown assert {assertion!r} in {case['id']}")


def test_cases_are_corpus_independent():
    cases = _load_cases()
    assert len(cases) >= 8
    for case in cases:
        assert case.get("pattern"), case["id"]
        for doc in case["documents"]:
            doc_id = str(doc["_id"])
            assert not doc_id.isdigit(), case["id"]
            assert not doc_id.startswith("test-"), case["id"]
            assert "beir:" not in doc_id


def test_scientific_alias_stems():
    assert "foxo" in token_stems("foxo3a")
    assert "p150" in token_stems("p150n")
    assert "p150" in token_stems("p150glued")
    score = _fixture_overlap(
        "FoxO3a activation",
        "FOXO transcription factors",
        "FOXO3 under oxidative stress",
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
    assert "slow_stage_colbert" in codes
