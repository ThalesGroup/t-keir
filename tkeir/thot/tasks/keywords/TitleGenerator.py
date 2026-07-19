"""Generate a document title when the converter did not provide one."""

from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"\w+", re.UNICODE)
_CONTENT_POS = frozenset({"NOUN", "PROPN", "ADJ", "NUM"})


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


def _morphosyntax_slice(
    morphosyntax: list[dict],
    start: int,
    end: int,
) -> list[dict]:
    """Return morphosyntax tokens covered by a token index range.

    Example:
        >>> morph = [{"text": "Rob", "pos": "PROPN"}, {"text": "Brown", "pos": "PROPN"}]
        >>> [token["text"] for token in _morphosyntax_slice(morph, 0, 2)]
        ['Rob', 'Brown']
    """
    if not morphosyntax:
        return []
    start = max(0, start)
    end = min(len(morphosyntax), end)
    return morphosyntax[start:end]


def _named_content_score(morph_slice: list[dict]) -> tuple[int, int]:
    """Return ``(propn_count, noun_count)`` for a morphosyntax slice.

    Example:
        >>> _named_content_score(
        ...     [{"text": "Rob", "pos": "PROPN"}, {"text": "Brown", "pos": "PROPN"}]
        ... )
        (2, 0)
    """
    propn = sum(1 for token in morph_slice if token.get("pos") == "PROPN")
    nouns = sum(1 for token in morph_slice if token.get("pos") == "NOUN")
    return propn, nouns


def _is_navigation_like(morph_slice: list[dict]) -> bool:
    """Return whether a token span looks like UI/navigation rather than a title.

    Example:
        >>> nav = [
        ...     {"text": "Donate", "pos": "VERB"},
        ...     {"text": "Create", "pos": "VERB"},
        ...     {"text": "account", "pos": "NOUN"},
        ...     {"text": "Log", "pos": "VERB"},
        ...     {"text": "in", "pos": "ADP"},
        ... ]
        >>> _is_navigation_like(nav)
        True
        >>> content = [
        ...     {"text": "Quarterly", "pos": "ADJ"},
        ...     {"text": "revenue", "pos": "NOUN"},
        ...     {"text": "increased", "pos": "VERB"},
        ... ]
        >>> _is_navigation_like(content)
        False
    """
    if not morph_slice:
        return True

    propn, nouns = _named_content_score(morph_slice)
    if propn >= 1:
        return False

    content_tokens = sum(
        1 for token in morph_slice if token.get("pos") in _CONTENT_POS
    )
    if content_tokens == 0:
        return True

    verbs = sum(1 for token in morph_slice if token.get("pos") == "VERB")
    if verbs >= 2 and nouns <= 1:
        return True

    adps = sum(1 for token in morph_slice if token.get("pos") == "ADP")
    if verbs >= 1 and adps >= 1 and nouns == 0:
        return True
    return False


def _is_boilerplate_sentence(
    text: str,
    morph_slice: list[dict] | None = None,
) -> bool:
    """Return whether text looks like UI/navigation noise rather than a title.

    Uses morphosyntax POS tags when available; otherwise length structure only.

    Example:
        >>> _is_boilerplate_sentence(
        ...     "Read edit view history",
        ...     [
        ...         {"text": "Read", "pos": "VERB"},
        ...         {"text": "edit", "pos": "VERB"},
        ...         {"text": "view", "pos": "VERB"},
        ...         {"text": "history", "pos": "NOUN"},
        ...     ],
        ... )
        True
        >>> _is_boilerplate_sentence("Quarterly revenue increased.")
        False
    """
    if morph_slice:
        return _is_navigation_like(morph_slice)

    tokens = _WORD_RE.findall(text)
    if not tokens:
        return True
    if any(len(token) >= 8 for token in tokens):
        return False
    return len(tokens) >= 3


def _is_low_value_ner_span(
    text: str,
    morph_slice: list[dict],
) -> bool:
    """Return whether an NER span is unlikely to be a document title.

    Example:
        >>> _is_low_value_ner_span(
        ...     "Rob Brown",
        ...     [{"text": "Rob", "pos": "PROPN"}, {"text": "Brown", "pos": "PROPN"}],
        ... )
        False
    """
    cleaned = (text or "").strip()
    if not cleaned or cleaned.isdigit():
        return True
    if morph_slice:
        return _is_navigation_like(morph_slice) or (
            sum(_named_content_score(morph_slice)) == 0
        )
    return not any(part[:1].isupper() for part in cleaned.split())


