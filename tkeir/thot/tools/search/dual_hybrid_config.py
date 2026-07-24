"""Title: Dual-retrieval hybrid search config (typed section of rag.yaml).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)

# spaCy 3.6 wheel URLs aligned with tkeir/pyproject.toml [dependency-groups] models.
_SPACY_WHEEL = (
    "https://github.com/explosion/spacy-models/releases/download/"
    "{tag}/{tag}-py3-none-any.whl"
)


def _wheel(tag: str) -> str:
    return _SPACY_WHEEL.format(tag=tag)


@dataclass(frozen=True)
class SpacyModelEntry:
    """One spaCy model selectable for a language code."""

    model: str
    download: str = ""


def _default_spacy_models() -> dict[str, SpacyModelEntry]:
    """Built-in language → model map (``default`` / ``xx`` is mandatory)."""
    return {
        "default": SpacyModelEntry(
            model="xx_ent_wiki_sm",
            download=_wheel("xx_ent_wiki_sm-3.6.0"),
        ),
        "xx": SpacyModelEntry(
            model="xx_ent_wiki_sm",
            download=_wheel("xx_ent_wiki_sm-3.6.0"),
        ),
        "en": SpacyModelEntry(
            model="en_core_web_md",
            download=_wheel("en_core_web_md-3.6.0"),
        ),
        "fr": SpacyModelEntry(
            model="fr_core_news_md",
            download=_wheel("fr_core_news_md-3.6.0"),
        ),
        "de": SpacyModelEntry(
            model="de_core_news_md",
            download=_wheel("de_core_news_md-3.6.0"),
        ),
        "es": SpacyModelEntry(
            model="es_core_news_md",
            download=_wheel("es_core_news_md-3.6.0"),
        ),
        "it": SpacyModelEntry(
            model="it_core_news_md",
            download=_wheel("it_core_news_md-3.6.0"),
        ),
        "pt": SpacyModelEntry(
            model="pt_core_news_md",
            download=_wheel("pt_core_news_md-3.6.0"),
        ),
        "nl": SpacyModelEntry(
            model="nl_core_news_md",
            download=_wheel("nl_core_news_md-3.6.0"),
        ),
        "zh": SpacyModelEntry(
            model="zh_core_web_md",
            download=_wheel("zh_core_web_md-3.6.0"),
        ),
        "ja": SpacyModelEntry(
            model="ja_core_news_md",
            download=_wheel("ja_core_news_md-3.6.0"),
        ),
    }


def _warn_if_not_unit(name: str, weights: dict[str, float], tol: float = 0.05) -> None:
    total = sum(weights.values())
    if abs(total - 1.0) > tol:
        LOGGER.warning(
            "Weight group '%s' sums to %.3f (expected ~1.0); continuing",
            name,
            total,
        )


@dataclass(frozen=True)
class PreprocessingConfig:
    """SpaCy normalizer settings (model chosen by detected language)."""

    min_token_length: int = 3
    drop_numbers: bool = True
    asciifold: bool = True
    extra_stopwords: tuple[str, ...] = ()
    spacy_models: dict[str, SpacyModelEntry] = field(
        default_factory=_default_spacy_models
    )

    def resolve_model(self, language: str | None) -> SpacyModelEntry:
        """Pick the spaCy model for ``language``, falling back to ``default``."""
        code = (language or "").strip().lower().replace("_", "-")
        if "-" in code:
            code = code.split("-", 1)[0]
        models = self.spacy_models
        if code and code in models:
            return models[code]
        if "default" in models:
            return models["default"]
        if "xx" in models:
            return models["xx"]
        raise KeyError(
            "preprocessing.spacy_models must define a 'default' (or 'xx') entry"
        )


@dataclass(frozen=True)
class ArmRetrievalConfig:
    """One Vespa retrieval arm."""

    profile: str
    hits: int = 100


@dataclass(frozen=True)
class DualRetrievalArms:
    """Chunk + document arm settings."""

    chunk: ArmRetrievalConfig = field(
        default_factory=lambda: ArmRetrievalConfig(profile="hybrid_2_level")
    )
    document: ArmRetrievalConfig = field(
        default_factory=lambda: ArmRetrievalConfig(profile="document_bm25")
    )


@dataclass(frozen=True)
class QueryExpansionConfig:
    """Business-ontology query expansion (ontology supplied per query)."""

    enabled: bool = True
    max_terms_per_relation: int = 5
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "original": 1.0,
            "synonyms": 0.9,
            "narrower": 0.6,
            "broader": 0.3,
            "related": 0.2,
        }
    )


@dataclass(frozen=True)
class RrfConfig:
    """Reciprocal Rank Fusion."""

    k: int = 60
    arm_weights: dict[str, float] = field(
        default_factory=lambda: {"chunk": 0.6, "document": 0.4}
    )
    top_n_after_fusion: int = 50


@dataclass(frozen=True)
class OntologyScoringYaml:
    """Ontology overlap scoring."""

    enabled: bool = True
    match_weights: dict[str, float] = field(
        default_factory=lambda: {
            "exact": 1.0,
            "synonym": 0.9,
            "narrower": 0.6,
            "broader": 0.3,
            "shared_parent": 0.2,
        }
    )
    max_traversal_depth: int = 2
    normalize_by_query_concepts: bool = True


@dataclass(frozen=True)
class CrossEncoderYaml:
    """Cross-encoder rerank stage."""

    enabled: bool = True
    model: str = "BAAI/bge-reranker-v2-m3"
    top_m: int = 8
    max_length: int = 256
    batch_size: int = 8


@dataclass(frozen=True)
class FinalFusionYaml:
    """Final weighted fusion of RRF / lexical / ontology / cross-encoder."""

    weights: dict[str, float] = field(
        default_factory=lambda: {
            "rrf": 0.35,
            "lexical_overlap": 0.30,
            "ontology_overlap": 0.15,
            "cross_encoder": 0.20,
        }
    )
    top_k_returned: int = 10
    near_copy_penalty: bool = True


@dataclass(frozen=True)
class FallbackYaml:
    """Graceful degradation knobs."""

    neutral_score: float = 0.5


@dataclass(frozen=True)
class DualHybridConfig:
    """Top-level dual-retrieval configuration."""

    enabled: bool = False
    preprocessing: PreprocessingConfig = field(default_factory=PreprocessingConfig)
    retrieval: DualRetrievalArms = field(default_factory=DualRetrievalArms)
    rank_profiles: dict[str, Any] = field(default_factory=dict)
    average_field_length: dict[str, Any] = field(default_factory=dict)
    query_expansion: QueryExpansionConfig = field(default_factory=QueryExpansionConfig)
    rrf: RrfConfig = field(default_factory=RrfConfig)
    ontology_scoring: OntologyScoringYaml = field(default_factory=OntologyScoringYaml)
    cross_encoder: CrossEncoderYaml = field(default_factory=CrossEncoderYaml)
    final_fusion: FinalFusionYaml = field(default_factory=FinalFusionYaml)
    fallback: FallbackYaml = field(default_factory=FallbackYaml)


def _spacy_models_from_mapping(
    raw: dict[str, Any] | None,
) -> dict[str, SpacyModelEntry]:
    """Parse ``preprocessing.spacy_models``; require ``default`` or ``xx``."""
    if not raw:
        return _default_spacy_models()
    merged: dict[str, SpacyModelEntry] = {}
    for lang, entry in raw.items():
        key = str(lang).strip().lower()
        if isinstance(entry, str):
            merged[key] = SpacyModelEntry(model=entry, download="")
        elif isinstance(entry, dict):
            model = str(entry.get("model") or entry.get("name") or "").strip()
            if not model:
                raise ValueError(
                    f"preprocessing.spacy_models.{key} requires 'model'"
                )
            merged[key] = SpacyModelEntry(
                model=model,
                download=str(entry.get("download") or entry.get("url") or ""),
            )
        else:
            raise ValueError(
                f"preprocessing.spacy_models.{key} must be a string or mapping"
            )
    if "default" not in merged and "xx" not in merged:
        raise ValueError(
            "preprocessing.spacy_models must include a mandatory "
            "'default' (or 'xx') multilingual model entry"
        )
    return merged


def dual_hybrid_from_mapping(raw: dict[str, Any] | None) -> DualHybridConfig:
    """Parse the ``dual_hybrid`` block from ``rag.yaml``."""
    cfg = raw or {}
    prep = cfg.get("preprocessing") or {}
    retrieval = cfg.get("retrieval") or {}
    chunk = retrieval.get("chunk") or {}
    document = retrieval.get("document") or {}
    qe = cfg.get("query_expansion") or {}
    rrf = cfg.get("rrf") or {}
    ont = cfg.get("ontology_scoring") or {}
    ce = cfg.get("cross_encoder") or {}
    ff = cfg.get("final_fusion") or {}
    fb = cfg.get("fallback") or {}

    qe_weights = dict(
        QueryExpansionConfig().weights,
        **(qe.get("weights") or {}),
    )
    rrf_weights = dict(RrfConfig().arm_weights, **(rrf.get("arm_weights") or {}))
    match_weights = dict(
        OntologyScoringYaml().match_weights, **(ont.get("match_weights") or {})
    )
    final_weights = dict(
        FinalFusionYaml().weights, **(ff.get("weights") or {})
    )

    _warn_if_not_unit("rrf.arm_weights", rrf_weights)
    _warn_if_not_unit("final_fusion.weights", final_weights)
    for profile_name, profile in (cfg.get("rank_profiles") or {}).get(
        "chunk", {}
    ).items():
        if isinstance(profile, dict):
            weight_keys = {
                key: float(value)
                for key, value in profile.items()
                if key.startswith(("closeness_", "bm25_"))
            }
            if weight_keys:
                _warn_if_not_unit(
                    f"rank_profiles.chunk.{profile_name}", weight_keys
                )
    doc_bm25 = (
        (cfg.get("rank_profiles") or {}).get("document") or {}
    ).get("document_bm25")
    if isinstance(doc_bm25, dict):
        _warn_if_not_unit(
            "rank_profiles.document.document_bm25",
            {key: float(value) for key, value in doc_bm25.items()},
        )

    spacy_models = _spacy_models_from_mapping(prep.get("spacy_models"))

    return DualHybridConfig(
        enabled=bool(cfg.get("enabled", False)),
        preprocessing=PreprocessingConfig(
            min_token_length=int(prep.get("min_token_length", 3)),
            drop_numbers=bool(prep.get("drop_numbers", True)),
            asciifold=bool(prep.get("asciifold", True)),
            extra_stopwords=tuple(prep.get("extra_stopwords") or ()),
            spacy_models=spacy_models,
        ),
        retrieval=DualRetrievalArms(
            chunk=ArmRetrievalConfig(
                profile=str(chunk.get("profile", "hybrid_2_level")),
                hits=int(chunk.get("hits", 100)),
            ),
            document=ArmRetrievalConfig(
                profile=str(document.get("profile", "document_bm25")),
                hits=int(document.get("hits", 100)),
            ),
        ),
        rank_profiles=dict(cfg.get("rank_profiles") or {}),
        average_field_length=dict(cfg.get("average_field_length") or {}),
        query_expansion=QueryExpansionConfig(
            enabled=bool(qe.get("enabled", True)),
            max_terms_per_relation=int(qe.get("max_terms_per_relation", 5)),
            weights=qe_weights,
        ),
        rrf=RrfConfig(
            k=int(rrf.get("k", 60)),
            arm_weights=rrf_weights,
            top_n_after_fusion=int(rrf.get("top_n_after_fusion", 50)),
        ),
        ontology_scoring=OntologyScoringYaml(
            enabled=bool(ont.get("enabled", True)),
            match_weights=match_weights,
            max_traversal_depth=int(ont.get("max_traversal_depth", 2)),
            normalize_by_query_concepts=bool(
                ont.get("normalize_by_query_concepts", True)
            ),
        ),
        cross_encoder=CrossEncoderYaml(
            enabled=bool(ce.get("enabled", True)),
            model=str(ce.get("model", "BAAI/bge-reranker-v2-m3")),
            top_m=int(ce.get("top_m", 8)),
            max_length=int(ce.get("max_length", 256)),
            batch_size=int(ce.get("batch_size", 8)),
        ),
        final_fusion=FinalFusionYaml(
            weights=final_weights,
            top_k_returned=int(ff.get("top_k_returned", 10)),
            near_copy_penalty=bool(ff.get("near_copy_penalty", True)),
        ),
        fallback=FallbackYaml(
            neutral_score=float(fb.get("neutral_score", 0.5)),
        ),
    )
