"""Title: Match user OKF wikis and extract short sections for upsert / RAG.

Library helpers only — no LLM. Used by agent ``wiki_upsert`` and OKF extract API.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from thot.okf.models import OkfBundle
from thot.okf.store import OkfBundleStore

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}", re.IGNORECASE)
_ANSWER_RE = re.compile(
    r"(?:^|\n)##\s+Answer\b(.*?)(?=\n##\s+\S|\Z)",
    flags=re.IGNORECASE | re.DOTALL,
)
_STRUCTURED_RE = re.compile(
    r"(?:^|\n)##\s+Structured facts\b(.*?)(?=\n##\s+\S|\Z)",
    flags=re.IGNORECASE | re.DOTALL,
)
_TITLE_RE = re.compile(r"(?:^|\n)#\s+([^\n]+)", flags=re.MULTILINE)


@dataclass(frozen=True)
class WikiMatch:
    """Best-matching OKF bundle for a query.

    Example:
        >>> WikiMatch(
        ...     bundle_id="b1", score=0.5, title="Port", path="/tmp/b1"
        ... ).bundle_id
        'b1'
    """

    bundle_id: str
    score: float
    title: str
    path: str
    query: str = ""


def _tokens(text: str) -> set[str]:
    """Tokenize for Jaccard similarity.

    Example:
        >>> from thot.okf.wiki_match import _tokens
        >>> "port" in _tokens("Latakia Port")
        True
    """
    return {t.casefold() for t in _TOKEN_RE.findall(text or "")}


def jaccard(a: str, b: str) -> float:
    """Jaccard similarity of token sets.

    Example:
        >>> from thot.okf.wiki_match import jaccard
        >>> jaccard("alpha beta", "alpha gamma") > 0
        True
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return float(inter) / float(union) if union else 0.0


def extract_wiki_sections(
    markdown: str,
    *,
    max_chars: int = 2400,
    include_structured: bool = True,
) -> str:
    """Return Answer (+ optional Structured facts) clipped for prompts.

    Example:
        >>> from thot.okf.wiki_match import extract_wiki_sections
        >>> out = extract_wiki_sections(
        ...     "# T\\n## Answer\\nHello.\\n## Evidence\\n- x\\n"
        ... )
        >>> "Hello" in out and "Evidence" not in out
        True
    """
    text = (markdown or "").strip()
    if not text:
        return ""
    parts: list[str] = []
    ans = _ANSWER_RE.search(text)
    if ans:
        body = ans.group(1).strip()
        if body:
            parts.append("## Answer\n\n" + body)
    if include_structured:
        sf = _STRUCTURED_RE.search(text)
        if sf:
            body = sf.group(1).strip()
            if body:
                parts.append("## Structured facts\n\n" + body)
    if not parts:
        # Fallback: title + head of document
        title_m = _TITLE_RE.search(text)
        head = text[:max_chars].rstrip()
        if title_m:
            return head
        return head
    out = "\n\n".join(parts)
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "\n…[wiki extract truncated]"
    return out


def _bundle_match_text(store: OkfBundleStore, bundle: OkfBundle) -> str:
    """Build searchable text from index.md / wiki title / query meta.

    Example:
        >>> class _Store:
        ...     def get_index(self, *_a, **_k):
        ...         return "# Index Title\\n"
        ...     def get_wiki(self, *_a, **_k):
        ...         return "# Wiki Title\\n"
        >>> from thot.okf.models import OkfBundle
        >>> from thot.okf.wiki_match import _bundle_match_text
        >>> b = OkfBundle(
        ...     bundle_id="b1",
        ...     user_space="u",
        ...     concept_count=0,
        ...     path="/tmp",
        ...     query="port",
        ... )
        >>> "Wiki Title" in _bundle_match_text(_Store(), b)
        True
    """
    chunks: list[str] = []
    if bundle.query:
        chunks.append(str(bundle.query))
    index = store.get_index(bundle.bundle_id, bundle.user_space) or ""
    chunks.append(index)
    wiki = store.get_wiki(bundle.bundle_id, bundle.user_space) or ""
    title_m = _TITLE_RE.search(wiki)
    if title_m:
        chunks.append(title_m.group(1))
    # First heading from index
    idx_title = _TITLE_RE.search(index)
    if idx_title:
        chunks.append(idx_title.group(1))
    return "\n".join(chunks)


def find_closest_wiki(
    user_space: str,
    query: str,
    *,
    store: OkfBundleStore | None = None,
    threshold: float = 0.15,
) -> WikiMatch | None:
    """Return the closest user wiki above ``threshold``, or ``None``.

    Scores each bundle using ``index.md`` (+ wiki title / query metadata).

    Example:
        >>> from thot.okf.wiki_match import find_closest_wiki
        >>> find_closest_wiki("nobody@tkeir", "") is None
        True
    """
    q = (query or "").strip()
    if not q:
        return None
    st = store or OkfBundleStore()
    best: WikiMatch | None = None
    for bundle in st.list_bundles(user_space):
        hay = _bundle_match_text(st, bundle)
        score = jaccard(q, hay)
        title_m = _TITLE_RE.search(hay)
        title = (title_m.group(1).strip() if title_m else bundle.bundle_id)[
            :120
        ]
        if best is None or score > best.score:
            best = WikiMatch(
                bundle_id=bundle.bundle_id,
                score=score,
                title=title,
                path=str(bundle.path),
                query=str(bundle.query or ""),
            )
    if best is None or best.score < float(threshold):
        return None
    return best


def wiki_extract_for_bundle(
    bundle_id: str,
    user_space: str,
    *,
    store: OkfBundleStore | None = None,
    max_chars: int = 2400,
) -> dict[str, Any]:
    """Load wiki.md and return extract payload for RAG / agents.

    Example:
        >>> from thot.okf.wiki_match import wiki_extract_for_bundle
        >>> wiki_extract_for_bundle("missing", "dev@tkeir")["found"]
        False
    """
    st = store or OkfBundleStore()
    bundle = st.get_bundle(bundle_id, user_space)
    if bundle is None:
        return {
            "found": False,
            "bundle_id": bundle_id,
            "user_space": user_space,
            "extract": "",
            "wiki_chars": 0,
        }
    wiki = st.get_wiki(bundle_id, user_space) or ""
    extract = extract_wiki_sections(wiki, max_chars=max_chars)
    return {
        "found": True,
        "bundle_id": bundle_id,
        "user_space": user_space,
        "path": str(bundle.path),
        "query": str(bundle.query or ""),
        "extract": extract,
        "wiki_chars": len(wiki),
        "extract_chars": len(extract),
    }
