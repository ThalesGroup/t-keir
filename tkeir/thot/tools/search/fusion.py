"""Title: Reciprocal Rank Fusion and final score fusion for dual retrieval.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[str]],
    arm_weights: dict[str, float],
    k: int,
) -> dict[str, float]:
    """Fuse ranked document-id lists with weighted RRF.

    Args:
        ranked_lists: Arm name → ordered document ids (best first).
        arm_weights: Per-arm multiplier (from config).
        k: RRF smoothing constant.

    Returns:
        Mapping of document id → raw RRF score.

    Example:
        >>> reciprocal_rank_fusion(
        ...     {"chunk": ["a", "b"], "document": ["b", "a"]},
        ...     {"chunk": 0.6, "document": 0.4},
        ...     k=60,
        ... )["a"] > 0
        True
    """
    scores: dict[str, float] = {}
    for arm, doc_ids in ranked_lists.items():
        weight = float(arm_weights.get(arm, 1.0))
        for rank, doc_id in enumerate(doc_ids, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + weight / (k + rank)
    return scores


def normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    """Min-max normalize scores to ``[0, 1]``.

    Args:
        scores: Raw scores.

    Returns:
        Normalized scores (empty → empty; constant → all 1.0).
    """
    if not scores:
        return {}
    values = list(scores.values())
    low = min(values)
    high = max(values)
    if high <= low:
        return {key: 1.0 for key in scores}
    span = high - low
    return {key: (value - low) / span for key, value in scores.items()}


def redistribute_weights(
    weights: dict[str, float],
    active: set[str],
) -> dict[str, float]:
    """Redistribute inactive signal weights across active ones.

    Args:
        weights: Configured fusion weights.
        active: Signal names that produced a usable score.

    Returns:
        Weights for active signals only (sum ≈ 1 when any active).
    """
    live = {key: float(weights[key]) for key in active if key in weights}
    total = sum(live.values())
    if total <= 0:
        if not active:
            return {}
        equal = 1.0 / len(active)
        return {key: equal for key in active}
    return {key: value / total for key, value in live.items()}


def weighted_fusion(
    signal_scores: dict[str, dict[str, float]],
    weights: dict[str, float],
) -> dict[str, float]:
    """Combine per-signal score maps with redistributed weights.

    Args:
        signal_scores: Signal name → (doc_id → normalized score).
        weights: Configured weights (inactive signals redistributed).

    Returns:
        Combined doc_id → score.
    """
    active = {name for name, mapping in signal_scores.items() if mapping}
    live_weights = redistribute_weights(weights, active)
    combined: dict[str, float] = {}
    for signal, mapping in signal_scores.items():
        weight = live_weights.get(signal)
        if weight is None:
            continue
        for doc_id, score in mapping.items():
            combined[doc_id] = combined.get(doc_id, 0.0) + weight * score
    return combined
