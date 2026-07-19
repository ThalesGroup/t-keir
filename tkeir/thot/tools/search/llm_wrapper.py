"""Backward-compatible re-exports for :mod:`thot.core.LlmWrapper`."""

from thot.core.LlmWrapper import (
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODELS,
    DEFAULT_LLM_MODELS,
    DEFAULT_RERANK_STRATEGY,
    DEFAULT_RERANKER_MODEL,
    DEFAULT_RERANKER_MODELS,
    EmbeddingClient,
    LLMClient,
    Provider,
    RerankStrategy,
    UnifiedLLMWrapper,
    WrapperConfig,
    _normalize_embedding,
)

__all__ = [
    "DEFAULT_EMBEDDING_DIM",
    "DEFAULT_EMBEDDING_MODELS",
    "DEFAULT_LLM_MODELS",
    "DEFAULT_RERANKER_MODEL",
    "DEFAULT_RERANKER_MODELS",
    "DEFAULT_RERANK_STRATEGY",
    "EmbeddingClient",
    "LLMClient",
    "Provider",
    "RerankStrategy",
    "UnifiedLLMWrapper",
    "WrapperConfig",
    "_normalize_embedding",
]
