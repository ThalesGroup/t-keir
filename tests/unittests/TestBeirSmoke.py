"""Title: BEIR smoke subset helpers

Unit tests for the fast BEIR smoke subset builder and rank alerts.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from thot.tools.eval.beir_eval import Metrics
from thot.tools.eval.beir_smoke import (
    build_smoke_subset,
    detect_rank_alerts,
    pick_close_docs,
)
from thot.tools.eval.beir_tkeir import (
    load_beir_business_ontology_payload,
)
from thot.tools.ingest.index_documents import _ensure_golden_chunks_for_index
from thot.tools.search.business_ontology import (
    annotate_document_with_business_ontology,
)


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
    for name in (
        "scifact",
        "fiqa",
        "arguana",
        "scidocs",
        "osint",
        "enterprise",
    ):
        payload = load_beir_business_ontology_payload(name)
        assert payload is not None, name
        assert payload.get("concepts"), name
        assert all(c.get("concept_id") for c in payload["concepts"])


def test_require_beir_business_ontology_and_force_stages():
    from thot.tools.eval.beir_tkeir import (
        beir_ontology_for_index,
        beir_ontology_for_search,
        require_beir_business_ontology,
    )
    from thot.tools.search.dual_hybrid_config import BusinessOntologyConfig
    from thot.tools.search.rag_config import load_rag_config

    payload = require_beir_business_ontology("scifact")
    assert payload is not None
    assert payload.get("concepts")

    dual = load_rag_config().dual_hybrid
    assert dual.business_ontology.index_enabled is True
    assert dual.business_ontology.search_enabled is True
    assert beir_ontology_for_index("scifact", dual_cfg=dual) is not None
    assert beir_ontology_for_search("scifact", dual_cfg=dual) is not None

    from dataclasses import replace

    dual_off = replace(
        dual,
        business_ontology=BusinessOntologyConfig(
            index_enabled=False,
            search_enabled=False,
        ),
    )
    assert beir_ontology_for_index("scifact", dual_cfg=dual_off) is None
    assert beir_ontology_for_search("scifact", dual_cfg=dual_off) is None


def test_index_resolves_dataset_business_ontology_from_source_id():
    from thot.tools.search.business_ontology import (
        resolve_index_ontology_payload,
    )

    doc = {"source_doc_id": "beir:scifact:42", "title": "x", "content": []}
    payload, name = resolve_index_ontology_payload(doc)
    assert name == "scifact"
    assert payload is not None
    assert payload.get("concepts")


def test_annotate_document_with_business_ontology_tags_json_ld():
    payload = load_beir_business_ontology_payload("scifact")
    assert payload is not None
    doc = {
        "source_doc_id": "beir:scifact:9",
        "title": "Tumor study",
        "content": ["Cancer cells show increased gene expression."],
        "kg": [
            {
                "subject": {"content": "cells"},
                "property": {"content": "show"},
                "value": {"content": "expression"},
                "field_type": "content",
            }
        ],
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
    assert (
        '"provenance": "external"' in json_ld
        or "'provenance': 'external'" in json_ld
    )
    # Document-side triple gets provenance=document; external triples added.
    provenances = {t.get("provenance") for t in tagged.get("kg") or []}
    assert "document" in provenances
    assert "external" in provenances
    assert tagged.get("core_concepts")
    assert any(
        row.get("role") == "cluster_center"
        for row in tagged["core_concepts"]
        if isinstance(row, dict)
    )


def test_annotate_document_adds_complete_ontology_path():
    from thot.tools.search.business_ontology import (
        annotate_document_with_business_ontology,
    )

    payload = {
        "concepts": [
            {
                "concept_id": "C4ISR",
                "preferred_label": "C4ISR",
                "broader": [],
                "narrower": ["SITUATIONAL_AWARENESS"],
            },
            {
                "concept_id": "SITUATIONAL_AWARENESS",
                "preferred_label": "situational awareness",
                "broader": ["C4ISR"],
                "narrower": ["AIS"],
            },
            {
                "concept_id": "AIS",
                "preferred_label": "Automatic Identification System",
                "synonyms": ["AIS"],
                "broader": ["SITUATIONAL_AWARENESS"],
                "narrower": ["AIS_ANOMALY"],
            },
            {
                "concept_id": "AIS_ANOMALY",
                "preferred_label": "AIS anomaly",
                "broader": ["AIS"],
                "narrower": ["DARK_ACTIVITY"],
            },
            {
                "concept_id": "DARK_ACTIVITY",
                "preferred_label": "AIS dark activity",
                "surface_forms": ["DARK_ACTIVITY_AIS_OFF", "DARK_ACTIVITY"],
                "broader": ["AIS_ANOMALY"],
                "narrower": [],
            },
            {
                "concept_id": "OPERATIONS",
                "preferred_label": "operations",
                "broader": [],
                "narrower": ["MESSAGE_PRECEDENCE"],
            },
            {
                "concept_id": "MESSAGE_PRECEDENCE",
                "preferred_label": "message precedence",
                "broader": ["OPERATIONS"],
                "narrower": ["PRIORITY"],
            },
            {
                "concept_id": "PRIORITY",
                "preferred_label": "PRIORITY precedence",
                "synonyms": ["PRIORITY"],
                "broader": ["MESSAGE_PRECEDENCE"],
                "narrower": [],
            },
        ]
    }
    doc = {
        "source_doc_id": "doc:1",
        "title": "Alert",
        "content": [
            "MARITIME ANALYTICS ALERT (DARK_ACTIVITY AIS_OFF): "
            "AIS transmitter disabled. Evaluation: B1 — PRIORITY"
        ],
        "kg": [],
        "golden_chunks": [],
    }
    tagged = annotate_document_with_business_ontology(doc, payload)
    ont = tagged["document_ontology"]
    paths = {
        row["concept_id"]: row
        for row in ont.get("external_ontology_paths") or []
    }
    assert "DARK_ACTIVITY" in paths
    assert paths["DARK_ACTIVITY"]["ontology_path"] == [
        "C4ISR",
        "SITUATIONAL_AWARENESS",
        "AIS",
        "AIS_ANOMALY",
        "DARK_ACTIVITY",
    ]
    assert "SITUATIONAL_AWARENESS" in (
        ont.get("external_ontology_path_ids") or []
    )
    assert "PRIORITY" in paths
    assert paths["PRIORITY"]["ontology_path"] == [
        "OPERATIONS",
        "MESSAGE_PRECEDENCE",
        "PRIORITY",
    ]


def test_annotate_enriches_nlp_misc_mention_with_ontology_path():
    from thot.tools.search.business_ontology import (
        annotate_document_with_business_ontology,
    )

    payload = {
        "concepts": [
            {"concept_id": "C4ISR", "preferred_label": "C4ISR", "broader": []},
            {
                "concept_id": "SITUATIONAL_AWARENESS",
                "preferred_label": "situational awareness",
                "broader": ["C4ISR"],
            },
            {
                "concept_id": "AIS",
                "preferred_label": "AIS",
                "broader": ["SITUATIONAL_AWARENESS"],
            },
            {
                "concept_id": "AIS_ANOMALY",
                "preferred_label": "AIS anomaly",
                "broader": ["AIS"],
            },
            {
                "concept_id": "DARK_ACTIVITY",
                "preferred_label": "AIS dark activity",
                "surface_forms": ["DARK_ACTIVITY_AIS_OFF"],
                "broader": ["AIS_ANOMALY"],
            },
        ]
    }
    nlp_json_ld = [
        {
            "@id": (
                "http://tkeir.local/doc/x/Misc/dark_activity_ais_off-53943ec1e704"
            ),
            "@type": ["http://tkeir.local/ontology/Misc"],
            "http://www.w3.org/2000/01/rdf-schema#label": [
                {"@value": "DARK_ACTIVITY_AIS_OFF"}
            ],
        }
    ]
    doc = {
        "source_doc_id": "doc:1",
        "content": [
            "MARITIME ALERT (DARK_ACTIVITY_AIS_OFF): AIS transmitter disabled"
        ],
        "kg": [],
        "document_ontology": {
            "json_ld": __import__("json").dumps(nlp_json_ld),
            "shacl_status": "PASSED",
        },
    }
    tagged = annotate_document_with_business_ontology(doc, payload)
    ont = tagged["document_ontology"]
    graph = __import__("json").loads(ont["json_ld"])
    assert isinstance(graph, list)
    misc = next(
        node
        for node in graph
        if "Misc/dark_activity" in str(node.get("@id") or "")
    )
    assert misc["ontology_path_compact"] == (
        "C4ISR/SITUATIONAL_AWARENESS/AIS/AIS_ANOMALY/DARK_ACTIVITY"
    )
    assert misc["maps_to_concept"] == "DARK_ACTIVITY"
    assert any(
        row.get("concept_id") == "DARK_ACTIVITY"
        for row in ont.get("external_ontology_paths") or []
    )


def test_resolve_search_business_ontology_loads_osint_and_merges():
    from thot.tools.search.business_ontology import (
        business_ontology_to_json_ld,
        resolve_search_business_ontology,
    )

    payload = resolve_search_business_ontology(dataset="osint")
    assert payload is not None
    assert len(payload["concepts"]) >= 10
    merged = resolve_search_business_ontology(
        dataset="osint",
        request_payload={
            "concepts": [
                {
                    "concept_id": "CUSTOM_TEST_CONCEPT",
                    "preferred_label": "Custom Test",
                }
            ]
        },
    )
    assert merged is not None
    ids = {c["concept_id"] for c in merged["concepts"]}
    assert "CUSTOM_TEST_CONCEPT" in ids
    json_ld = business_ontology_to_json_ld(payload)
    assert "DefinedTerm" in json_ld
    assert "business_ontology" in json_ld


def test_select_core_concepts_near_cluster_center():
    from thot.tools.search.business_ontology import select_core_concepts

    cores = select_core_concepts(
        [
            "cancer",
            "tumor",
            "neoplasm",
            "gene expression",
            "transcription",
        ],
        concept_ids=["CANCER", "TUMOR", "NEOPLASM", "GENE_EXPR", "TXN"],
        max_core=4,
        min_cluster_size=2,
    )
    assert cores
    assert all(row.get("role") == "cluster_center" for row in cores)
    assert len(cores) <= 4


def test_pick_close_docs_prefers_overlap():
    corpus = {
        "far": {"title": "", "text": "zzzz unrelated"},
        "near": {"title": "", "text": "alpha beta claim"},
        "mid": {"title": "", "text": "alpha only"},
    }
    close = pick_close_docs("alpha beta evidence", corpus, exclude=set(), n=2)
    assert close[0] == "near"
    assert "far" not in close[:1]


def test_build_smoke_subset_prefers_eval_report_focus():
    corpus = {
        f"d{i}": {"title": "", "text": f"token{i} evidence abstract text"}
        for i in range(1, 20)
    }
    queries = {
        "1": "token1 claim",
        "3": "token3 claim",
        "99": "token5 claim",
        "100": "token6 claim",
    }
    qrels = {
        "1": {"d1": 1},
        "3": {"d3": 1},
        "99": {"d5": 1},
        "100": {"d6": 1},
    }
    _subset, sq, _sr, stats = build_smoke_subset(
        corpus,
        queries,
        qrels,
        n_queries=2,
        n_close=2,
        rank_docs=3,
        seed=0,
        focus_query_ids=["3", "1", "missing"],
    )
    assert list(sq.keys()) == ["3", "1"]
    assert stats["focused_selected"] == ["3", "1"]
    assert "missing" in stats["focus_missing"]


def test_resolve_focus_query_ids_scifact_defaults():
    from thot.tools.eval.beir_smoke import resolve_focus_query_ids

    ids = resolve_focus_query_ids("scifact")
    assert ids[:3] == ["1", "3", "5"]
    assert resolve_focus_query_ids("scifact", focus_eval_report=False) == []
    assert resolve_focus_query_ids("scifact", query_ids=["42", "7"]) == [
        "42",
        "7",
    ]


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


def test_detect_timing_alerts_colbert():
    from thot.tools.eval.beir_smoke import (
        StageTimings,
        detect_timing_alerts,
    )

    timings = StageTimings(
        queries=2,
        docs_indexed=10,
        retrieve_ms=100.0,
        dual_avg_ms={"colbert": 2000.0, "vespa_arms": 50.0},
    )
    alerts = detect_timing_alerts(timings)
    assert any(a.code == "slow_stage_colbert" for a in alerts)
    assert all(a.focus for a in alerts)


def test_render_smoke_report_leads_with_focus():
    from thot.tools.eval.beir_smoke import (
        RankAlert,
        SmokeRun,
        StageTimings,
        compare_smoke_to_previous,
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

    previous = {
        "wall_s": 10.0,
        "runs": [
            {
                "name": "scifact",
                "tkeir_ndcg10": 0.5,
                "tkeir_recall10": 0.5,
                "alerts": [{"severity": "high", "code": "gold_miss_all"}],
                "timings": {"retrieve_ms": 1000.0},
            }
        ],
    }
    # Improved NDCG vs previous (even if still zero alerts on this toy run).
    improved = SmokeRun(
        name="scifact",
        queries=1,
        docs_indexed=5,
        gold_docs=1,
        close_docs=4,
        bm25=Metrics(ndcg={"NDCG@10": 0.9}),
        tkeir=Metrics(ndcg={"NDCG@10": 0.7}),
        timings=StageTimings(retrieve_ms=800.0),
        alerts=[],
    )
    comparison = compare_smoke_to_previous(
        [improved], wall_s=8.0, previous=previous
    )
    assert comparison.overall == "better"
    md2 = render_smoke_report([improved], wall_s=8.0, comparison=comparison)
    assert "## Vs previous report" in md2
    assert md2.index("Vs previous") < md2.index("Focus — problems")
    assert "**Better**" in md2 or "better" in md2.lower()


def test_compare_smoke_to_previous_verdicts():
    from thot.tools.eval.beir_smoke import (
        RankAlert,
        SmokeRun,
        StageTimings,
        compare_smoke_to_previous,
    )

    def _run(name: str, ndcg: float, high: int = 0) -> SmokeRun:
        alerts = [
            RankAlert(
                code="gold_miss_all",
                detail="x",
                severity="high",
                focus="f",
            )
        ] * high
        return SmokeRun(
            name=name,
            queries=1,
            docs_indexed=2,
            gold_docs=1,
            close_docs=1,
            bm25=Metrics(ndcg={"NDCG@10": 0.5}),
            tkeir=Metrics(ndcg={"NDCG@10": ndcg}, recall={"Recall@10": ndcg}),
            timings=StageTimings(retrieve_ms=100.0),
            alerts=alerts,
        )

    assert (
        compare_smoke_to_previous(
            [_run("scifact", 0.5)], wall_s=1.0, previous=None
        ).overall
        == "no_baseline"
    )

    previous = {
        "wall_s": 5.0,
        "runs": [
            {
                "name": "scifact",
                "tkeir_ndcg10": 0.4,
                "tkeir_recall10": 0.4,
                "alerts": [{"severity": "high", "code": "a"}],
                "timings": {"retrieve_ms": 200.0},
            },
            {
                "name": "fiqa",
                "tkeir_ndcg10": 0.6,
                "tkeir_recall10": 0.6,
                "alerts": [],
                "timings": {"retrieve_ms": 200.0},
            },
        ],
    }
    better = compare_smoke_to_previous(
        [_run("scifact", 0.55), _run("fiqa", 0.65)],
        wall_s=4.0,
        previous=previous,
    )
    assert better.overall == "better"

    worse = compare_smoke_to_previous(
        [_run("scifact", 0.2, high=2), _run("fiqa", 0.4)],
        wall_s=6.0,
        previous=previous,
    )
    assert worse.overall == "worse"

    mixed = compare_smoke_to_previous(
        [_run("scifact", 0.7), _run("fiqa", 0.3)],
        wall_s=5.0,
        previous=previous,
    )
    assert mixed.overall == "mixed"
