# -*- coding: utf-8 -*-
"""Tests for Vespa feed helpers."""

from thot.tools.search.vespa_client import (
    build_chunk_tensor,
    build_questions_tensor,
    build_text_raw_contains_or_clause,
    chunk_embedding_text,
    escape_yql_literal,
    sanitize_vespa_string,
    strip_search_vector_payload,
)


def test_sanitize_vespa_string_removes_form_feed():
    assert sanitize_vespa_string("hello\fworld") == "hello world"


def test_build_chunk_tensor_returns_plain_vector():
    assert build_chunk_tensor([1.0, 2.0, 3.0], embedding_dim=3) == [
        1.0,
        2.0,
        3.0,
    ]


def test_build_questions_tensor_uses_mapped_keys():
    tensor = build_questions_tensor([[0.1, 0.2], [0.3, 0.4]], embedding_dim=2)
    assert tensor == {"0": [0.1, 0.2], "1": [0.3, 0.4]}


def test_strip_search_vector_payload_removes_context_tags():
    payload = (
        "[CONTEXT_BEFORE] Previous topic: Acme Corp "
        "It targets enterprise customers "
        "[CONTEXT_AFTER] Next focus: Microsoft responded quickly"
    )
    assert strip_search_vector_payload(payload) == (
        "Previous topic: Acme Corp It targets enterprise customers "
        "Next focus: Microsoft responded quickly"
    )


def test_chunk_embedding_text_prefers_search_vector_payload():
    chunk = {
        "text_raw": "Core chunk text",
        "search_vector_payload": (
            "[CONTEXT_BEFORE] before summary Core chunk text "
            "[CONTEXT_AFTER] after summary"
        ),
    }
    assert chunk_embedding_text(chunk) == (
        "before summary Core chunk text after summary"
    )


def test_build_text_raw_contains_or_clause_single_term():
    assert (
        build_text_raw_contains_or_clause("Yang") == 'text_raw contains "Yang"'
    )


def test_build_text_raw_contains_or_clause_multiple_terms():
    assert build_text_raw_contains_or_clause("Michael Chang") == (
        '(text_raw contains "Michael" OR text_raw contains "Chang")'
    )


def test_build_text_raw_contains_or_clause_escapes_quotes():
    assert build_text_raw_contains_or_clause('say "hi"') == (
        '(text_raw contains "say" OR text_raw contains "\\"hi\\"")'
    )


def test_build_text_raw_contains_or_clause_empty():
    assert build_text_raw_contains_or_clause("") is None
    assert build_text_raw_contains_or_clause("   ") is None


def test_build_text_raw_contains_or_clause_deduplicates_terms():
    assert build_text_raw_contains_or_clause("the the song") == (
        '(text_raw contains "the" OR text_raw contains "song")'
    )


def test_escape_yql_literal():
    assert escape_yql_literal('say "hello"') == 'say \\"hello\\"'
