"""Title: BGE-M3 dense + sparse embeddings via FlagEmbedding.

Loads weights from ``resources/modeling/net/bge-m3`` (local project tree),
not from the Hugging Face hub cache.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass
from typing import Any

from thot.core.TkeirPaths import bge_m3_model_dir

LOGGER = logging.getLogger(__name__)

BGE_M3_DENSE_DIM = 1024
_DEFAULT_LOCAL_NAME = "bge-m3"

_LOCK = threading.Lock()
_MODEL: Any | None = None
_MODEL_PATH: str | None = None


@dataclass(frozen=True)
class DenseSparseEmbedding:
    """One text encoded as dense + sparse BGE-M3 outputs."""

    dense: list[float]
    # Token id (string) → weight for Vespa mapped tensor ``token{}``.
    sparse: dict[str, float]


def local_bge_m3_ready(path: str | None = None) -> bool:
    """Return whether a usable BGE-M3 checkout exists under ``net/``.

    Requires ``config.json`` plus at least one dense weight file
    (``model.safetensors`` or ``pytorch_model.bin``).
    """
    root = path or bge_m3_model_dir()
    if not os.path.isfile(os.path.join(root, "config.json")):
        return False
    for name in ("model.safetensors", "pytorch_model.bin"):
        if os.path.isfile(os.path.join(root, name)):
            return True
    return False


def resolve_bge_m3_path(model_id: str | None = None) -> str:
    """Resolve the filesystem path used to load BGE-M3.

    Prefers ``resources/modeling/net/bge-m3``. Absolute/relative paths that
    already exist are accepted. Hugging Face repo ids are rejected at load
    time unless the local ``net/bge-m3`` tree is present (run ``make pull-bge-model``).
    """
    candidate = (model_id or "").strip()
    local = bge_m3_model_dir()
    if local_bge_m3_ready(local):
        if not candidate or candidate in {
            _DEFAULT_LOCAL_NAME,
            "BAAI/bge-m3",
            "bge-m3",
            "bge_m3",
        }:
            return local
        # Explicit local override
        if os.path.isdir(candidate) and local_bge_m3_ready(candidate):
            return os.path.abspath(candidate)
        return local
    if candidate and os.path.isdir(candidate) and local_bge_m3_ready(candidate):
        return os.path.abspath(candidate)
    raise FileNotFoundError(
        f"BGE-M3 model not found at {local}. "
        "Run: make pull-bge-model  (downloads into resources/modeling/net/bge-m3)"
    )


def _load_model(model_id: str | None = None) -> Any:
    """Lazy-load FlagEmbedding BGEM3FlagModel from the local net/ tree."""
    global _MODEL, _MODEL_PATH
    path = resolve_bge_m3_path(model_id)
    with _LOCK:
        if _MODEL is not None and _MODEL_PATH == path:
            return _MODEL
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "FlagEmbedding is required for BGE-M3 dense+sparse embeddings. "
                "Install with: pip install FlagEmbedding"
            ) from exc
        LOGGER.info("Loading FlagEmbedding BGEM3FlagModel from %s …", path)
        _MODEL = BGEM3FlagModel(path, use_fp16=True)
        _MODEL_PATH = path
        return _MODEL


def _normalize_dense(vec: list[float] | Any, dim: int) -> list[float]:
    if vec is None:
        values: list[float] = []
    else:
        # numpy ndarray / list / tuple
        values = [float(x) for x in list(vec)[:dim]]
    if len(values) < dim:
        values.extend([0.0] * (dim - len(values)))
    return values[:dim]


# Special / padding tokens dropped after id→token conversion.
_SPARSE_STOP = frozenset(
    {
        "[cls]",
        "[sep]",
        "[pad]",
        "[unk]",
        "[mask]",
        "<s>",
        "</s>",
        "<pad>",
        "<unk>",
        "<mask>",
        "",
    }
)
_CONTENT_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]{1,}", re.UNICODE)
# Common English function words — keep content-bearing sparse cells denser.
_CONTENT_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "by",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "at",
        "into",
        "than",
        "then",
        "but",
        "not",
        "no",
        "nor",
        "so",
        "if",
        "we",
        "our",
        "their",
        "they",
        "them",
        "he",
        "she",
        "his",
        "her",
        "which",
        "who",
        "whom",
        "what",
        "when",
        "where",
        "how",
        "can",
        "may",
        "will",
        "would",
        "could",
        "should",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "also",
        "such",
        "via",
        "using",
        "used",
        "use",
        "per",
    }
)

# Default caps / weights for SPLADE-style sparse enrichment (SciFact gap).
DEFAULT_SPARSE_MAX_TOKENS = 384
DEFAULT_ONTOLOGY_SPARSE_WEIGHT = 0.85
DEFAULT_CONTENT_SPARSE_WEIGHT = 0.55
DEFAULT_QUERY_EXPAND_SPARSE_WEIGHT = 0.75


def normalize_sparse_token(token: str) -> str | None:
    """Normalize a sparse dimension key (casefold, drop specials)."""
    cleaned = (token or "").strip().casefold()
    if not cleaned or cleaned in _SPARSE_STOP:
        return None
    if not any(ch.isalnum() for ch in cleaned):
        return None
    if len(cleaned) < 2:
        return None
    return cleaned


def _sparse_from_lexical_weights(raw: Any) -> dict[str, float]:
    """Convert FlagEmbedding lexical_weights to Vespa token{} cells."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        items = raw.items()
    else:
        try:
            items = dict(raw).items()
        except Exception:  # noqa: BLE001
            return {}
    out: dict[str, float] = {}
    for key, weight in items:
        try:
            w = float(weight)
        except (TypeError, ValueError):
            continue
        if w == 0.0:
            continue
        tok = normalize_sparse_token(str(key))
        if tok is None:
            # Keep raw numeric token-ids when conversion has not run yet.
            raw_key = str(key).strip()
            if raw_key.isdigit():
                out[raw_key] = max(out.get(raw_key, 0.0), w)
            continue
        out[tok] = max(out.get(tok, 0.0), w)
    return out


