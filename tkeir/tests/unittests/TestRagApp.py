# -*- coding: utf-8 -*-
"""Tests for RAG prompt configuration helpers."""

from thot.tools.search.app import (
    _build_generation_prompts,
    _language_prompt_cfg,
    _load_prompts,
    _no_chunks_message,
    _unavailable_answer,
)


def test_unavailable_answer_is_language_specific():
    prompts = _load_prompts()
    en_cfg = _language_prompt_cfg(prompts, "en")
    fr_cfg = _language_prompt_cfg(prompts, "fr")
    assert (
        _unavailable_answer(en_cfg, "en")
        == "The information is not available."
    )
    assert (
        _unavailable_answer(fr_cfg, "fr")
        == "L'information n'est pas disponible."
    )


def test_generation_prompts_inject_unavailable_answer():
    prompts = _load_prompts()
    fr_cfg = _language_prompt_cfg(prompts, "fr")
    unavailable = _unavailable_answer(fr_cfg, "fr")
    system_prompt, user_prompt = _build_generation_prompts(
        fr_cfg,
        fused_summary="Faits",
        focus_passages="Passages",
        chunk_excerpts="Extraits",
        query_text="Qui est Rob Brown ?",
        unavailable_answer=unavailable,
    )
    assert unavailable in system_prompt
    assert unavailable in user_prompt
    assert "Passages" in user_prompt
    assert _no_chunks_message(fr_cfg).startswith("Aucun")


def test_pipeline_runner_for_language_falls_back_to_english():
    from thot.tools.search.app import AppState, _pipeline_runner_for_language

    state = AppState()
    sentinel = object()
    state.pipeline_runners = {"en": sentinel}
    assert _pipeline_runner_for_language(state, "fr") is sentinel
    assert _pipeline_runner_for_language(state, "en") is sentinel
