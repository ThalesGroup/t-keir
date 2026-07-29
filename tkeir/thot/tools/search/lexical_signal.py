"""Title: Structural token stems for query expansion / ontology indexing.

Language-agnostic helpers used by :mod:`query_expander` and
:mod:`business_ontology`. Morphology and synonyms come from spaCy /
business ontology — never hardcoded lexicons.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re

# Unicode letter/digit tokens (any script); no language word lists.
_TOKEN_RE = re.compile(r"[\w][\w\-]*", re.UNICODE)
_MIN_TOKEN_LEN = 3


def tokenize(text: str) -> list[str]:
    """Casefold alphanumeric tokens from any Unicode script.

    Example:
        >>> tokenize("FoxO3a / p150n")
        ['foxo3a', 'p150n']
    """
    return [m.group(0).casefold() for m in _TOKEN_RE.finditer(text or "")]


def token_stems(token: str) -> set[str]:
    """Return structural identifier variants (no language morphology).

    Strips punctuation and trailing digit/letter scientific suffixes so
    ``FoxO3a`` / ``p150n`` share stems with ``FOXO`` / ``p150``. Does **not**
    apply language-specific plural / tense rules — use TextNormalizer /
    ontology for that.

    Example:
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
