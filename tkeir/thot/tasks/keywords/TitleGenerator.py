# -*- coding: utf-8 -*-
"""Generate a document title when the converter did not provide one."""

from __future__ import annotations

import re

_PREFERRED_NER_LABELS = frozenset(
    {
        "person",
        "per",
        "organization",
        "org",
        "company",
        "product",
        "event",
        "facility",
        "location",
        "loc",
        "gpe",
    }
)

_BOILERPLATE_TOKENS = frozenset(
    {
        "donate",
        "create",
        "account",
        "log",
        "article",
        "talk",
        "read",
        "edit",
        "view",
        "history",
        "languages",
        "wikipedia",
        "encyclopedia",
        "copyright",
        "privacy",
        "policy",
        "cookie",
        "mobile",
    }
)

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_title(text: str, max_length: int) -> str:
    """Normalize title helper.

    Example:
        >>> _normalize_title('  Hello   World  ', 20)
        'Hello World'
    """
    cleaned = _WHITESPACE_RE.sub(" ", text).strip(" \t\n\r-–—|:")
    if not cleaned:
        return ""
    if len(cleaned) <= max_length:
        return cleaned
    truncated = cleaned[:max_length].rsplit(" ", 1)[0].strip()
    return truncated or cleaned[:max_length].strip()


def _has_title(tkeir_doc: dict) -> bool:
    """Has title helper.

    Example:
        >>> _has_title({'title': 'Report'})
        True
        >>> _has_title({'title': '  '})
        False
    """
    return bool((tkeir_doc.get("title") or "").strip())


def _title_from_early_ner(
    tkeir_doc: dict,
    max_token_window: int,
) -> str:
    """Title from early ner helper.

    Example:
        >>> from thot.tasks.keywords.TitleGenerator import _title_from_early_ner
        >>> callable(_title_from_early_ner)
        True
    """
    best: tuple[int, int, str] | None = None
    for span in tkeir_doc.get("content_ner") or []:
        label = (span.get("label") or "").lower()
        if label not in _PREFERRED_NER_LABELS:
            continue
        start = int(span.get("start", 0))
        if start > max_token_window:
            continue
        text = (span.get("text") or "").strip()
        if not text:
            continue
        word_count = len(text.split())
        if word_count > 12:
            continue
        candidate = (start, -word_count, text)
        if best is None or candidate < best:
            best = candidate
    return best[2] if best else ""


def _title_from_keywords(
    content_keywords: list[tuple],
    max_length: int,
) -> str:
    """Title from keywords helper.

    Example:
        >>> from thot.tasks.keywords.TitleGenerator import _title_from_keywords
        >>> callable(_title_from_keywords)
        True
    """
    best: tuple[float, int, str] | None = None
    for score, text, _phrase in content_keywords:
        phrase = (text or "").strip()
        if not phrase:
            continue
        word_count = len(phrase.split())
        if word_count < 2 or word_count > 10:
            continue
        lowered = phrase.lower()
        if any(token in _BOILERPLATE_TOKENS for token in lowered.split()):
            continue
        length_penalty = abs(word_count - 4)
        candidate = (float(score), length_penalty, phrase)
        if best is None or candidate > best:
            best = candidate
    if best is None:
        return ""
    return _normalize_title(best[2], max_length)


def _sentence_text(morphosyntax: list[dict], start: int, end: int) -> str:
    """Sentence text helper.

    Example:
        >>> morph = [{'text': 'Hello'}, {'text': 'world'}]
        >>> _sentence_text(morph, 0, 2)
        'Hello world'
    """
    return " ".join(
        token.get("text", "") for token in morphosyntax[start:end]
    ).strip()


def _is_boilerplate_sentence(text: str) -> bool:
    """Is boilerplate sentence helper.

    Example:
        >>> _is_boilerplate_sentence('Read edit view history')
        True
        >>> _is_boilerplate_sentence('Quarterly revenue increased.')
        False
    """
    tokens = [token.lower() for token in re.findall(r"[A-Za-z']+", text)]
    if not tokens:
        return True
    boilerplate_hits = sum(
        1 for token in tokens if token in _BOILERPLATE_TOKENS
    )
    return boilerplate_hits >= max(2, len(tokens) // 2)


def _title_from_first_sentence(
    tkeir_doc: dict,
    max_length: int,
    max_tokens: int,
) -> str:
    """Title from first sentence helper.

    Example:
        >>> from thot.tasks.keywords.TitleGenerator import _title_from_first_sentence
        >>> callable(_title_from_first_sentence)
        True
    """
    morphosyntax = tkeir_doc.get("content_morphosyntax") or []
    if not morphosyntax:
        return ""

    sentence_starts = [0]
    for index, token in enumerate(morphosyntax):
        if index > 0 and token.get("is_sent_start"):
            sentence_starts.append(index)
    sentence_starts.append(len(morphosyntax))

    for start_index in range(len(sentence_starts) - 1):
        start = sentence_starts[start_index]
        end = sentence_starts[start_index + 1]
        token_count = end - start
        if token_count < 3 or token_count > max_tokens:
            continue
        sentence = _sentence_text(morphosyntax, start, end)
        if not sentence or _is_boilerplate_sentence(sentence):
            continue
        return _normalize_title(sentence, max_length)
    return ""


def _title_from_content_lines(tkeir_doc: dict, max_length: int) -> str:
    """Title from content lines helper.

    Example:
        >>> from thot.tasks.keywords.TitleGenerator import _title_from_content_lines
        >>> callable(_title_from_content_lines)
        True
    """
    content = tkeir_doc.get("content") or []
    raw_text = "\n".join(str(block) for block in content if block).strip()
    if not raw_text:
        return ""

    for line in raw_text.splitlines():
        candidate = _WHITESPACE_RE.sub(" ", line).strip()
        if not candidate:
            continue
        word_count = len(candidate.split())
        if word_count < 2 or word_count > 16:
            continue
        if _is_boilerplate_sentence(candidate):
            continue
        return _normalize_title(candidate, max_length)
    return ""


def generate_missing_title(
    tkeir_doc: dict,
    content_keywords: list[tuple] | None = None,
    max_length: int = 120,
    max_ner_token_window: int = 120,
) -> str:
    """Return a generated title, or an empty string when a title already exists.

    Example:
        >>> doc = {'title': 'Existing', 'content_morphosyntax': []}
        >>> generate_missing_title(doc)
        ''
    """
    if _has_title(tkeir_doc):
        return ""

    candidates: list[tuple[int, str]] = []

    ner_title = _title_from_early_ner(tkeir_doc, max_ner_token_window)
    if ner_title:
        candidates.append((100, ner_title))

    keyword_title = _title_from_keywords(content_keywords or [], max_length)
    if keyword_title:
        candidates.append((80, keyword_title))

    sentence_title = _title_from_first_sentence(
        tkeir_doc, max_length, max_tokens=20
    )
    if sentence_title:
        candidates.append((60, sentence_title))

    line_title = _title_from_content_lines(tkeir_doc, max_length)
    if line_title:
        candidates.append((40, line_title))

    if not candidates:
        return ""

    candidates.sort(key=lambda item: item[0], reverse=True)
    return _normalize_title(candidates[0][1], max_length)
