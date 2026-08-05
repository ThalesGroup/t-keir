"""Title: Language-agnostic SimHash for collector near-duplicate detection.

Uses accent-folded lowercase character n-grams so French/English (and other
Latin-script) pages with the same content collide, independent of spaCy language.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable

_WS_RE = re.compile(r"\s+")


def normalize_for_simhash(text: str) -> str:
    """Normalize text for language-agnostic fingerprinting.

    NFKC → fold accents → lowercase → drop punctuation → collapse whitespace.
    Unicode letters/digits are kept so non-Latin scripts still fingerprint.

    Example:
        >>> from thot.tools.collector.simhash import normalize_for_simhash
        >>> normalize_for_simhash("Café FRANÇAIS!")
        'cafe francais'
        >>> normalize_for_simhash("café français.")
        'cafe francais'
    """
    raw = unicodedata.normalize("NFKC", text or "")
    try:
        from fold_to_ascii import fold

        folded = fold(raw)
    except Exception:  # noqa: BLE001
        folded = "".join(
            c
            for c in unicodedata.normalize("NFKD", raw)
            if not unicodedata.combining(c)
        )
    cleaned = "".join(
        c if (c.isalnum() or c.isspace()) else " " for c in folded.lower()
    )
    return _WS_RE.sub(" ", cleaned).strip()


def char_ngrams(text: str, *, n: int = 3) -> list[str]:
    """Return character n-grams over normalized text (padded).

    Example:
        >>> from thot.tools.collector.simhash import char_ngrams, normalize_for_simhash
        >>> grams = char_ngrams(normalize_for_simhash("ab"), n=3)
        >>> "  a" in grams and "ab " in grams
        True
    """
    if n < 1:
        return []
    body = text or ""
    if not body:
        return []
    padded = f"{' ' * (n - 1)}{body}{' ' * (n - 1)}"
    return [padded[i : i + n] for i in range(len(padded) - n + 1)]


def _feature_hash(feature: str) -> int:
    """Hash one n-gram feature to an unsigned 64-bit int.

    Example:
        >>> from thot.tools.collector.simhash import _feature_hash
        >>> isinstance(_feature_hash("abc"), int)
        True
        >>> _feature_hash("abc") == _feature_hash("abc")
        True
    """
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=False)


def simhash64(text: str, *, ngram: int = 3) -> int:
    """Compute a 64-bit SimHash over language-agnostic char n-grams.

    Example:
        >>> from thot.tools.collector.simhash import simhash64
        >>> base = "The maritime AIS anomaly report describes spoofing near the Strait of Hormuz. " * 3
        >>> a = simhash64(base.strip())
        >>> b = simhash64(base.strip() + "!")
        >>> hamming_distance(a, b) <= 3
        True
        >>> simhash64("Café") == simhash64("cafe")
        True
    """
    normalized = normalize_for_simhash(text)
    features = char_ngrams(normalized, n=ngram)
    if not features:
        return 0
    weights = [0] * 64
    for feature in features:
        value = _feature_hash(feature)
        for bit in range(64):
            if value & (1 << bit):
                weights[bit] += 1
            else:
                weights[bit] -= 1
    fingerprint = 0
    for bit, weight in enumerate(weights):
        if weight > 0:
            fingerprint |= 1 << bit
    return fingerprint


def hamming_distance(left: int, right: int) -> int:
    """Return Hamming distance between two 64-bit fingerprints.

    Example:
        >>> from thot.tools.collector.simhash import hamming_distance
        >>> hamming_distance(0b1010, 0b1000)
        1
    """
    return (int(left) ^ int(right)).bit_count()


def is_near_duplicate(
    candidate: int,
    known: Iterable[int],
    *,
    max_distance: int = 3,
) -> tuple[bool, int | None]:
    """Return ``(True, matching_hash)`` when ``candidate`` is near a known hash.

    Example:
        >>> from thot.tools.collector.simhash import is_near_duplicate, simhash64
        >>> h = simhash64("hello world again and again")
        >>> is_near_duplicate(h, [h])[0]
        True
        >>> is_near_duplicate(simhash64("totally different xyz"), [h], max_distance=3)[0]
        False
    """
    for existing in known:
        if hamming_distance(candidate, int(existing)) <= max_distance:
            return True, int(existing)
    return False, None
