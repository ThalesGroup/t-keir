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
    drop_numbers: bool = False
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
class DualRetrievalArms:
    """Vespa passage retrieval hits / ranking profile."""

    hits: int = 100
    ranking_profile: str = "hybrid"


@dataclass(frozen=True)
class NlpSeedExpansionConfig:
    """NLP-seeded ontology resolve + neighborhood expansion.

    When enabled, applies if the query has at least ``min_tokens`` whitespace
    tokens **or** at least ``min_sentences`` sentence-like spans (so
    multi-sentence claims qualify even when shorter than ``min_tokens``).

    NER / keyword / SVO labels from the linguistic pipeline are then resolved
    against the business ontology and expanded (synonym / narrower / related /
    broader) into Vespa ``ontology_concepts`` and BM25 probe terms.

    Short single-sentence queries still get raw-query expansion when
    ``query_expansion.enabled``.
    """

    enabled: bool = True
    min_tokens: int = 32
    min_sentences: int = 2


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
            "paraphrase": 0.85,
        }
    )
    nlp_seed_expansion: NlpSeedExpansionConfig = field(
        default_factory=NlpSeedExpansionConfig
    )


@dataclass(frozen=True)
class RrfConfig:
    """Reciprocal Rank Fusion (global + user when mode=both)."""

    k: int = 60
    arm_weights: dict[str, float] = field(
        default_factory=lambda: {"global": 0.55, "user": 0.45}
    )
    top_n_after_fusion: int = 50


@dataclass(frozen=True)
class OntologyScoringYaml:
    """Optional Graph-RAG rescoring of first-stage hits (OntologyRescorer)."""

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
    max_traversal_depth: int = 1
    normalize_by_query_concepts: bool = True
    # Blend weight vs first-stage score: final = (1-w)*first + w*ontology.
    rescore_weight: float = 0.13


@dataclass(frozen=True)
class ColbertYaml:
    """BGE-M3 ColBERT MaxSim second stage (production + BEIR)."""

    enabled: bool = True
    top_m: int = 40
    first_stage_weight: float = 0.55
    colbert_weight: float = 0.45
    # Residual weight for first-stage docs outside the ColBERT pool.
    tail_weight: float = 0.15
    batch_size: int = 8
    # First-stage RRF(BGE, BM25) pool before ColBERT (corpus retrieve).
    rrf_k: int = 60
    pool: int = 100


@dataclass(frozen=True)
class FinalFusionYaml:
    """Truncate to the final top-k after ColBERT / OntologyRescorer."""

    top_k_returned: int = 10


@dataclass(frozen=True)
class FallbackYaml:
    """Graceful degradation knobs."""

    neutral_score: float = 0.5


@dataclass(frozen=True)
class BusinessOntologyConfig:
    """External dataset business ontology (``datasets/<name>/business_ontology.yaml``).

    Defaults keep ontology on for both index and search; flip either flag in
    ``rag.yaml`` to disable without code changes.
    """

    # Tag document json_ld + chunk concept_ids / ontology_text at index time.
    index_enabled: bool = True
    # Load and pass the YAML payload on each search request (expansion /
    # scoring still respect query_expansion.enabled / ontology_scoring.enabled).
    search_enabled: bool = True


@dataclass(frozen=True)
class IndexDumpConfig:
    """Write one JSON dump per indexed document (chunk + sparse + concepts).

    Used by BEIR eval/smoke and general ``index_pipeline_document``. Path is
    relative to the repository root unless absolute.

    When ``save_document`` is true, the dump also stores the full analyzed
    pipeline document (after external-ontology annotation) under
    ``analyzed_document``.
    """

    enabled: bool = True
    path: str = "workspace/index-dumps"
    save_document: bool = True


