"""Title: Distinctive lexical overlap signal for dual-hybrid fusion.

Language-agnostic ranking aid: rewards documents that cover distinctive
query tokens (length-weighted, no language word lists), with structural
identifier stemming so aliases like ``FoxO3a`` ↔ ``FOXO`` still match.
Also penalizes near-copies of long document-as-query inputs and builds
compact BM25 projections. Lexical morphology / synonyms come from spaCy
normalization and the request business ontology — never hardcoded lexicon.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re
from typing import Iterable

# Unicode letter/digit tokens (any script); no language word lists.
_TOKEN_RE = re.compile(r"[^\W\d_][\w\-]*", re.UNICODE)
# Queries longer than this are treated as document-as-query (e.g. ArguAna).
_LONG_QUERY_TOKENS = 32
_MIN_TOKEN_LEN = 3


def tokenize(text: str) -> list[str]:
    """Casefold alphanumeric tokens from any Unicode script."""
    return [m.group(0).casefold() for m in _TOKEN_RE.finditer(text or "")]


def token_stems(token: str) -> set[str]:
    """Return structural identifier variants (no language morphology).

    Strips punctuation and trailing digit/letter scientific suffixes so
    ``FoxO3a`` / ``p150n`` share stems with ``FOXO`` / ``p150``. Does **not**
    apply language-specific plural / tense rules — use TextNormalizer /
    ontology for that.

    Examples:
        >>> "foxo" in token_stems("foxo3a")
        True
        >>> "p150" in token_stems("p150n")
        True
    """
    tok = (token or "").casefold().strip()
    if not tok:
        return set()
    out = {tok}
    alnum = "".join(ch for ch in tok if ch.isalnum())
    if alnum:
        out.add(alnum)
    # Drop trailing digit + trailing letters: foxo3a → foxo, p150n → p150
    stripped = re.sub(r"\d+[^\W\d_]*$", "", alnum or tok, flags=re.UNICODE)
    if len(stripped) >= _MIN_TOKEN_LEN:
        out.add(stripped)
    match = re.match(r"^([^\W\d_]*\d+)", alnum or tok, flags=re.UNICODE)
    if match and len(match.group(1)) >= _MIN_TOKEN_LEN:
        out.add(match.group(1))
    return out


def distinctive_tokens(text: str) -> set[str]:
    """Query tokens that carry ranking signal (short tokens dropped)."""
    out: set[str] = set()
    for tok in tokenize(text):
        if len(tok) < _MIN_TOKEN_LEN:
            continue
        out |= token_stems(tok)
    return out


def is_long_query(query: str, *, min_tokens: int = _LONG_QUERY_TOKENS) -> bool:
    """True when the query looks like a full document / argument."""
    return len(tokenize(query)) >= min_tokens


def lexical_query_projection(query: str, *, max_terms: int = 16) -> str:
    """Compact BM25 projection: distinctive tokens, longest first.

    For long document-as-query inputs, using the full text as BM25 OR terms
    floods the query. Projection keeps the strongest length-weighted stems.
    """
    weighted: list[tuple[float, str]] = []
    seen: set[str] = set()
    for tok in tokenize(query):
        if len(tok) < _MIN_TOKEN_LEN:
            continue
        for stem in token_stems(tok):
            if stem in seen or len(stem) < _MIN_TOKEN_LEN:
                continue
            seen.add(stem)
            weighted.append((token_weight(stem), stem))
    weighted.sort(key=lambda row: (-row[0], -len(row[1]), row[1]))
    terms = [stem for _, stem in weighted[:max_terms]]
    return " ".join(terms)


def _doc_token_index(text: str) -> set[str]:
    idx: set[str] = set()
    for tok in tokenize(text):
        idx |= token_stems(tok)
    return idx


def token_weight(token: str) -> float:
    """Boost longer stems (language-agnostic rarity proxy)."""
    return 1.0 + 0.08 * max(0, len(token or "") - 5)


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

    For long queries, score against the compact projection so near-copy
    documents are not rewarded for shared boilerplate.
    """
    probe = (
        lexical_query_projection(query)
        if is_long_query(query)
        else query
    )
    qtoks = distinctive_tokens(probe)
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
    """Jaccard similarity over raw tokens."""
    left_set = set(tokenize(left))
    right_set = set(tokenize(right))
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def containment_ratio(left: str, right: str) -> float:
    """Fraction of ``left`` tokens found in ``right``."""
    left_set = set(tokenize(left))
    right_set = set(tokenize(right))
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set)


def near_copy_penalty(
    query: str,
    doc_text: str,
    *,
    threshold: float | None = None,
) -> float:
    """Demote docs that are near-copies of a *long* document-as-query.

    Short claim/question queries often appear almost verbatim in gold abstracts.
    Penalizing those hurts recall. Only apply when the query itself looks like
    a full argument / document.
    """
    if not is_long_query(query):
        return 1.0
    thresh = threshold if threshold is not None else 0.72
    jac = jaccard_tokens(query, doc_text)
    contain = max(
        containment_ratio(query, doc_text),
        containment_ratio(doc_text, query),
    )
    if jac >= thresh or contain >= 0.90:
        return 0.05
    if jac >= thresh - 0.10 or contain >= 0.80:
        return 0.35
    return 1.0


def rare_token_multiplier(
    query: str,
    *,
    title: str = "",
    body: str = "",
) -> float:
    """Boost docs that hit long query tokens; demote if they miss all.

    Length ≥ 8 is a language-agnostic proxy for rare identifiers / entities.
    """
    rare = [tok for tok in distinctive_tokens(query) if len(tok) >= 8]
    if not rare:
        return 1.0
    doc = _doc_token_index(f"{title} {body}")
    hits = sum(1 for tok in rare if _stems_match(tok, doc))
    if hits == 0:
        return 0.65
    return 1.0 + 0.40 * (hits / len(rare))


def score_documents(
    query: str,
    documents: Iterable[dict[str, str]],
    *,
    apply_near_copy_penalty: bool = True,
) -> dict[str, float]:
    """Score a list of ``{_id, title?, text?}`` dicts for fusion."""
    scores: dict[str, float] = {}
    for doc in documents:
        doc_id = str(doc.get("_id") or doc.get("source_doc_id") or "")
        if not doc_id:
            continue
        title = str(doc.get("title") or "")
        body = str(doc.get("text") or doc.get("best_chunk_text") or "")
        score = lexical_overlap_score(query, title=title, body=body)
        score *= rare_token_multiplier(query, title=title, body=body)
        if apply_near_copy_penalty:
            score *= near_copy_penalty(query, f"{title} {body}".strip())
        scores[doc_id] = score
    return scores
