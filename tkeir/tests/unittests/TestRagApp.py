# -*- coding: utf-8 -*-
"""Tests for RAG prompt configuration helpers."""

from thot.tools.search.app import (
    _build_generation_prompts,
    _language_prompt_cfg,
    _load_prompts,
    _no_chunks_message,
    _resolve_system_prompt_template,
    _resolve_user_prompt_template,
    _unavailable_answer,
)
from thot.tools.search.rag_config import RagPromptConfig


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
        query_analysis="- Lexical search query: Rob Brown",
        generation_guidance="MODE DE GÉNÉRATION : réponse directe",
        unavailable_answer=unavailable,
    )
    assert unavailable in system_prompt
    assert unavailable in user_prompt
    assert "Passages" in user_prompt
    assert _no_chunks_message(fr_cfg).startswith("Aucun")


def test_resolve_user_prompt_template_uses_compact_svo_variant():
    prompts = _load_prompts()
    en_cfg = _language_prompt_cfg(prompts, "en")
    svo_template = _resolve_user_prompt_template(
        en_cfg,
        RagPromptConfig("svo_ontology", 80),
    )
    default_template = _resolve_user_prompt_template(
        en_cfg,
        RagPromptConfig("chunk_excerpts", 80),
    )
    assert "STRUCTURED FACTS" in svo_template
    assert "KEY PASSAGES" in svo_template
    assert (
        "SEARCH QUERY ANALYSIS" not in default_template
        or "GLOBAL CONTEXT" in default_template
        or "### GLOBAL CONTEXT" in default_template
    )
    assert (
        "KEY PASSAGES" not in default_template
        or "### KEY PASSAGES" in default_template
    )
    assert "GLOBAL CONTEXT" not in svo_template
    assert "SEARCH QUERY ANALYSIS" in default_template
    assert (
        "RELEVANT TEXT EXCERPTS" in default_template
        or "### RELEVANT TEXT EXCERPTS" in default_template
    )
    system_svo = _resolve_system_prompt_template(
        en_cfg,
        RagPromptConfig("svo_ontology", 80),
    )
    assert system_svo is not None
    assert "KEY PASSAGES" in system_svo


def test_pipeline_runner_for_language_falls_back_to_english():
    from thot.tools.search.app import AppState, _pipeline_runner_for_language

    state = AppState()
    sentinel = object()
    state.pipeline_runners = {"en": sentinel}
    assert _pipeline_runner_for_language(state, "fr") is sentinel
    assert _pipeline_runner_for_language(state, "en") is sentinel
