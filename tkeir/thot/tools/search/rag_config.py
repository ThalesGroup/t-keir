"""Title: Rag config

Load RAG API runtime configuration from ``configs/rag.yaml``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from thot.core.KeywordRules import DEFAULT_MIN_KEYWORD_LENGTH
from thot.core.TkeirPaths import rag_config_path
from thot.tools.search.dual_hybrid_config import (
    DualHybridConfig,
    dual_hybrid_from_mapping,
)

_DEFAULT_MIN_KEYWORD_LENGTH = DEFAULT_MIN_KEYWORD_LENGTH
_DEFAULT_MAX_ENTITIES = 120
_DEFAULT_MAX_KEYWORDS = 60
_DEFAULT_CHUNK_CONTEXT_MODE = "chunk_excerpts"
_DEFAULT_MAX_SVO_TRIPLES = 80
_DEFAULT_PASSAGE_COUNT = 3
_DEFAULT_PASSAGE_MAX_CHARS = 1800
_DEFAULT_PASSAGE_CONTEXT_SENTENCES = 2
_DEFAULT_MAX_CHARS_PER_CHUNK = 1800
_DEFAULT_MAX_CHUNKS_FOR_PROMPT = 6
# Legacy flat YAML keys (still supported).
_DEFAULT_MAX_FOCUS_PASSAGES = _DEFAULT_PASSAGE_COUNT
_DEFAULT_MAX_CHARS_PER_PASSAGE = _DEFAULT_PASSAGE_MAX_CHARS
_DEFAULT_FOCUS_CONTEXT_SENTENCES = _DEFAULT_PASSAGE_CONTEXT_SENTENCES
_ALLOWED_CHUNK_CONTEXT_MODES = frozenset({"chunk_excerpts", "svo_ontology"})
_DEFAULT_RERANK_ENABLED = True
_DEFAULT_RERANK_CANDIDATES = 50
_DEFAULT_RERANK_STRATEGY = "embedding_cosine"
_ALLOWED_RERANK_STRATEGIES = frozenset({"cross_encoder", "embedding_cosine"})
_FORBIDDEN_LLM_RERANK_STRATEGIES = frozenset(
    {
        "llm",
        "llm_judge",
        "llm_rerank",
        "generate",
        "generation",
        "chat",
        "prompt",
    }
)
_DEFAULT_VESPA_URL = "http://localhost:8080"
_DEFAULT_VESPA_CONFIG_URL = "http://localhost:19071"
_DEFAULT_VESPA_TIMEOUT_SECONDS = 60.0
_DEFAULT_ENRICH_WORKERS = 8


@dataclass(frozen=True)
class RagVespaConcurrency:
    """Worker pools for hit enrichment after search."""

    enrich_workers: int = _DEFAULT_ENRICH_WORKERS


@dataclass(frozen=True)
class RagVespaConfig:
    """Vespa endpoints, timeouts, and concurrency for search/index."""

    url: str = _DEFAULT_VESPA_URL
    config_url: str = _DEFAULT_VESPA_CONFIG_URL
    timeout_seconds: float = _DEFAULT_VESPA_TIMEOUT_SECONDS
    # Streaming group. Keycloak JWT drives the live value; this is the
    # auth-off / CLI fallback (dev@tkeir). Override with VESPA_USER_SPACE.
    user_space: str = "dev@tkeir"
    concurrency: RagVespaConcurrency = RagVespaConcurrency()


@dataclass(frozen=True)
class RagModelsConfig:
    """Model names for search / index (overridden by env vars when set)."""

    provider: str | None = None
    embedding_model: str | None = None
    llm_model: str | None = None
    reranker_model: str | None = None
    embedding_dim: int | None = None


@dataclass(frozen=True)
class RagRerankConfig:
    """Second-stage rerank after Vespa hybrid retrieval."""

    enabled: bool = _DEFAULT_RERANK_ENABLED
    candidates: int = _DEFAULT_RERANK_CANDIDATES
    strategy: str = _DEFAULT_RERANK_STRATEGY


@dataclass(frozen=True)
class RagSearchConfig:
    """Hybrid Vespa retrieval settings for query analysis."""

    enabled: bool = False
    use_chunk_embedding: bool = True
    use_text_raw: bool = True
    use_ner: bool = True
    use_svo: bool = True
    use_keywords: bool = True
    use_lemmas: bool = True
    ranking_profile: str = "auto"
    hits: int = 20
    max_yql_terms: int = 48
    weight_chunk_embedding: float = 0.38
    weight_text_raw_bm25: float = 0.28
    rerank: RagRerankConfig = RagRerankConfig()


@dataclass(frozen=True)
class RagPassageConfig:
    """KEY PASSAGE sizing for LLM prompt generation."""

    count: int = _DEFAULT_PASSAGE_COUNT
    max_chars: int = _DEFAULT_PASSAGE_MAX_CHARS
    context_sentences: int = _DEFAULT_PASSAGE_CONTEXT_SENTENCES


@dataclass(frozen=True)
class RagPromptConfig:
    """Prompt assembly settings for RAG answer generation."""

    chunk_context_mode: str
    max_svo_triples: int
    passages: RagPassageConfig = RagPassageConfig()
    max_chars_per_chunk: int = _DEFAULT_MAX_CHARS_PER_CHUNK
    max_chunks_for_prompt: int = _DEFAULT_MAX_CHUNKS_FOR_PROMPT

    @property
    def max_focus_passages(self) -> int:
        """Backward-compatible alias for :attr:`passages.count`.

        Example:
            >>> RagPromptConfig(
            ...     chunk_context_mode="svo_ontology",
            ...     max_svo_triples=10,
            ...     passages=RagPassageConfig(count=7),
            ... ).max_focus_passages
            7
        """
        return self.passages.count

    @property
    def max_chars_per_passage(self) -> int:
        """Backward-compatible alias for :attr:`passages.max_chars`.

        Example:
            >>> RagPromptConfig(
            ...     chunk_context_mode="svo_ontology",
            ...     max_svo_triples=10,
            ...     passages=RagPassageConfig(max_chars=900),
            ... ).max_chars_per_passage
            900
        """
        return self.passages.max_chars

    @property
    def focus_context_sentences(self) -> int:
        """Backward-compatible alias for :attr:`passages.context_sentences`.

        Example:
            >>> RagPromptConfig(
            ...     chunk_context_mode="svo_ontology",
            ...     max_svo_triples=10,
            ...     passages=RagPassageConfig(context_sentences=3),
            ... ).focus_context_sentences
            3
        """
        return self.passages.context_sentences


@dataclass(frozen=True)
class RagOntologyConfig:
    """Ontology export settings for the RAG HMI."""

    min_keyword_length: int
    max_entities: int
    max_keywords: int


@dataclass(frozen=True)
class RagAnswerGenerationConfig:
    """QA answer-generation toggles (generate-eval + prompt assembly)."""

    use_nlp: bool = True
    use_ontology: bool = True
    use_reasoner: bool = True


@dataclass(frozen=True)
class RagConfig:
    """Runtime configuration for the Vespa RAG API."""

    ontology: RagOntologyConfig
    prompt: RagPromptConfig
    search: RagSearchConfig
    models: RagModelsConfig = RagModelsConfig()
    vespa: RagVespaConfig = RagVespaConfig()
    dual_hybrid: DualHybridConfig = DualHybridConfig()
    answer_generation: RagAnswerGenerationConfig = RagAnswerGenerationConfig()


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


def _passage_config_from_mapping(
    prompt_cfg: dict[str, Any],
) -> RagPassageConfig:
    """Build passage sizing from ``prompt.passages`` or legacy flat keys.

    Example:
        >>> cfg = _passage_config_from_mapping(
        ...     {"passages": {"count": 5, "max_chars": 2400, "context_sentences": 1}}
        ... )
        >>> (cfg.count, cfg.max_chars, cfg.context_sentences)
        (5, 2400, 1)
    """
    passages = prompt_cfg.get("passages") or {}
    if not isinstance(passages, dict):
        passages = {}

    count = passages.get("count", prompt_cfg.get("max_focus_passages"))
    max_chars = passages.get(
        "max_chars", prompt_cfg.get("max_chars_per_passage")
    )
    context_sentences = passages.get(
        "context_sentences", prompt_cfg.get("focus_context_sentences")
    )
    if context_sentences is None:
        context_sentences = _DEFAULT_PASSAGE_CONTEXT_SENTENCES
    if count is None:
        count = _DEFAULT_PASSAGE_COUNT
    if max_chars is None:
        max_chars = _DEFAULT_PASSAGE_MAX_CHARS

    return RagPassageConfig(
        count=max(1, int(count)),
        max_chars=max(200, int(max_chars)),
        context_sentences=max(0, int(context_sentences)),
    )


def resolve_passage_settings(
    *,
    defaults: RagPassageConfig,
    count: int | None = None,
    max_chars: int | None = None,
    context_sentences: int | None = None,
) -> RagPassageConfig:
    """Merge per-request passage overrides with config defaults.

    Example:
        >>> base = RagPassageConfig(count=3, max_chars=1800, context_sentences=2)
        >>> resolved = resolve_passage_settings(defaults=base, count=5)
        >>> resolved.count
        5
    """
    return RagPassageConfig(
        count=max(1, int(count if count is not None else defaults.count)),
        max_chars=max(
            200,
            int(max_chars if max_chars is not None else defaults.max_chars),
        ),
        context_sentences=max(
            0,
            int(
                context_sentences
                if context_sentences is not None
                else defaults.context_sentences
            ),
        ),
    )


def _rerank_config_from_mapping(
    mapping: dict[str, Any] | None,
) -> RagRerankConfig:
    """Build :class:`RagRerankConfig` from ``search.rerank`` YAML.

    Allowed strategies: ``cross_encoder`` (opt-in via ``RERANKER_MODEL``),
    ``embedding_cosine``. LLM / generative aliases fall back to
    ``embedding_cosine``. Production dual-hybrid uses BGE-M3 ColBERT instead.

    Example:
        >>> _rerank_config_from_mapping(
        ...     {"enabled": False, "candidates": 20, "strategy": "embedding_cosine"}
        ... )
        RagRerankConfig(enabled=False, candidates=20, strategy='embedding_cosine')
    """
    cfg = mapping if isinstance(mapping, dict) else {}
    strategy = (
        str(cfg.get("strategy", _DEFAULT_RERANK_STRATEGY)).strip().lower()
    )
    if (
        strategy in _FORBIDDEN_LLM_RERANK_STRATEGIES
        or strategy not in _ALLOWED_RERANK_STRATEGIES
    ):
        strategy = _DEFAULT_RERANK_STRATEGY
    return RagRerankConfig(
        enabled=_as_bool(cfg.get("enabled"), _DEFAULT_RERANK_ENABLED),
        candidates=max(
            1, int(cfg.get("candidates", _DEFAULT_RERANK_CANDIDATES))
        ),
        strategy=strategy,
    )


def _vespa_config_from_mapping(
    mapping: dict[str, Any] | None,
) -> RagVespaConfig:
    """Build :class:`RagVespaConfig` from the top-level ``vespa`` YAML.

    Example:
        >>> cfg = _vespa_config_from_mapping(
        ...     {"url": "http://vespa:8080", "concurrency": {"enrich_workers": 4}}
        ... )
        >>> cfg.url
        'http://vespa:8080'
        >>> cfg.concurrency.enrich_workers
        4
    """
    cfg = mapping if isinstance(mapping, dict) else {}
    concurrency_raw = cfg.get("concurrency") or {}
    if not isinstance(concurrency_raw, dict):
        concurrency_raw = {}
    return RagVespaConfig(
        url=str(cfg.get("url") or _DEFAULT_VESPA_URL).rstrip("/"),
        config_url=str(
            cfg.get("config_url") or _DEFAULT_VESPA_CONFIG_URL
        ).rstrip("/"),
        timeout_seconds=max(
            1.0,
            float(cfg.get("timeout_seconds", _DEFAULT_VESPA_TIMEOUT_SECONDS)),
        ),
        user_space=str(cfg.get("user_space") or "dev@tkeir").strip()
        or "dev@tkeir",
        concurrency=RagVespaConcurrency(
            enrich_workers=max(
                1,
                int(
                    concurrency_raw.get(
                        "enrich_workers", _DEFAULT_ENRICH_WORKERS
                    )
                ),
            ),
        ),
    )


def _models_config_from_mapping(
    mapping: dict[str, Any] | None,
) -> RagModelsConfig:
    """Build :class:`RagModelsConfig` from the top-level ``models`` YAML.

    Example:
        >>> _models_config_from_mapping({"embedding_model": "bge-m3"}).embedding_model
        'bge-m3'
    """
    cfg = mapping if isinstance(mapping, dict) else {}
    dim_raw = cfg.get("embedding_dim")
    embedding_dim = int(dim_raw) if dim_raw is not None else None
    return RagModelsConfig(
        provider=(
            str(cfg["provider"]).strip()
            if cfg.get("provider") not in (None, "")
            else None
        ),
        embedding_model=(
            str(cfg["embedding_model"]).strip()
            if cfg.get("embedding_model") not in (None, "")
            else None
        ),
        llm_model=(
            str(cfg["llm_model"]).strip()
            if cfg.get("llm_model") not in (None, "")
            else None
        ),
        reranker_model=(
            str(cfg["reranker_model"]).strip()
            if cfg.get("reranker_model") not in (None, "")
            else None
        ),
        embedding_dim=embedding_dim,
    )


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
        use_text_raw=_as_bool(cfg.get("use_text_raw"), True),
        use_ner=_as_bool(cfg.get("use_ner"), True),
        use_svo=_as_bool(cfg.get("use_svo"), True),
        use_keywords=_as_bool(cfg.get("use_keywords"), True),
        use_lemmas=_as_bool(cfg.get("use_lemmas"), True),
        ranking_profile=str(cfg.get("ranking_profile", "auto")),
        hits=max(1, int(cfg.get("hits", 20))),
        max_yql_terms=max(1, int(cfg.get("max_yql_terms", 32))),
        weight_chunk_embedding=float(cfg.get("weight_chunk_embedding", 0.30)),
        weight_text_raw_bm25=float(cfg.get("weight_text_raw_bm25", 0.40)),
        rerank=_rerank_config_from_mapping(cfg.get("rerank")),
    )


def _answer_generation_config_from_mapping(
    mapping: dict[str, Any] | None,
) -> RagAnswerGenerationConfig:
    """Build :class:`RagAnswerGenerationConfig` from YAML.

    Example:
        >>> _answer_generation_config_from_mapping({"use_nlp": False}).use_nlp
        False
    """
    cfg = mapping if isinstance(mapping, dict) else {}
    return RagAnswerGenerationConfig(
        use_nlp=_as_bool(cfg.get("use_nlp"), True),
        use_ontology=_as_bool(cfg.get("use_ontology"), True),
        use_reasoner=_as_bool(cfg.get("use_reasoner"), True),
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

    models_cfg = payload.get("models") or {}
    if not isinstance(models_cfg, dict):
        models_cfg = {}

    vespa_cfg = payload.get("vespa") or {}
    if not isinstance(vespa_cfg, dict):
        vespa_cfg = {}

    dual_cfg = payload.get("dual_hybrid") or {}
    if not isinstance(dual_cfg, dict):
        dual_cfg = {}

    answer_cfg = payload.get("answer_generation") or {}
    if not isinstance(answer_cfg, dict):
        answer_cfg = {}

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
            passages=_passage_config_from_mapping(prompt_cfg),
            max_chars_per_chunk=max(
                200,
                int(
                    prompt_cfg.get(
                        "max_chars_per_chunk", _DEFAULT_MAX_CHARS_PER_CHUNK
                    )
                ),
            ),
            max_chunks_for_prompt=max(
                1,
                int(
                    prompt_cfg.get(
                        "max_chunks_for_prompt", _DEFAULT_MAX_CHUNKS_FOR_PROMPT
                    )
                ),
            ),
        ),
        search=_search_config_from_mapping(search_cfg),
        models=_models_config_from_mapping(models_cfg),
        vespa=_vespa_config_from_mapping(vespa_cfg),
        dual_hybrid=dual_hybrid_from_mapping(dual_cfg),
        answer_generation=_answer_generation_config_from_mapping(answer_cfg),
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