@dataclass(frozen=True)
class DualHybridConfig:
    """Top-level dual-retrieval configuration."""

    enabled: bool = False
    search_mode: str = "auto"  # auto | global | user | both
    preprocessing: PreprocessingConfig = field(default_factory=PreprocessingConfig)
    retrieval: DualRetrievalArms = field(default_factory=DualRetrievalArms)
    rank_profiles: dict[str, Any] = field(default_factory=dict)
    average_field_length: dict[str, Any] = field(default_factory=dict)
    business_ontology: BusinessOntologyConfig = field(
        default_factory=BusinessOntologyConfig
    )
    index_dump: IndexDumpConfig = field(default_factory=IndexDumpConfig)
    query_expansion: QueryExpansionConfig = field(default_factory=QueryExpansionConfig)
    rrf: RrfConfig = field(default_factory=RrfConfig)
    ontology_scoring: OntologyScoringYaml = field(default_factory=OntologyScoringYaml)
    colbert: ColbertYaml = field(default_factory=ColbertYaml)
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
    # Backward compatible: old chunk/document arms → single hits/profile.
    if "hits" not in retrieval and isinstance(retrieval.get("chunk"), dict):
        retrieval = {
            "hits": int((retrieval.get("chunk") or {}).get("hits", 100)),
            "ranking_profile": str(
                (retrieval.get("chunk") or {}).get("profile", "hybrid")
            ),
        }
    chunk = retrieval.get("chunk") or {}
    document = retrieval.get("document") or {}
    qe = cfg.get("query_expansion") or {}
    nlp_seed = qe.get("nlp_seed_expansion") or {}
    rrf = cfg.get("rrf") or {}
    ont = cfg.get("ontology_scoring") or {}
    cb = cfg.get("colbert") or {}
    ff = cfg.get("final_fusion") or {}
    fb = cfg.get("fallback") or {}
    bo = cfg.get("business_ontology") or {}
    dump = cfg.get("index_dump") or {}

    qe_weights = dict(
        QueryExpansionConfig().weights,
        **(qe.get("weights") or {}),
    )
    rrf_weights = dict(RrfConfig().arm_weights, **(rrf.get("arm_weights") or {}))
    match_weights = dict(
        OntologyScoringYaml().match_weights, **(ont.get("match_weights") or {})
    )

    _warn_if_not_unit("rrf.arm_weights", rrf_weights)
    for profile_name, profile in (cfg.get("rank_profiles") or {}).get(
        "passage", {}
    ).items():
        if isinstance(profile, dict):
            weight_keys = {
                key: float(value)
                for key, value in profile.items()
                if key in {"dense", "sparse", "bm25"}
            }
            if weight_keys:
                _warn_if_not_unit(
                    f"rank_profiles.passage.{profile_name}", weight_keys
                )

    spacy_models = _spacy_models_from_mapping(prep.get("spacy_models"))

    return DualHybridConfig(
        enabled=bool(cfg.get("enabled", False)),
        search_mode=str(cfg.get("search_mode") or "auto").strip().lower()
        or "auto",
        preprocessing=PreprocessingConfig(
            min_token_length=int(prep.get("min_token_length", 3)),
            drop_numbers=bool(prep.get("drop_numbers", False)),
            asciifold=bool(prep.get("asciifold", True)),
            extra_stopwords=tuple(prep.get("extra_stopwords") or ()),
            spacy_models=spacy_models,
        ),
        retrieval=DualRetrievalArms(
            hits=int(
                retrieval.get("hits")
                or chunk.get("hits")
                or document.get("hits")
                or 100
            ),
            ranking_profile=str(
                retrieval.get("ranking_profile")
                or chunk.get("profile")
                or "hybrid"
            ),
        ),
        rank_profiles=dict(cfg.get("rank_profiles") or {}),
        average_field_length=dict(cfg.get("average_field_length") or {}),
        business_ontology=BusinessOntologyConfig(
            index_enabled=bool(bo.get("index_enabled", True)),
            search_enabled=bool(bo.get("search_enabled", True)),
        ),
        index_dump=IndexDumpConfig(
            enabled=bool(dump.get("enabled", True)),
            path=str(
                dump.get("path") or IndexDumpConfig().path
            ).strip()
            or IndexDumpConfig().path,
            save_document=bool(dump.get("save_document", True)),
        ),
        query_expansion=QueryExpansionConfig(
            enabled=bool(qe.get("enabled", True)),
            max_terms_per_relation=int(qe.get("max_terms_per_relation", 5)),
            weights=qe_weights,
            nlp_seed_expansion=NlpSeedExpansionConfig(
                enabled=bool(
                    nlp_seed.get(
                        "enabled", NlpSeedExpansionConfig().enabled
                    )
                ),
                min_tokens=max(
                    1,
                    int(
                        nlp_seed.get(
                            "min_tokens",
                            NlpSeedExpansionConfig().min_tokens,
                        )
                    ),
                ),
                min_sentences=max(
                    1,
                    int(
                        nlp_seed.get(
                            "min_sentences",
                            NlpSeedExpansionConfig().min_sentences,
                        )
                    ),
                ),
            ),
        ),
        rrf=RrfConfig(
            k=int(rrf.get("k", 60)),
            arm_weights=rrf_weights,
            top_n_after_fusion=int(rrf.get("top_n_after_fusion", 50)),
        ),
        ontology_scoring=OntologyScoringYaml(
            enabled=bool(ont.get("enabled", True)),
            match_weights=match_weights,
            max_traversal_depth=int(ont.get("max_traversal_depth", 1)),
            normalize_by_query_concepts=bool(
                ont.get("normalize_by_query_concepts", True)
            ),
            rescore_weight=float(
                ont.get("rescore_weight", OntologyScoringYaml().rescore_weight)
            ),
        ),
        colbert=ColbertYaml(
            enabled=bool(cb.get("enabled", True)),
            top_m=int(cb.get("top_m", 40)),
            first_stage_weight=float(cb.get("first_stage_weight", 0.55)),
            colbert_weight=float(cb.get("colbert_weight", 0.45)),
            tail_weight=float(cb.get("tail_weight", 0.15)),
            batch_size=int(cb.get("batch_size", 8)),
            rrf_k=int(cb.get("rrf_k", 60)),
            pool=int(cb.get("pool", 100)),
        ),
        final_fusion=FinalFusionYaml(
            top_k_returned=int(ff.get("top_k_returned", 10)),
        ),
        fallback=FallbackYaml(
            neutral_score=float(fb.get("neutral_score", 0.5)),
        ),
    )
