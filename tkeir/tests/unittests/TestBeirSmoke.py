"""Title: BEIR smoke subset helpers

Unit tests for the fast BEIR smoke subset builder and rank alerts.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from thot.tools.search.beir_eval import Metrics
from thot.tools.search.beir_smoke import (
    build_smoke_subset,
    detect_rank_alerts,
    pick_close_docs,
)
from thot.tools.search.beir_tkeir import (
    annotate_document_with_business_ontology,
    load_beir_business_ontology_payload,
)
from thot.tools.search.index_documents import _ensure_golden_chunks_for_index


def test_ensure_golden_chunks_for_index_synthesizes_when_missing():
    doc = {
        "source_doc_id": "beir:scifact:1",
        "title": "Claim",
        "content": ["Cancer risk increases with age."],
        "golden_chunks": [],
    }
    out = _ensure_golden_chunks_for_index(doc)
    assert out["golden_chunks"]
    assert out["golden_chunks"][0]["chunk_id"].endswith("#chunk-0-index")
    assert "Cancer risk" in out["golden_chunks"][0]["text_raw"]


def test_load_beir_business_ontologies():
    for name in ("scifact", "fiqa", "arguana"):
        payload = load_beir_business_ontology_payload(name)
        assert payload is not None, name
        assert payload.get("concepts"), name
        assert all(c.get("concept_id") for c in payload["concepts"])


def test_annotate_document_with_business_ontology_tags_json_ld():
    payload = load_beir_business_ontology_payload("scifact")
    assert payload is not None
    doc = {
        "source_doc_id": "beir:scifact:9",
        "title": "Tumor study",
        "content": ["Cancer cells show increased gene expression."],
        "golden_chunks": [
            {
                "chunk_id": "beir:scifact:9#0",
                "text_raw": "Cancer cells show increased gene expression.",
            }
        ],
    }
    tagged = annotate_document_with_business_ontology(doc, payload)
    json_ld = (tagged.get("document_ontology") or {}).get("json_ld") or ""
    assert "CANCER" in json_ld or "cancer" in json_ld.lower()
    assert "DefinedTerm" in json_ld


def test_pick_close_docs_prefers_overlap():
    corpus = {
        "far": {"title": "", "text": "zzzz unrelated"},
        "near": {"title": "", "text": "alpha beta claim"},
        "mid": {"title": "", "text": "alpha only"},
    }
    close = pick_close_docs(
        "alpha beta evidence", corpus, exclude=set(), n=2
    )
    assert close[0] == "near"
    assert "far" not in close[:1]


def test_build_smoke_subset_gold_and_close_per_query():
    corpus = {
        "d1": {"title": "", "text": "alpha evidence paper"},
        "d2": {"title": "", "text": "alpha related abstract"},
        "d3": {"title": "", "text": "beta related abstract"},
        "d4": {"title": "", "text": "gamma unrelated"},
        "d5": {"title": "", "text": "delta filler text"},
        "d6": {"title": "", "text": "epsilon filler text"},
        "d7": {"title": "", "text": "zeta filler text"},
        "d8": {"title": "", "text": "eta filler text"},
        "d9": {"title": "", "text": "theta filler text"},
        "d10": {"title": "", "text": "iota filler text"},
        "d11": {"title": "", "text": "kappa filler text"},
        "d12": {"title": "", "text": "lambda filler text"},
    }
    queries = {"q1": "alpha evidence", "q2": "missing"}
    qrels = {"q1": {"d1": 1}, "q2": {"dx": 1}}
    subset, sq, sr, stats = build_smoke_subset(
        corpus,
        queries,
        qrels,
        n_queries=2,
        n_close=3,
        rank_docs=5,
        seed=0,
    )
    assert "q1" in sq
    assert "q2" not in sq
    assert "d1" in subset
    assert stats["gold_docs"] == 1
    assert stats["close_docs"] >= 3
    assert stats["min_pool_per_query"] >= 5
    assert len(subset) >= 5
    assert sr["q1"]["d1"] == 1


def test_build_smoke_subset_excludes_arguana_query_self():
    corpus = {
        "q1": {"title": "", "text": "argument itself with tokens"},
        "d_gold": {"title": "", "text": "counterargument opposing stance"},
        "d_noise": {"title": "", "text": "argument topical essay"},
        "d2": {"title": "", "text": "argument related filler a"},
        "d3": {"title": "", "text": "argument related filler b"},
        "d4": {"title": "", "text": "argument related filler c"},
        "d5": {"title": "", "text": "argument related filler d"},
        "d6": {"title": "", "text": "argument related filler e"},
        "d7": {"title": "", "text": "argument related filler f"},
        "d8": {"title": "", "text": "argument related filler g"},
        "d9": {"title": "", "text": "argument related filler h"},
        "d10": {"title": "", "text": "argument related filler i"},
    }
    queries = {"q1": "argument itself with tokens"}
    qrels = {"q1": {"d_gold": 1, "q1": 1}}
    subset, sq, sr, stats = build_smoke_subset(
        corpus,
        queries,
        qrels,
        n_queries=1,
        n_close=2,
        rank_docs=5,
        seed=1,
    )
    assert "q1" in sq
    assert "q1" not in subset
    assert "d_gold" in subset
    assert "q1" not in sr["q1"]
    assert stats["gold_docs"] == 1
    assert stats["min_pool_per_query"] >= 5


def test_detect_rank_alerts_tkeir_collapse():
    bm25 = Metrics(ndcg={"NDCG@10": 0.8})
    tkeir = Metrics(ndcg={"NDCG@10": 0.0})
    alerts = detect_rank_alerts(
        bm25=bm25,
        tkeir=tkeir,
        tkeir_results={"q1": {}},
        qrels={"q1": {"d1": 1}},
        tkeir_error=None,
    )
    codes = {a.code for a in alerts}
    assert "tkeir_ndcg_zero" in codes
    assert "empty_retrievals" in codes
    assert "gold_miss_all" in codes
    assert all(a.focus for a in alerts)


def test_detect_timing_alerts_cross_encoder():
    from thot.tools.search.beir_smoke import (
        StageTimings,
        detect_timing_alerts,
    )

    timings = StageTimings(
        queries=2,
        docs_indexed=10,
        retrieve_ms=100.0,
        dual_avg_ms={"cross_encoder": 2000.0, "vespa_arms": 50.0},
    )
    alerts = detect_timing_alerts(timings)
    assert any(a.code == "slow_stage_cross_encoder" for a in alerts)
    assert all(a.focus for a in alerts)


def test_render_smoke_report_leads_with_focus():
    from thot.tools.search.beir_smoke import (
        RankAlert,
        SmokeRun,
        StageTimings,
        render_smoke_report,
    )

    run = SmokeRun(
        name="scifact",
        queries=1,
        docs_indexed=5,
        gold_docs=1,
        close_docs=4,
        bm25=Metrics(ndcg={"NDCG@10": 0.9}),
        tkeir=Metrics(ndcg={"NDCG@10": 0.0}),
        timings=StageTimings(),
        alerts=[
            RankAlert(
                code="tkeir_ndcg_zero",
                detail="collapsed",
                severity="high",
                focus="check mapping",
            )
        ],
    )
    md = render_smoke_report([run], wall_s=1.0)
    assert "## Focus — problems to fix" in md
    assert md.index("Focus — problems") < md.index("Summary metrics")
    assert "Code focus:" in md
    assert "tkeir_ndcg_zero" in md