def _convert_lexical_ids_to_tokens(model: Any, lexical: Any) -> list[Any]:
    """Map BGE token-id sparse dicts to decoded tokens (SPLADE-readable)."""
    if lexical is None:
        return []
    converter = getattr(model, "convert_id_to_token", None)
    if converter is None:
        return list(lexical) if not isinstance(lexical, dict) else [lexical]
    try:
        converted = converter(lexical)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("BGE convert_id_to_token failed: %s", exc)
        return list(lexical) if not isinstance(lexical, dict) else [lexical]
    if isinstance(converted, dict):
        return [converted]
    return list(converted or [])


def merge_sparse(
    *parts: dict[str, float] | None,
    max_tokens: int = DEFAULT_SPARSE_MAX_TOKENS,
) -> dict[str, float]:
    """Merge sparse maps (max weight wins) and keep the strongest cells."""
    merged: dict[str, float] = {}
    for part in parts:
        if not part:
            continue
        for key, weight in part.items():
            tok = normalize_sparse_token(str(key))
            if tok is None:
                continue
            try:
                w = float(weight)
            except (TypeError, ValueError):
                continue
            if w == 0.0:
                continue
            merged[tok] = max(merged.get(tok, 0.0), w)
    if max_tokens > 0 and len(merged) > max_tokens:
        top = sorted(merged.items(), key=lambda kv: kv[1], reverse=True)[
            :max_tokens
        ]
        return dict(top)
    return merged


def terms_to_sparse(
    terms: list[str] | tuple[str, ...] | set[str],
    *,
    weight: float,
) -> dict[str, float]:
    """Build a sparse map from free-text terms (ontology / expansion)."""
    out: dict[str, float] = {}
    w = float(weight)
    if w == 0.0:
        return out
    for term in terms:
        if not term:
            continue
        # Multi-word labels contribute both the phrase and its tokens.
        phrase = normalize_sparse_token(str(term).replace(" ", "-"))
        if phrase is not None and "-" in phrase:
            out[phrase] = max(out.get(phrase, 0.0), w)
        for tok in _CONTENT_TOKEN_RE.findall(str(term)):
            key = normalize_sparse_token(tok)
            if key is None or key in _CONTENT_STOP:
                continue
            out[key] = max(out.get(key, 0.0), w)
    return out


def content_sparse_from_text(
    text: str,
    *,
    weight: float = DEFAULT_CONTENT_SPARSE_WEIGHT,
    max_tokens: int = DEFAULT_SPARSE_MAX_TOKENS,
) -> dict[str, float]:
    """Surface-form content tokens — densifies sparse vs raw BGE-M3 alone.

    SciFact leaderboard leader is SPLADE (learned sparse expansion). BGE-M3
    lexical weights are often sparse/small; injecting content tokens keeps a
    stronger lexical channel alongside dense (closer to SPLADE+BM25 hybrid).
    """
    counts: dict[str, int] = {}
    for tok in _CONTENT_TOKEN_RE.findall(text or ""):
        key = normalize_sparse_token(tok)
        if key is None or key in _CONTENT_STOP:
            continue
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return {}
    max_tf = max(counts.values())
    base = float(weight)
    out = {
        tok: base * (0.5 + 0.5 * (tf / max_tf))
        for tok, tf in counts.items()
    }
    return merge_sparse(out, max_tokens=max_tokens)


