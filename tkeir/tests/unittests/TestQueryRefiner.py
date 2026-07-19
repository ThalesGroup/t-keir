"""Tests for RAG query refinement helpers."""

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
