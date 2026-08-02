"""Title: Query Refiner

Tests for RAG query refinement helpers.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.tools.search.query_refiner import meaningful_tokens_from_morphosyntax


def test_meaningful_tokens_from_morphosyntax_drops_stopwords():
    morphosyntax = [
        {"text": "Who", "pos": "PRON"},
        {"text": "report", "pos": "VERB"},
        {"text": "Yang", "pos": "PROPN"},
        {"text": "had", "pos": "AUX"},
        {"text": "replace", "pos": "VERB"},
        {"text": "Donald", "pos": "PROPN"},
        {"text": "Trump", "pos": "PROPN"},
        {"text": "?", "pos": "PUNCT"},
    ]
    assert meaningful_tokens_from_morphosyntax(morphosyntax) == [
        "report",
        "Yang",
        "replace",
        "Donald",
        "Trump",
    ]


def test_meaningful_tokens_from_morphosyntax_deduplicates():
    morphosyntax = [
        {"text": "the", "pos": "DET"},
        {"text": "the", "pos": "DET"},
        {"text": "song", "pos": "NOUN"},
        {"text": "song", "pos": "NOUN"},
    ]
    assert meaningful_tokens_from_morphosyntax(morphosyntax) == ["song"]


def test_meaningful_tokens_from_morphosyntax_empty():
    assert meaningful_tokens_from_morphosyntax([]) == []


def test_content_terms_from_morphosyntax_is_language_agnostic():
    from thot.tools.search.query_analyzer import (
        content_terms_for_grounding,
        content_terms_from_morphosyntax,
    )

    morph_fr = [
        {"text": "Le", "lemma": "le", "pos": "DET"},
        {"text": "canal", "lemma": "canal", "pos": "NOUN"},
        {"text": "de", "lemma": "de", "pos": "ADP"},
        {"text": "Suez", "lemma": "Suez", "pos": "PROPN"},
    ]
    terms = content_terms_from_morphosyntax(morph_fr)
    assert "canal" in terms
    assert "suez" in terms
    assert "le" not in terms
    assert "de" not in terms

    grounded = content_terms_for_grounding(
        "Le canal de Suez",
        morphosyntax=morph_fr,
    )
    assert grounded == terms
