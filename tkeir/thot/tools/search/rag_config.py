# -*- coding: utf-8 -*-
"""Load RAG API runtime configuration from ``configs/rag.yaml``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from thot.core.KeywordRules import DEFAULT_MIN_KEYWORD_LENGTH
from thot.core.TkeirPaths import rag_config_path

_DEFAULT_MIN_KEYWORD_LENGTH = DEFAULT_MIN_KEYWORD_LENGTH
_DEFAULT_MAX_ENTITIES = 120
_DEFAULT_MAX_KEYWORDS = 60
_DEFAULT_CHUNK_CONTEXT_MODE = "chunk_excerpts"
_DEFAULT_MAX_SVO_TRIPLES = 80
_ALLOWED_CHUNK_CONTEXT_MODES = frozenset({"chunk_excerpts", "svo_ontology"})


@dataclass(frozen=True)
class RagSearchConfig:
    """Hybrid Vespa retrieval settings for query analysis."""

    enabled: bool = False
    use_chunk_embedding: bool = True
    use_question_embedding: bool = True
    use_text_raw: bool = True
    use_parent_content: bool = True
    use_parent_title: bool = True
    use_ner: bool = True
    use_svo: bool = True
    use_keywords: bool = True
    use_lemmas: bool = True
    ranking_profile: str = "hybrid_2_level"
    hits: int = 20
    max_yql_terms: int = 32
    weight_chunk_embedding: float = 0.30
    weight_question_embedding: float = 0.10
    weight_text_raw_bm25: float = 0.40
    weight_parent_content_bm25: float = 0.20
    weight_parent_title_bm25: float = 0.15


@dataclass(frozen=True)
class RagPromptConfig:
    """Prompt assembly settings for RAG answer generation."""

    chunk_context_mode: str
    max_svo_triples: int


@dataclass(frozen=True)
class RagOntologyConfig:
    """Ontology export settings for the RAG HMI."""

    min_keyword_length: int
    max_entities: int
    max_keywords: int


@dataclass(frozen=True)
class RagConfig:
    """Runtime configuration for the Vespa RAG API."""

    ontology: RagOntologyConfig
    prompt: RagPromptConfig
    search: RagSearchConfig


def _normalize_chunk_context_mode(value: object) -> str:
    """Normalize prompt chunk-context mode to a supported value.

    Example:
        >>> from thot.tools.search.rag_config import _normalize_chunk_context_mode
        >>> _normalize_chunk_context_mode("svo_ontology")
        'svo_ontology'
    """
    mode = str(value or _DEFAULT_CHUNK_CONTEXT_MODE).strip()
    if mode not in _ALLOWED_CHUNK_CONTEXT_MODES:
        return _DEFAULT_CHUNK_CONTEXT_MODE
    return mode


def _as_bool(value: object, default: bool) -> bool:
    """Coerce YAML or CLI values into booleans.

    Example:
        >>> from thot.tools.search.rag_config import _as_bool
        >>> _as_bool("yes", False)
        True
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _search_config_from_mapping(
    mapping: dict[str, Any] | None,
) -> RagSearchConfig:
    """Build :class:`RagSearchConfig` from a YAML mapping.

    Example:
        >>> from thot.tools.search.rag_config import _search_config_from_mapping
        >>> _search_config_from_mapping({"enabled": True}).enabled
        True
    """
    cfg = mapping or {}
    if not isinstance(cfg, dict):
        cfg = {}
    return RagSearchConfig(
        enabled=_as_bool(cfg.get("enabled"), False),
        use_chunk_embedding=_as_bool(cfg.get("use_chunk_embedding"), True),
        use_question_embedding=_as_bool(
            cfg.get("use_question_embedding"), True
        ),
        use_text_raw=_as_bool(cfg.get("use_text_raw"), True),
        use_parent_content=_as_bool(cfg.get("use_parent_content"), True),
        use_parent_title=_as_bool(cfg.get("use_parent_title"), True),
        use_ner=_as_bool(cfg.get("use_ner"), True),
        use_svo=_as_bool(cfg.get("use_svo"), True),
        use_keywords=_as_bool(cfg.get("use_keywords"), True),
        use_lemmas=_as_bool(cfg.get("use_lemmas"), True),
        ranking_profile=str(cfg.get("ranking_profile", "hybrid_2_level")),
        hits=max(1, int(cfg.get("hits", 20))),
        max_yql_terms=max(1, int(cfg.get("max_yql_terms", 32))),
        weight_chunk_embedding=float(cfg.get("weight_chunk_embedding", 0.30)),
        weight_question_embedding=float(
            cfg.get("weight_question_embedding", 0.10)
        ),
        weight_text_raw_bm25=float(cfg.get("weight_text_raw_bm25", 0.40)),
        weight_parent_content_bm25=float(
            cfg.get("weight_parent_content_bm25", 0.20)
        ),
        weight_parent_title_bm25=float(
            cfg.get("weight_parent_title_bm25", 0.15)
        ),
    )


def load_rag_config() -> RagConfig:
    """Load RAG settings from ``configs/rag.yaml``.

    Returns:
        Parsed configuration with defaults for missing keys.

    Example:
        >>> from thot.tools.search.rag_config import load_rag_config
        >>> load_rag_config().ontology.min_keyword_length >= 1
        True
    """
    with open(rag_config_path(), encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    ontology_cfg = payload.get("ontology") or {}
    if not isinstance(ontology_cfg, dict):
        ontology_cfg = {}

    min_keyword_length = int(
        ontology_cfg.get("min_keyword_length", _DEFAULT_MIN_KEYWORD_LENGTH)
    )
    max_entities = int(ontology_cfg.get("max_entities", _DEFAULT_MAX_ENTITIES))
    max_keywords = int(ontology_cfg.get("max_keywords", _DEFAULT_MAX_KEYWORDS))

    prompt_cfg = payload.get("prompt") or {}
    if not isinstance(prompt_cfg, dict):
        prompt_cfg = {}

    search_cfg = payload.get("search") or {}
    if not isinstance(search_cfg, dict):
        search_cfg = {}

    return RagConfig(
        ontology=RagOntologyConfig(
            min_keyword_length=max(1, min_keyword_length),
            max_entities=max(1, max_entities),
            max_keywords=max(1, max_keywords),
        ),
        prompt=RagPromptConfig(
            chunk_context_mode=_normalize_chunk_context_mode(
                prompt_cfg.get("chunk_context_mode")
            ),
            max_svo_triples=max(
                1,
                int(
                    prompt_cfg.get("max_svo_triples", _DEFAULT_MAX_SVO_TRIPLES)
                ),
            ),
        ),
        search=_search_config_from_mapping(search_cfg),
    )


def ontology_settings_from_mapping(
    mapping: dict[str, Any] | RagOntologyConfig | None,
) -> RagOntologyConfig:
    """Normalize ontology settings from a config mapping or dataclass.

    Example:
        >>> ontology_settings_from_mapping({"min_keyword_length": 4}).min_keyword_length
        4
    """
    if isinstance(mapping, RagOntologyConfig):
        return mapping
    if not isinstance(mapping, dict):
        return load_rag_config().ontology
    return RagOntologyConfig(
        min_keyword_length=max(
            1,
            int(
                mapping.get("min_keyword_length", _DEFAULT_MIN_KEYWORD_LENGTH)
            ),
        ),
        max_entities=max(
            1,
            int(mapping.get("max_entities", _DEFAULT_MAX_ENTITIES)),
        ),
        max_keywords=max(
            1,
            int(mapping.get("max_keywords", _DEFAULT_MAX_KEYWORDS)),
        ),
    )
