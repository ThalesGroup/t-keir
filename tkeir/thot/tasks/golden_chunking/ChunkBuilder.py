# -*- coding: utf-8 -*-
"""Build semantic golden chunks from analyzed T-KEIR documents."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from thot.tools.search.chunk_index_labels import (
    LABEL_ACTIVE_ENTITIES,
    LABEL_CONTINUES_WITH,
    LABEL_NEXT_FOCUS,
    LABEL_PREVIOUS_CONTEXT,
    LABEL_TOPIC,
    LABEL_UPCOMING_ENTITIES,
)

_DEMONSTRATIVE_POS = frozenset({"DET", "PRON"})
_NOUN_LIKE_POS = frozenset({"NOUN", "PROPN"})


@dataclass(frozen=True)
class SentenceSpan:
    start: int
    end: int

    def token_count(self) -> int:
        """token_count API.

        Example:
            >>> from thot.tasks.golden_chunking.ChunkBuilder import SentenceSpan
            >>> SentenceSpan(2, 5).token_count()
            3
        """
        return self.end - self.start


@dataclass
class ChunkSettings:
    target_min_tokens: int = 300
    target_max_tokens: int = 500
    high_ner_density_max_tokens: int = 250
    ner_density_threshold: int = 3


def _join_tokens(tokens: list[dict], start: int, end: int) -> str:
    """Join tokens helper.

    Example:
        >>> tokens = [{'text': 'Hello'}, {'text': 'world'}]
        >>> _join_tokens(tokens, 0, 2)
        'Hello world'
    """
    return " ".join(token["text"] for token in tokens[start:end]).strip()


def extract_sentence_spans(morphosyntax: list[dict]) -> list[SentenceSpan]:
    """extract_sentence_spans API.

    Example:
        >>> morph = [
        ...     {'text': 'Hi', 'is_sent_start': True},
        ...     {'text': '.', 'is_sent_start': False},
        ...     {'text': 'Bye', 'is_sent_start': True},
        ... ]
        >>> spans = extract_sentence_spans(morph)
        >>> len(spans)
        2
    """
    if not morphosyntax:
        return []
    starts = [0]
    for index, token in enumerate(morphosyntax):
        if index > 0 and token.get("is_sent_start"):
            starts.append(index)
    sentences: list[SentenceSpan] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(morphosyntax)
        if end > start:
            sentences.append(SentenceSpan(start=start, end=end))
    return sentences


def _ner_density(ner_spans: list[dict], sentence: SentenceSpan) -> int:
    """Ner density helper.

    Example:
        >>> from thot.tasks.golden_chunking.ChunkBuilder import SentenceSpan
        >>> sentence = SentenceSpan(0, 3)
        >>> ner = [{'start': 0, 'end': 1, 'label': 'person'}, {'start': 1, 'end': 2, 'label': 'org'}]
        >>> _ner_density(ner, sentence)
        2
    """
    labels = set()
    for span in ner_spans:
        if span["start"] < sentence.end and span["end"] > sentence.start:
            labels.add(span["label"])
    return len(labels)


def _window_target_max(
    sentences: list[SentenceSpan],
    ner_spans: list[dict],
    start_index: int,
    end_index: int,
    settings: ChunkSettings,
) -> int:
    """Window target max helper.

    Example:
        >>> from thot.tasks.golden_chunking.ChunkBuilder import _window_target_max
        >>> callable(_window_target_max)
        True
    """
    densities = [
        _ner_density(ner_spans, sentences[index])
        for index in range(start_index, end_index)
    ]
    if densities and max(densities) >= settings.ner_density_threshold:
        return settings.high_ner_density_max_tokens
    return settings.target_max_tokens


def build_sentence_chunk_ranges(
    sentences: list[SentenceSpan],
    ner_spans: list[dict],
    settings: ChunkSettings,
) -> list[tuple[int, int]]:
    """build_sentence_chunk_ranges API.

    Example:
        >>> from thot.tasks.golden_chunking.ChunkBuilder import build_sentence_chunk_ranges
        >>> callable(build_sentence_chunk_ranges)
        True
    """
    if not sentences:
        return []

    ranges: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(sentences):
        token_count = 0
        end_index = cursor

        while end_index < len(sentences):
            target_max = _window_target_max(
                sentences, ner_spans, cursor, end_index + 1, settings
            )
            next_count = sentences[end_index].token_count()
            if token_count + next_count > target_max and end_index > cursor:
                break
            token_count += next_count
            end_index += 1
            if token_count >= settings.target_min_tokens:
                break

        if end_index == cursor:
            end_index = cursor + 1

        ranges.append((cursor, end_index))
        cursor = end_index
    return ranges


_NUMERIC_ENTITY_RE = re.compile(r"^-?\d+(?:[.,]\d+)?(?:\s+\d+)*%?$")
_ENTITY_LABEL_PRIORITY = (
    "person",
    "organization",
    "org",
    "company",
    "event",
    "facility",
    "product",
    "location",
    "gpe",
)


def _label_priority(label: str) -> int:
    """Label priority helper.

    Example:
        >>> _label_priority('person')
        0
    """
    normalized = str(label).lower()
    for index, preferred in enumerate(_ENTITY_LABEL_PRIORITY):
        if preferred in normalized:
            return index
    return len(_ENTITY_LABEL_PRIORITY)


def _is_noisy_entity_text(text: str) -> bool:
    """Noisy entity text helper.

    Example:
        >>> _is_noisy_entity_text('42')
        True
        >>> _is_noisy_entity_text('Alice')
        False
    """
    compact = str(text).strip().replace(" ", "")
    if not compact:
        return True
    if _NUMERIC_ENTITY_RE.match(compact):
        return True
    return compact.isdigit()


def _flatten_primary_entities(
    primary_entities: dict[str, list[str]],
    *,
    limit: int = 8,
) -> list[str]:
    """Rank entity texts for summaries, prioritizing people and organizations.

    Example:
        >>> _flatten_primary_entities({'person': ['Alice', 'Bob']})
        ['Alice', 'Bob']
    """
    ranked: list[tuple[int, str, str]] = []
    for label, values in primary_entities.items():
        priority = _label_priority(label)
        for value in values:
            text = str(value).strip()
            if not text or _is_noisy_entity_text(text):
                continue
            ranked.append((priority, text.lower(), text))

    ranked.sort(key=lambda item: (item[0], item[1]))
    selected: list[str] = []
    seen: set[str] = set()
    for _priority, key, value in ranked:
        if key in seen:
            continue
        seen.add(key)
        selected.append(value)
        if len(selected) >= limit:
            break
    return selected


def _triple_token_positions(triple: dict) -> list[int]:
    """Triple token positions helper.

    Example:
        >>> _triple_token_positions({
        ...     'subject': {'positions': [0, 1]},
        ...     'property': {'positions': [2]},
        ...     'value': {'positions': [3]},
        ... })
        [0, 1, 2, 3]
    """
    positions: list[int] = []
    for part in ("subject", "property", "value"):
        positions.extend((triple.get(part) or {}).get("positions", []))
    return positions


def _triples_for_token_range(
    kg: list[dict], start: int, end: int
) -> list[dict]:
    """Triples for token range helper.

    Example:
        >>> from thot.tasks.golden_chunking.ChunkBuilder import _triples_for_token_range
        >>> callable(_triples_for_token_range)
        True
    """
    selected = []
    for triple in kg:
        if triple.get("field_type") not in (None, "content"):
            continue
        if any(
            start <= position < end
            for position in _triple_token_positions(triple)
        ):
            selected.append(triple)
    return selected


def _format_svo_triplets(triples: list[dict]) -> list[list[str]]:
    """Format svo triplets helper.

    Example:
        >>> triples = [{'subject': {'content': ['Alice']}, 'property': {'content': ['built']}, 'value': {'content': ['parser']}}]
        >>> _format_svo_triplets(triples)
        [['Alice', 'built', 'parser']]
    """
    formatted = []
    for triple in triples:
        formatted.append(
            [
                " ".join(triple.get("subject", {}).get("content", [])),
                " ".join(triple.get("property", {}).get("content", [])),
                " ".join(triple.get("value", {}).get("content", [])),
            ]
        )
    return formatted


def _primary_entities(
    ner_spans: list[dict], start: int, end: int
) -> dict[str, list[str]]:
    """Primary entities helper.

    Example:
        >>> from thot.tasks.golden_chunking.ChunkBuilder import _primary_entities
        >>> callable(_primary_entities)
        True
    """
    entities: dict[str, list[str]] = {}
    for span in ner_spans:
        if span["start"] >= end or span["end"] <= start:
            continue
        label = span["label"]
        entities.setdefault(label, [])
        if span["text"] not in entities[label]:
            entities[label].append(span["text"])
    return entities


def _active_subject(triples: list[dict]) -> str:
    """Active subject helper.

    Example:
        >>> from thot.tasks.golden_chunking.ChunkBuilder import _active_subject
        >>> callable(_active_subject)
        True
    """
    for triple in reversed(triples):
        subject = " ".join(
            triple.get("subject", {}).get("content", [])
        ).strip()
        if subject:
            return subject
    return ""


def _implicit_reference_phrases(tokens: list[dict]) -> list[str]:
    """Implicit reference phrases helper.

    Example:
        >>> from thot.tasks.golden_chunking.ChunkBuilder import _implicit_reference_phrases
        >>> callable(_implicit_reference_phrases)
        True
    """
    phrases: list[str] = []
    for index, token in enumerate(tokens[:-1]):
        if token.get("pos") not in _DEMONSTRATIVE_POS:
            continue
        next_token = tokens[index + 1]
        if next_token.get("pos") not in _NOUN_LIKE_POS:
            continue
        phrase = (
            f"{token.get('text', '')} {next_token.get('text', '')}".strip()
        )
        if phrase and phrase not in phrases:
            phrases.append(phrase)
    return phrases


def _has_pronoun_token(tokens: list[dict]) -> bool:
    """Has pronoun token helper.

    Example:
        >>> _has_pronoun_token([{'pos': 'PRON', 'text': 'she'}])
        True
    """
    return any(token.get("pos") == "PRON" for token in tokens)


def _resolve_implicit_subjects(
    tokens: list[dict],
    triples: list[dict],
    carried_subject: str,
) -> list[str]:
    """Resolve implicit subjects helper.

    Example:
        >>> from thot.tasks.golden_chunking.ChunkBuilder import _resolve_implicit_subjects
        >>> callable(_resolve_implicit_subjects)
        True
    """
    implicit: list[str] = []
    subject = _active_subject(triples) or carried_subject

    if subject:
        for phrase in _implicit_reference_phrases(tokens):
            implicit.append(f"{phrase} -> {subject}")
        if _has_pronoun_token(tokens):
            implicit.append(subject)

    deduped: list[str] = []
    for item in implicit:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _summarize_chunk(
    text_raw: str,
    primary_entities: dict[str, list[str]],
    svo_triplets: list[list[str]],
    mode: str,
) -> str:
    """Summarize chunk helper.

    Example:
        >>> callable(_summarize_chunk)
        True
    """
    parts: list[str] = []
    flat_entities = _flatten_primary_entities(primary_entities)
    if flat_entities:
        label = (
            LABEL_UPCOMING_ENTITIES
            if mode == "after"
            else LABEL_ACTIVE_ENTITIES
        )
        parts.append(label + ": " + ", ".join(flat_entities))

    if svo_triplets:
        subject, verb, obj = svo_triplets[0]
        if mode == "after":
            parts.append(
                LABEL_NEXT_FOCUS
                + ": "
                + " ".join(
                    part for part in (subject, verb, obj) if part
                ).strip()
            )
        else:
            parts.append(
                LABEL_TOPIC
                + ": "
                + " ".join(
                    part for part in (subject, verb, obj) if part
                ).strip()
            )
    elif text_raw:
        snippet = " ".join(text_raw.split()[:18])
        if mode == "after":
            parts.append(LABEL_CONTINUES_WITH + ": " + snippet)
        else:
            parts.append(LABEL_PREVIOUS_CONTEXT + ": " + snippet)

    summary = ". ".join(part for part in parts if part).strip()
    if len(summary) > 320:
        return summary[:317] + "..."
    return summary


def _chunk_id(parent_doc_id: str, index: int, text_raw: str) -> str:
    """Chunk id helper.

    Example:
        >>> _chunk_id('doc.txt', 0, 'hello')
        'doc.txt#chunk-0-2cf24dba5f'
    """
    digest = hashlib.sha256(text_raw.encode("utf-8")).hexdigest()[:10]
    base = parent_doc_id or "document"
    if base.startswith("file://"):
        base = base[len("file://") :]
    return f"{base}#chunk-{index}-{digest}"


def _build_search_payload(
    text_raw: str, context_before: str, context_after: str
) -> str:
    """Build search payload helper.

    Example:
        >>> _build_search_payload('body', 'before', 'after')
        '[CONTEXT_BEFORE] before body [CONTEXT_AFTER] after'
    """
    payload = text_raw
    if context_before:
        payload = "[CONTEXT_BEFORE] " + context_before + " " + payload
    if context_after:
        payload = payload + " [CONTEXT_AFTER] " + context_after
    return payload.strip()


def build_golden_chunks(
    document: dict,
    settings: ChunkSettings | None = None,
) -> list[dict]:
    """Build golden chunks for the content field of an analyzed document.

    Example:
        >>> from thot.tasks.golden_chunking.ChunkBuilder import build_golden_chunks
        >>> callable(build_golden_chunks)
        True
    """
    settings = settings or ChunkSettings()
    morphosyntax = document.get("content_morphosyntax") or []
    ner_spans = document.get("content_ner") or []
    kg = document.get("kg") or []
    parent_doc_id = (
        document.get("source_doc_id") or document.get("source") or ""
    )

    sentences = extract_sentence_spans(morphosyntax)
    if not sentences:
        return []

    ranges = build_sentence_chunk_ranges(sentences, ner_spans, settings)
    chunk_specs: list[dict] = []
    carried_subject = ""

    for start_sentence, end_sentence in ranges:
        token_start = sentences[start_sentence].start
        token_end = sentences[end_sentence - 1].end
        chunk_tokens = morphosyntax[token_start:token_end]
        text_raw = _join_tokens(morphosyntax, token_start, token_end)
        triples = _triples_for_token_range(kg, token_start, token_end)
        svo_triplets = _format_svo_triplets(triples)
        primary_entities = _primary_entities(ner_spans, token_start, token_end)
        implicit_subjects = _resolve_implicit_subjects(
            chunk_tokens, triples, carried_subject
        )
        carried_subject = _active_subject(triples) or carried_subject
        chunk_specs.append(
            {
                "text_raw": text_raw,
                "primary_entities": primary_entities,
                "svo_triplets": svo_triplets,
                "implicit_subjects": implicit_subjects,
                "token_start": token_start,
                "token_end": token_end,
                "sentence_start": start_sentence,
                "sentence_end": end_sentence,
            }
        )

    chunks: list[dict] = []
    for index, spec in enumerate(chunk_specs):
        context_before = ""
        context_after = ""
        if index > 0:
            previous = chunk_specs[index - 1]
            context_before = _summarize_chunk(
                previous["text_raw"],
                previous["primary_entities"],
                previous["svo_triplets"],
                mode="before",
            )
        if index + 1 < len(chunk_specs):
            nxt = chunk_specs[index + 1]
            context_after = _summarize_chunk(
                nxt["text_raw"],
                nxt["primary_entities"],
                nxt["svo_triplets"],
                mode="after",
            )

        chunks.append(
            {
                "chunk_id": _chunk_id(parent_doc_id, index, spec["text_raw"]),
                "parent_doc_id": parent_doc_id,
                "text_raw": spec["text_raw"],
                "search_vector_payload": _build_search_payload(
                    spec["text_raw"], context_before, context_after
                ),
                "metadata": {
                    "implicit_subjects": spec["implicit_subjects"],
                    "primary_entities": spec["primary_entities"],
                    "svo_triplets": spec["svo_triplets"],
                    "context_summary_before": context_before,
                    "context_summary_after": context_after,
                    "token_start": spec["token_start"],
                    "token_end": spec["token_end"],
                    "sentence_start": spec["sentence_start"],
                    "sentence_end": spec["sentence_end"],
                },
            }
        )

    return chunks
