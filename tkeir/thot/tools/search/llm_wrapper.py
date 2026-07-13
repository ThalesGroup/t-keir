# -*- coding: utf-8 -*-
"""Backward-compatible re-exports for :mod:`thot.core.LlmWrapper`."""

from thot.core.LlmWrapper import (
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODELS,
    DEFAULT_LLM_MODELS,
    EmbeddingClient,
    LLMClient,
    Provider,
    UnifiedLLMWrapper,
    WrapperConfig,
    _normalize_embedding,
)

__all__ = [
    "DEFAULT_EMBEDDING_DIM",
    "DEFAULT_EMBEDDING_MODELS",
    "DEFAULT_LLM_MODELS",
    "EmbeddingClient",
    "LLMClient",
    "Provider",
    "UnifiedLLMWrapper",
    "WrapperConfig",
    "_normalize_embedding",
]
