"""Title: Passage BM25 probe content terms

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.tools.search.passage_retrieval import (
    PassageHit,
    _boost_hits_by_content_overlap,
    _content_probe_terms,
)


def test_content_probe_terms_drop_interrogative_pronoun():
    terms = _content_probe_terms(
        "What happen at Suez",
        {
            "search_terms": ["Suez", "What", "happen at", "happen"],
            "ner_entities": [{"text": "Suez", "label": "LOC"}],
            "morphosyntax": [
                {"text": "What", "lemma": "what", "pos": "PRON"},
                {"text": "happen", "lemma": "happen", "pos": "VERB"},
                {"text": "at", "lemma": "at", "pos": "ADP"},
                {"text": "Suez", "lemma": "Suez", "pos": "PROPN"},
            ],
        },
        ["Suez", "What", "happen at", "happen"],
    )
    assert "Suez" in terms
    assert "happen" in terms
    assert not any(term.casefold() == "what" for term in terms)


def test_build_search_terms_drops_svo_interrogative_subject():
    from thot.tools.search.query_analyzer import (
        NerEntity,
        QueryAnalysis,
        SvoTriple,
        build_search_terms,
    )
    from thot.tools.search.rag_config import RagSearchConfig

    analysis = QueryAnalysis(
        raw_query="What happen at Suez",
        language="en",
        ner_entities=[NerEntity("Suez", "location")],
        svo_triples=[SvoTriple(subject="What", verb="happen at", object="")],
        lemmas=["happen", "Suez"],
        morphosyntax=[
            {"text": "What", "lemma": "what", "pos": "PRON"},
            {"text": "happen", "lemma": "happen", "pos": "VERB"},
            {"text": "at", "lemma": "at", "pos": "ADP"},
            {"text": "Suez", "lemma": "Suez", "pos": "PROPN"},
        ],
    )
    terms = build_search_terms(analysis, RagSearchConfig())
    assert "Suez" in terms
    assert not any(term.casefold() == "what" for term in terms)


def test_content_probe_without_nlp_keeps_phrase_not_split_tokens():
    terms = _content_probe_terms("What happen at Suez", None, [])
    assert terms == ["What happen at Suez"]


def test_boost_prefers_entity_overlap():
    hits = [
        PassageHit(
            "a",
            "a",
            "Source observed what appeared to be a fixed-wing UAV near Gaza",
            0.95,
            "global",
        ),
        PassageHit(
            "b",
            "b",
            "Cautious calm around Suez Gulf Approach after maritime reports",
            0.40,
            "global",
        ),
    ]
    boosted = _boost_hits_by_content_overlap(hits, ["Suez"])
    assert boosted[0].passage_id == "b"


def test_extract_focus_passages_accepts_single_entity_term():
    from thot.tools.search.ontology_utils import extract_focus_passages

    text = (
        "Unrelated filler about weather. "
        "Unverified reports of an explosion heard near Suez Gulf Approach. "
        "More unrelated filler."
    )
    passages = extract_focus_passages(
        [("c1", text)],
        "What happen at Suez",
        context_sentences=0,
        analysis={
            "search_terms": ["Suez", "happen"],
            "lemmas": ["Suez", "happen"],
        },
    )
    assert "Suez" in passages
    assert "explosion" in passages.lower() or "Suez Gulf" in passages