def _title_from_early_ner(
    tkeir_doc: dict,
    max_token_window: int,
) -> str:
    """Pick the earliest NER span whose POS tags look like a named title.

    Example:
        >>> doc = {
        ...     "content_morphosyntax": [
        ...         {"text": "Rob", "pos": "PROPN"},
        ...         {"text": "Brown", "pos": "PROPN"},
        ...     ],
        ...     "content_ner": [
        ...         {"start": 0, "end": 2, "label": "person", "text": "Rob Brown"},
        ...     ],
        ... }
        >>> _title_from_early_ner(doc, 120)
        'Rob Brown'
    """
    morphosyntax = tkeir_doc.get("content_morphosyntax") or []
    best: tuple[int, int, int, str] | None = None
    for span in tkeir_doc.get("content_ner") or []:
        start = int(span.get("start", 0))
        end = int(span.get("end", start))
        if start > max_token_window:
            continue
        text = (span.get("text") or "").strip()
        if not text or len(text.split()) > 12:
            continue
        morph_slice = _morphosyntax_slice(morphosyntax, start, end)
        if _is_low_value_ner_span(text, morph_slice):
            continue
        propn, nouns = _named_content_score(morph_slice)
        named_score = propn * 2 + nouns
        candidate = (start, -named_score, -len(text.split()), text)
        if best is None or candidate < best:
            best = candidate
    return best[3] if best else ""


def _sentence_spans(morphosyntax: list[dict]) -> list[tuple[int, int]]:
    """Return ``(start, end)`` token spans for each sentence.

    Example:
        >>> morph = [
        ...     {"text": "Hello", "is_sent_start": True},
        ...     {"text": "world", "is_sent_start": False},
        ...     {"text": "Again", "is_sent_start": True},
        ... ]
        >>> _sentence_spans(morph)
        [(0, 2), (2, 3)]
    """
    if not morphosyntax:
        return []
    starts = [0]
    for index, token in enumerate(morphosyntax):
        if index > 0 and token.get("is_sent_start"):
            starts.append(index)
    starts.append(len(morphosyntax))
    return [
        (starts[index], starts[index + 1]) for index in range(len(starts) - 1)
    ]


def _phrase_in_boilerplate_sentence(
    phrase: str,
    morphosyntax: list[dict],
) -> bool:
    """Return whether a keyword phrase only appears inside navigation-like text.

    Example:
        >>> morph = [
        ...     {"text": "Read", "pos": "VERB", "is_sent_start": True},
        ...     {"text": "edit", "pos": "VERB"},
        ...     {"text": "view", "pos": "VERB"},
        ...     {"text": "history", "pos": "NOUN"},
        ... ]
        >>> _phrase_in_boilerplate_sentence("edit view", morph)
        True
    """
    normalized = _WHITESPACE_RE.sub(" ", phrase.strip().lower())
    if not normalized:
        return True
    for start, end in _sentence_spans(morphosyntax):
        sentence = _sentence_text(morphosyntax, start, end)
        if normalized not in sentence.lower():
            continue
        if _is_boilerplate_sentence(
            sentence,
            _morphosyntax_slice(morphosyntax, start, end),
        ):
            return True
    return False


def _title_from_keywords(
    content_keywords: list[tuple],
    max_length: int,
    morphosyntax: list[dict] | None = None,
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
        if morphosyntax and _phrase_in_boilerplate_sentence(
            phrase, morphosyntax
        ):
            continue
        if _is_boilerplate_sentence(phrase):
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

    for start, end in _sentence_spans(morphosyntax):
        token_count = end - start
        if token_count < 3 or token_count > max_tokens:
            continue
        morph_slice = _morphosyntax_slice(morphosyntax, start, end)
        sentence = _sentence_text(morphosyntax, start, end)
        if not sentence or _is_boilerplate_sentence(sentence, morph_slice):
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

    morphosyntax = tkeir_doc.get("content_morphosyntax") or []
    for line in raw_text.splitlines():
        candidate = _WHITESPACE_RE.sub(" ", line).strip()
        if not candidate:
            continue
        word_count = len(candidate.split())
        if word_count < 2 or word_count > 16:
            continue
        morph_slice: list[dict] | None = None
        if (
            morphosyntax
            and candidate.lower()
            in " ".join(
                token.get("text", "") for token in morphosyntax
            ).lower()
        ):
            for start, end in _sentence_spans(morphosyntax):
                sentence = _sentence_text(morphosyntax, start, end)
                if candidate.lower() in sentence.lower():
                    morph_slice = _morphosyntax_slice(morphosyntax, start, end)
                    break
        if _is_boilerplate_sentence(candidate, morph_slice):
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

    morphosyntax = tkeir_doc.get("content_morphosyntax") or []
    candidates: list[tuple[int, str]] = []

    ner_title = _title_from_early_ner(tkeir_doc, max_ner_token_window)
    if ner_title:
        candidates.append((100, ner_title))

    keyword_title = _title_from_keywords(
        content_keywords or [],
        max_length,
        morphosyntax=morphosyntax,
    )
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
