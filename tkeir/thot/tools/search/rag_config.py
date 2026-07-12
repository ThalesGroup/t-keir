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

    return RagConfig(
        ontology=RagOntologyConfig(
            min_keyword_length=max(1, min_keyword_length),
            max_entities=max(1, max_entities),
            max_keywords=max(1, max_keywords),
        )
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
