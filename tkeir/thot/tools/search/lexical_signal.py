"""Title: Distinctive lexical overlap signal for dual-hybrid fusion.

Corpus-independent ranking aid: rewards documents that cover *distinctive*
query tokens (not stopwords), with light scientific-token stemming so
aliases like ``FoxO3a`` ↔ ``FOXO`` still match. Also penalizes near-copies
of the query (common false-positive failure mode).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re
from typing import Iterable

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,}", re.UNICODE)
_STOPWORDS = frozenset(
    """
    a an the of to in for on with and or is are was were be been being that
    this these those it its as at by from into about than then so if not no
    do does did can could would should will have has had how what when where
    which who why your you we they their our my me i am there their such all
    but other one them only may even many new also most use some any much
    more who whom whose been being
    """.split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens (keeps digits inside tokens)."""
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text or "")]


def token_stems(token: str) -> set[str]:
    """Return matching variants for scientific / compound tokens.

    Examples:
        >>> "foxo" in token_stems("foxo3a")
        True
        >>> "p150" in token_stems("p150n") or "p150" in token_stems("p150glued")
        True
    """
    tok = (token or "").lower().strip()
    if not tok:
        return set()
    out = {tok}
    alnum = re.sub(r"[^a-z0-9]", "", tok)
    if alnum:
        out.add(alnum)
    # Drop trailing digit+letter suffixes: foxo3a → foxo, p150n → p150
    stripped = re.sub(r"\d+[a-z]*$", "", alnum or tok)
    if len(stripped) >= 3:
        out.add(stripped)
    # Prefix before trailing letters after digits: p150glued → p150
    match = re.match(r"^([a-z]*\d+)", alnum or tok)
    if match and len(match.group(1)) >= 3:
        out.add(match.group(1))
    return out


def distinctive_tokens(text: str) -> set[str]:
    """Query tokens that carry ranking signal (stopwords removed)."""
    out: set[str] = set()
    for tok in tokenize(text):
        if tok in _STOPWORDS or len(tok) < 3:
            continue
        out |= token_stems(tok)
    return out


def _doc_token_index(text: str) -> set[str]:
    idx: set[str] = set()
    for tok in tokenize(text):
        idx |= token_stems(tok)
    return idx


_GENERIC = frozenset(
    """
    risk high levels level low factor development disease patient patients
    treatment study studies associated increase increased decrease decreased
    human people company market money better deals get
    """.split()
)


def token_weight(token: str) -> float:
    """Down-weight generic topic tokens; boost longer distinctive stems."""
    tok = (token or "").lower()
    if tok in _GENERIC:
        return 0.35
    return 1.0 + 0.08 * max(0, len(tok) - 5)


def _stems_match(query_stem: str, doc_stems: set[str]) -> bool:
    if query_stem in doc_stems:
        return True
    if len(query_stem) < 4:
        return False
    for doc_stem in doc_stems:
        if len(doc_stem) < 4:
            continue
        if doc_stem.startswith(query_stem) or query_stem.startswith(doc_stem):
            return True
    return False


def lexical_overlap_score(
    query: str,
    *,
    title: str = "",
    body: str = "",
) -> float:
    """Weighted coverage of distinctive query stems in title+body.

    Generic topic tokens (``risk``, ``high``, ``levels``, …) count less so
    documents that only share topical stopwords lose to docs that hit
    distinctive terms (``copeptin``, ``tetraspanin``, …).

    Returns:
        Score in ``[0, 1]``. Empty distinctive query → ``0.0``.
    """
    qtoks = distinctive_tokens(query)
    if not qtoks:
        return 0.0
    doc = _doc_token_index(f"{title} {body}")
    if not doc:
        return 0.0
    num = 0.0
    den = 0.0
    for tok in qtoks:
        weight = token_weight(tok)
        den += weight
        if _stems_match(tok, doc):
            num += weight
    return num / den if den else 0.0


def jaccard_tokens(left: str, right: str) -> float:
    """Jaccard similarity over raw tokens (including stopwords)."""
    left_set = set(tokenize(left))
    right_set = set(tokenize(right))
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def near_copy_penalty(
    query: str, doc_text: str, *, threshold: float = 0.85
) -> float:
    """Return ``0.15`` when ``doc_text`` is a near-copy of ``query``, else ``1.0``.

    Used to demote false positives where an opposing motion (or the query
    itself) is almost identical to the query string.
    """
    if jaccard_tokens(query, doc_text) >= threshold:
        return 0.15
    return 1.0


def score_documents(
    query: str,
    documents: Iterable[dict[str, str]],
    *,
    apply_near_copy_penalty: bool = True,
) -> dict[str, float]:
    """Score a list of ``{_id, title?, text?}`` dicts for fusion.

    Returns:
        Mapping ``doc_id → score`` in ``[0, 1]`` after optional near-copy
        penalty (not re-normalized — absolute coverage matters).
    """
    scores: dict[str, float] = {}
    for doc in documents:
        doc_id = str(doc.get("_id") or doc.get("source_doc_id") or "")
        if not doc_id:
            continue
        title = str(doc.get("title") or "")
        body = str(doc.get("text") or doc.get("best_chunk_text") or "")
        score = lexical_overlap_score(query, title=title, body=body)
        if apply_near_copy_penalty:
            score *= near_copy_penalty(query, f"{title} {body}".strip())
        scores[doc_id] = score
    return scores