def enrich_sparse(
    base: dict[str, float] | None,
    *,
    text: str = "",
    ontology_labels: list[str] | None = None,
    expansion_terms: list[str] | None = None,
    ontology_weight: float = DEFAULT_ONTOLOGY_SPARSE_WEIGHT,
    content_weight: float = DEFAULT_CONTENT_SPARSE_WEIGHT,
    expansion_weight: float = DEFAULT_QUERY_EXPAND_SPARSE_WEIGHT,
    max_tokens: int = DEFAULT_SPARSE_MAX_TOKENS,
) -> dict[str, float]:
    """SPLADE-style sparse enrichment over BGE-M3 lexical weights.

    Merges:
      1. BGE-M3 sparse (token-decoded)
      2. Chunk / query surface content tokens
      3. Ontology expansion labels (synonyms + paraphrase bridges)
      4. Query-time expansion terms
    """
    return merge_sparse(
        base,
        content_sparse_from_text(text, weight=content_weight, max_tokens=max_tokens)
        if text
        else None,
        terms_to_sparse(ontology_labels or [], weight=ontology_weight),
        terms_to_sparse(expansion_terms or [], weight=expansion_weight),
        max_tokens=max_tokens,
    )


def encode_texts(
    texts: list[str],
    *,
    model_id: str | None = None,
    dense_dim: int = BGE_M3_DENSE_DIM,
    batch_size: int = 16,
) -> list[DenseSparseEmbedding]:
    """Encode texts with BGE-M3 dense + sparse outputs.

    Sparse weights are converted from tokenizer ids to decoded tokens (same
    space FlagEmbedding uses for ``compute_lexical_matching_score``), then
    normalized. Callers should further enrich with ontology/content via
    :func:`enrich_sparse` (optional experiments only — not used on the
    production index/query path after SciFact regression).

    Args:
        texts: Input strings (empty list → empty result).
        model_id: Optional local path override (default: ``net/bge-m3``).
        dense_dim: Dense vector length (BGE-M3 = 1024).
        batch_size: FlagEmbedding batch size.

    Returns:
        One :class:`DenseSparseEmbedding` per input text.
    """
    if not texts:
        return []
    model = _load_model(model_id)
    output = model.encode(
        texts,
        batch_size=batch_size,
        max_length=8192,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )
    # FlagEmbedding returns numpy arrays; do not use ``x or []`` (ambiguous truth).
    dense_vecs = output.get("dense_vecs")
    if dense_vecs is None:
        dense_vecs = []
    lexical = output.get("lexical_weights")
    if lexical is None:
        lexical = []
    lexical = _convert_lexical_ids_to_tokens(model, lexical)
    n_dense = len(dense_vecs)
    n_lex = len(lexical)
    results: list[DenseSparseEmbedding] = []
    for index, text in enumerate(texts):
        dense_raw = dense_vecs[index] if index < n_dense else []
        sparse_raw = lexical[index] if index < n_lex else {}
        results.append(
            DenseSparseEmbedding(
                dense=_normalize_dense(dense_raw, dense_dim),
                sparse=_sparse_from_lexical_weights(sparse_raw),
            )
        )
        if not results[-1].dense and text:
            LOGGER.warning("Empty dense embedding for text[%d]", index)
    return results


def encode_one(
    text: str,
    *,
    model_id: str | None = None,
    dense_dim: int = BGE_M3_DENSE_DIM,
) -> DenseSparseEmbedding:
    """Encode a single string."""
    return encode_texts(
        [text], model_id=model_id, dense_dim=dense_dim, batch_size=1
    )[0]


def encode_colbert_vecs(
    texts: list[str],
    *,
    model_id: str | None = None,
    batch_size: int = 8,
    max_length: int = 512,
) -> list[Any] | None:
    """Encode texts to BGE-M3 ColBERT multi-vectors (query-time MaxSim).

    Indexing stores dense+sparse only; ColBERT is computed at search time
    from the same FlagEmbedding weights under ``resources/modeling/net/bge-m3``.
    """
    if not texts:
        return []
    model = _load_model(model_id)
    packed = model.encode(
        texts,
        batch_size=batch_size,
        max_length=max_length,
        return_dense=False,
        return_sparse=False,
        return_colbert_vecs=True,
    )
    colbert = packed.get("colbert_vecs")
    if colbert is None:
        return None
    return list(colbert)


def vespa_dense_tensor(dense: list[float], dim: int) -> dict[str, list[float]]:
    """Vespa indexed tensor payload for ``tensor<float>(x[dim])``."""
    values = _normalize_dense(dense, dim)
    return {"values": values}


def vespa_sparse_tensor(sparse: dict[str, float]) -> dict[str, Any]:
    """Vespa mapped tensor payload for ``tensor<float>(token{})``."""
    cells = [
        {"address": {"token": str(token)}, "value": float(weight)}
        for token, weight in sparse.items()
        if weight
    ]
    return {"cells": cells}
