"""Title: Rag report

RAG report assembly: structured answers, markdown export, highlight labels.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from thot.tools.search.ontology_utils import (
    _focus_query_terms,
    _is_metadata_sentence,
    _split_sentences,
    chunk_text_matches_query,
    extract_focus_passages,
    extract_query_highlight_terms,
    highlight_query_terms_in_chunks,
    prioritize_chunks_by_query_match,
)
from thot.tools.search.query_analyzer import content_terms_for_grounding
from thot.tools.search.vespa_client import clean_chunk_text_for_prompt

if TYPE_CHECKING:
    from thot.tools.search.app import FusedOntology, RetrievedChunk

_SHORT_ANSWER_MARKER = "SHORT_ANSWER:"
_DETAILED_REPORT_MARKER = "DETAILED_REPORT:"


def _format_document_name(parent_doc_id: str) -> str:
    """Return a short display name from a parent document URI.

    Example:
        >>> _format_document_name("file://tests/input/doc.pdf")
        'doc.pdf'
    """
    without_scheme = parent_doc_id.replace("file://", "")
    return without_scheme.split("/")[-1] or parent_doc_id


def is_unavailable_short_answer(
    short_answer: str, unavailable_answer: str
) -> bool:
    """Return whether the short answer is the configured unavailable fallback.

    Example:
        >>> is_unavailable_short_answer(
        ...     "The information is not available.",
        ...     "The information is not available.",
        ... )
        True
    """
    short = short_answer.strip().lower()
    if not short:
        return True
    unavailable = unavailable_answer.strip().lower()
    if not unavailable:
        return False
    return short == unavailable or unavailable in short


def chunks_matching_query(
    chunks: list[RetrievedChunk],
    query_text: str,
    *,
    content_terms: set[str] | list[str] | None = None,
) -> list[RetrievedChunk]:
    """Return retrieved chunks whose body contains at least one query term.

    Example:
        >>> from thot.tools.search.app import RetrievedChunk
        >>> chunk = RetrievedChunk(
        ...     chunk_id="c1",
        ...     text_raw="Charles Sutton Medal",
        ...     parent_doc_id="file://doc.pdf",
        ... )
        >>> chunks_matching_query([chunk], "Charles Sutton")[0].chunk_id
        'c1'
    """
    return [
        chunk
        for chunk in chunks
        if chunk_text_matches_query(
            query_text,
            chunk.text_raw,
            content_terms=content_terms,
        )
    ]


def _answer_terms(short_answer: str) -> set[str]:
    """Extract salient surface tokens from a short answer (no language lists).

    Example:
        >>> _answer_terms('George Harrison') == {'george', 'harrison'}
        True
    """
    terms: set[str] = set()
    for token in re.findall(
        r"[A-Za-z0-9][A-Za-z0-9'._-]{2,}", short_answer.lower()
    ):
        terms.add(token.strip("._-"))
    for word in re.findall(r"[A-Za-z][A-Za-z'._-]+", short_answer):
        if word[0].isupper():
            terms.add(word.lower().strip("._-"))
    return {term for term in terms if term}


def _year_tokens(text: str) -> set[str]:
    """Return four-digit year tokens (1500–2099) from ``text``."""
    return set(re.findall(r"\b((?:1[5-9]|20)\d{2})\b", text or ""))


def answer_supported_by_matching_chunks(
    short_answer: str,
    chunks: list[RetrievedChunk],
    query_text: str,
    *,
    unavailable_answer: str = "",
    language: str | None = None,
    pipeline_runner: Any | None = None,
    answer_morphosyntax: list[dict[str, Any]] | None = None,
    query_morphosyntax: list[dict[str, Any]] | None = None,
    query_content_terms: set[str] | None = None,
) -> bool:
    """Return whether the answer is grounded in query-matching chunks.

    Content terms come from UD morphosyntax (language-agnostic POS), not from
    language-specific stopword lists.

    Example:
        >>> from thot.tools.search.app import RetrievedChunk
        >>> chunk = RetrievedChunk(
        ...     chunk_id="c1",
        ...     text_raw='George Harrison liked "Something in the Way She Moves".',
        ...     parent_doc_id="file://doc.pdf",
        ... )
        >>> answer_supported_by_matching_chunks(
        ...     "George Harrison",
        ...     [chunk],
        ...     'Who liked "Something in the Way She Moves"',
        ...     answer_morphosyntax=[
        ...         {"text": "George", "lemma": "George", "pos": "PROPN"},
        ...         {"text": "Harrison", "lemma": "Harrison", "pos": "PROPN"},
        ...     ],
        ... )
        True
    """
    if is_unavailable_short_answer(short_answer, unavailable_answer):
        return False

    matching = chunks_matching_query(
        chunks, query_text, content_terms=query_content_terms
    )
    if not matching or not short_answer.strip():
        return False

    corpus = "\n".join(chunk.text_raw.lower() for chunk in matching)
    query_lower = (query_text or "").lower()

    # Years in the answer must appear in passages (or already in the query).
    for year in _year_tokens(short_answer):
        if year not in corpus and year not in query_lower:
            return False

    passage_answer = _passage_based_short_answer(query_text, matching)
    short_clean = short_answer.strip().lower()
    # When a compact who/what extract exists (e.g. a person name), longer LLM
    # answers that diverge must ground *every* novel content term — partial
    # overlap with the song/title still allows "name + invented detail".
    require_full_novel_grounding = False
    if passage_answer:
        passage_clean = passage_answer.strip().lower()
        if short_clean == passage_clean:
            return True
        is_compact_passage = (
            len(passage_clean.split()) <= 4
            and len(passage_answer.strip()) <= 48
        )
        if is_compact_passage:
            require_full_novel_grounding = True

    answer_content = content_terms_for_grounding(
        short_answer,
        morphosyntax=answer_morphosyntax,
        language=language,
        pipeline_runner=pipeline_runner,
        min_length=3,
    )
    if query_content_terms is not None:
        query_content = {t.lower() for t in query_content_terms}
    else:
        query_content = content_terms_for_grounding(
            query_text,
            morphosyntax=query_morphosyntax,
            language=language,
            pipeline_runner=pipeline_runner,
            min_length=3,
        )

    must_ground = sorted(answer_content - query_content)
    if must_ground:
        grounded = sum(1 for term in must_ground if term in corpus)
        threshold = 1.0 if require_full_novel_grounding else 0.85
        if grounded / len(must_ground) < threshold:
            # Soft accept only when overlap is already moderate and the answer
            # names a distinctive query entity present in passages. Blocks
            # near-zero overlap hallucinations (e.g. 1956 Suez Crisis).
            distinctive = {
                term
                for term in query_content
                if len(term) >= 4 and term in corpus and term in short_clean
            }
            if (
                distinctive
                and not require_full_novel_grounding
                and grounded / len(must_ground) >= 0.5
            ):
                return True
            return False
        return True

    answer_terms = _answer_terms(short_answer)
    if not answer_terms:
        return False
    if len(answer_terms) > 12:
        return False
    return any(term in corpus for term in answer_terms)


def _predicate_stem_variants(predicate: str) -> set[str]:
    """Return lowercase verb forms derived from a who-question predicate.

    Example:
        >>> "liked" in _predicate_stem_variants("like")
        True
    """
    stem = predicate.rstrip("e")
    return {
        form.lower()
        for form in {
            predicate,
            f"{predicate}s",
            f"{predicate}d",
            f"{predicate}ed",
            f"{predicate}ing",
            f"{stem}ed",
            f"{stem}ing",
        }
    }


def _extract_person_from_sentence(
    sentence: str,
    predicate: str | None = None,
) -> str | None:
    """Extract a person name from a focus sentence when possible.

    Uses capitalization structure and the query predicate — no fixed verb lists.

    Example:
        >>> _extract_person_from_sentence(
        ...     'George Harrison liked "Something" from the Beatles album Abbey Road.',
        ...     'like',
        ... )
        'George Harrison'
    """
    if predicate:
        for variant in sorted(
            _predicate_stem_variants(predicate), key=len, reverse=True
        ):
            name_match = re.search(
                rf"([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+)*)\s+{re.escape(variant)}\b",
                sentence,
                re.I,
            )
            if name_match:
                candidate = name_match.group(1).strip()
                if not _is_metadata_sentence(f"{candidate} is mentioned."):
                    return candidate

    patterns = (
        r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\s+([a-z][a-z'-]+)\b",
        r"\b([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+)+)\s+([a-z][a-z'-]+)\b",
    )
    best_name: str | None = None
    best_score = -999
    for pattern in patterns:
        for match in re.finditer(pattern, sentence):
            candidate = match.group(1).strip()
            if _is_metadata_sentence(f"{candidate} is mentioned."):
                continue
            verb = match.group(2).lower()
            score = 0
            if predicate and verb in _predicate_stem_variants(predicate):
                score += 10
            word_count = len(candidate.split())
            if word_count == 2:
                score += 5
            score -= word_count
            if score > best_score:
                best_score = score
                best_name = candidate
    if best_name:
        return best_name

    leading = re.match(
        r"^([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+)+)",
        sentence.strip(),
    )
    if leading:
        candidate = leading.group(1).strip()
        if not _is_metadata_sentence(f"{candidate} is mentioned."):
            return candidate
    return None


def _who_question_key_phrases(query_text: str) -> list[str]:
    """Return multi-word highlight phrases for a who-question."""
    return [
        label.lower()
        for label in extract_query_highlight_terms(query_text)
        if len(label.split()) >= 2
    ]


def _score_who_focus_sentence(
    sentence: str,
    *,
    predicate: str | None,
    terms: set[str],
    key_phrases: list[str],
) -> int | None:
    """Score a sentence for who-question focus ranking, or None if irrelevant."""
    if _is_metadata_sentence(sentence):
        return None
    sentence_lower = sentence.lower()
    if predicate and predicate in sentence_lower:
        return sum(1 for term in terms if term in sentence_lower)
    if key_phrases and any(phrase in sentence_lower for phrase in key_phrases):
        return 5 + sum(1 for term in terms if term in sentence_lower)
    return None


def _best_who_focus_sentence(
    matching: list[RetrievedChunk],
    query_text: str,
) -> tuple[str, str] | None:
    """Return the best who-question ``(chunk_id, sentence)`` pair when possible."""
    predicate = _who_predicate_token(query_text)
    terms = _focus_query_terms(query_text)
    key_phrases = _who_question_key_phrases(query_text)
    best: tuple[str, str] | None = None
    best_score = -999
    for chunk in matching:
        for sentence in _split_sentences(chunk.text_raw):
            score = _score_who_focus_sentence(
                sentence,
                predicate=predicate,
                terms=terms,
                key_phrases=key_phrases,
            )
            if score is None or score <= best_score:
                continue
            best_score = score
            best = (chunk.chunk_id, sentence.strip())
    return best


def _focus_sentence_from_passages(
    matching: list[RetrievedChunk],
    query_text: str,
) -> tuple[str, str] | None:
    """Return the top focus passage as a ``(chunk_id, sentence)`` pair."""
    focus = extract_focus_passages(
        [
            (
                chunk.chunk_id,
                clean_chunk_text_for_prompt(chunk.text_raw),
            )
            for chunk in matching
        ],
        query_text,
        max_passages=1,
    )
    if not focus or focus == "No focused passages identified.":
        return None
    line = focus.split("\n")[0].strip()
    match = re.match(r"- \[(.+?)\] (.+)", line)
    if match:
        return match.group(1), match.group(2).strip()
    chunk_id = matching[0].chunk_id if matching else ""
    return chunk_id, line.lstrip("- ").strip()


def _best_focus_sentence(
    matching: list[RetrievedChunk],
    query_text: str,
) -> tuple[str, str] | None:
    """Return the best ``(chunk_id, sentence)`` pair for the query.

    Example:
        >>> from thot.tools.search.app import RetrievedChunk
        >>> chunks = [RetrievedChunk(
        ...     chunk_id='c1',
        ...     text_raw='George Harrison liked the song.',
        ...     parent_doc_id='file://doc.pdf',
        ... )]
        >>> _best_focus_sentence(chunks, 'Who liked the song')
        ('c1', 'George Harrison liked the song.')
    """
    if re.match(r"^\s*who\b", query_text, re.I):
        who_best = _best_who_focus_sentence(matching, query_text)
        if who_best is not None:
            return who_best
    return _focus_sentence_from_passages(matching, query_text)


def _top_focus_sentence(
    matching: list[RetrievedChunk],
    query_text: str,
) -> tuple[str, str] | None:
    """Return the best ``(chunk_id, sentence)`` pair for the query.

    Example:
        >>> from thot.tools.search.rag_report import _top_focus_sentence
        >>> callable(_top_focus_sentence)
        True
    """
    return _best_focus_sentence(matching, query_text)


def _who_predicate_token(query_text: str) -> str | None:
    """Return the main verb/token immediately following a ``who`` question.

    Example:
        >>> _who_predicate_token('Who liked the song')
        'liked'
    """
    match = re.match(
        r"^\s*who\s+([A-Za-z][A-Za-z'._-]*)",
        query_text,
        re.I,
    )
    if not match:
        return None
    return match.group(1).lower()


def _subject_before_query_token(query_text: str, sentence: str) -> str | None:
    """Extract the subject that precedes a query verb/token in a focus sentence.

    Example:
        >>> _subject_before_query_token(
        ...     'Who liked the song',
        ...     'George Harrison liked the song.',
        ... )
        'George Harrison'
    """
    if re.match(r"^\s*who\b", query_text, re.I):
        predicate = _who_predicate_token(query_text)
        if predicate:
            name_match = re.search(
                rf"([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+)*)\s+{re.escape(predicate)}\b",
                sentence,
            )
            if name_match:
                return name_match.group(1).strip()
        return None

    for token in sorted(_focus_query_terms(query_text), key=len, reverse=True):
        match = re.search(rf"^(.+?)\s+{re.escape(token)}\b", sentence, re.I)
        if not match:
            continue
        subject = match.group(1).strip().strip("\"'")
        if subject and len(subject) > 1:
            return subject
    return None


def _passage_based_short_answer(
    query_text: str,
    matching: list[RetrievedChunk],
) -> str | None:
    """Build a concise answer from the top focus passage when possible.

    Example:
        >>> from thot.tools.search.app import RetrievedChunk
        >>> chunk = RetrievedChunk(
        ...     chunk_id="c1",
        ...     text_raw='George Harrison liked "Something in the Way She Moves".',
        ...     parent_doc_id="file://doc.pdf",
        ... )
        >>> _passage_based_short_answer(
        ...     'Who liked "Something in the Way She Moves"',
        ...     [chunk],
        ... )
        'George Harrison'
    """
    top = _top_focus_sentence(matching, query_text)
    if top is None:
        return None
    _chunk_id, sentence = top
    if re.match(r"^\s*who\b", query_text, re.I):
        predicate = _who_predicate_token(query_text)
        person = _extract_person_from_sentence(sentence, predicate)
        if person:
            return person
        subject = _subject_before_query_token(query_text, sentence)
        if subject:
            return subject
    clause = re.split(r"\s+so\s+|\.", sentence, maxsplit=1)[0].strip()
    return clause[:400] if clause else None


def build_chunk_evidence_answer(
    query_text: str,
    chunks: list[RetrievedChunk],
    *,
    content_terms: set[str] | list[str] | None = None,
) -> tuple[str, str] | None:
    """Build a chunk-grounded answer when the LLM returned unavailable.

    Args:
        query_text: Original user question.
        chunks: Retrieved chunks from Vespa.
        content_terms: Optional NLP content terms for matching (preferred).

    Returns:
        ``(short_answer, detailed_report)`` when query terms appear in chunks,
        otherwise ``None``.

    Example:
        >>> from thot.tools.search.app import RetrievedChunk
        >>> chunk = RetrievedChunk(
        ...     chunk_id="doc.pdf#chunk-1",
        ...     text_raw="Awards · Charles Sutton Medal · AFL",
        ...     parent_doc_id="file://tests/doc.pdf",
        ... )
        >>> short, _ = build_chunk_evidence_answer("Charles Sutton", [chunk])
        >>> "doc.pdf" in short
        True
    """
    matching = chunks_matching_query(
        chunks, query_text, content_terms=content_terms
    )
    if not matching:
        return None

    passage_answer = _passage_based_short_answer(query_text, matching)

    by_document: dict[str, list[RetrievedChunk]] = defaultdict(list)
    for chunk in matching:
        by_document[chunk.parent_doc_id].append(chunk)

    doc_lines: list[str] = []
    for parent_doc_id, doc_chunks in sorted(
        by_document.items(),
        key=lambda item: (
            -_document_top_relevance(item[1]),
            _format_document_name(item[0]).lower(),
        ),
    ):
        display_name = _format_document_name(parent_doc_id)
        chunk_ids = [
            (
                chunk.chunk_id.split("#")[-1]
                if "#" in chunk.chunk_id
                else chunk.chunk_id
            )
            for chunk in sorted(
                doc_chunks,
                key=lambda item: item.relevance or 0.0,
                reverse=True,
            )
        ]
        suffix = "s" if len(chunk_ids) != 1 else ""
        doc_lines.append(
            f"- **{display_name}** "
            f"({len(chunk_ids)} matching chunk{suffix}: "
            f"{', '.join(chunk_ids)})"
        )

    short_answer = passage_answer or (
        "The excerpts do not fully answer the question, but query terms appear "
        "in the following retrieved document(s):\n" + "\n".join(doc_lines)
    )
    if passage_answer and len(by_document) > 1:
        short_answer = f"{passage_answer}\n\nAlso mentioned in: " + ", ".join(
            _format_document_name(parent_doc_id)
            for parent_doc_id in by_document
        )
    elif passage_answer and doc_lines:
        short_answer = f"{passage_answer}\n\nSource: " + ", ".join(
            _format_document_name(parent_doc_id)
            for parent_doc_id in by_document
        )

    detailed_lines = [
        "## Detailed Analysis",
        "",
        "Retrieved chunks contain terms from your query. Relevant excerpts:",
        "",
    ]
    for chunk in prioritize_chunks_by_query_match(matching, query_text)[:8]:
        display_name = _format_document_name(chunk.parent_doc_id)
        excerpt = re.sub(r"\s+", " ", chunk.text_raw).strip()
        if len(excerpt) > 500:
            excerpt = f"{excerpt[:500].rstrip()}…"
        detailed_lines.append(
            f"- **{display_name}** — chunk `{chunk.chunk_id}` "
            f"(relevance: {_format_relevance(chunk.relevance)})"
        )
        detailed_lines.append(f"  {excerpt}")
        detailed_lines.append("")

    return short_answer, "\n".join(detailed_lines).strip()


def should_apply_chunk_evidence(
    short_answer: str,
    chunks: list[RetrievedChunk],
    query_text: str,
    unavailable_answer: str,
    *,
    detailed_report: str = "",
    language: str | None = None,
    pipeline_runner: Any | None = None,
    answer_morphosyntax: list[dict[str, Any]] | None = None,
    query_morphosyntax: list[dict[str, Any]] | None = None,
    query_content_terms: set[str] | None = None,
) -> bool:
    """Return whether to replace the LLM answer with chunk-grounded evidence.

    A long DETAILED_REPORT is not a grounding signal — only passage overlap is.
    ``detailed_report`` is kept for call-site compatibility.

    Example:
        >>> from thot.tools.search.app import RetrievedChunk
        >>> chunk = RetrievedChunk(
        ...     chunk_id="doc.pdf#c1",
        ...     text_raw="Charles Sutton Medal",
        ...     parent_doc_id="file://doc.pdf",
        ... )
        >>> should_apply_chunk_evidence(
        ...     "The information is not available.",
        ...     [chunk],
        ...     "Charles Sutton",
        ...     "The information is not available.",
        ... )
        True
    """
    _ = detailed_report
    matching = chunks_matching_query(
        chunks, query_text, content_terms=query_content_terms
    )
    if not matching:
        return False
    if is_unavailable_short_answer(short_answer, unavailable_answer):
        return True
    if answer_supported_by_matching_chunks(
        short_answer,
        chunks,
        query_text,
        unavailable_answer=unavailable_answer,
        language=language,
        pipeline_runner=pipeline_runner,
        answer_morphosyntax=answer_morphosyntax,
        query_morphosyntax=query_morphosyntax,
        query_content_terms=query_content_terms,
    ):
        return False
    return True


def apply_chunk_evidence_fallback(
    *,
    query_text: str,
    short_answer: str,
    detailed_report: str,
    chunks: list[RetrievedChunk],
    unavailable_answer: str,
    language: str | None = None,
    pipeline_runner: Any | None = None,
    answer_morphosyntax: list[dict[str, Any]] | None = None,
    query_morphosyntax: list[dict[str, Any]] | None = None,
    query_content_terms: set[str] | None = None,
) -> tuple[str, str, bool]:
    """Replace weak LLM answers when retrieved chunks contain query terms.

    Returns:
        ``(short_answer, detailed_report, used_chunk_evidence)``.

    Example:
        >>> from thot.tools.search.app import RetrievedChunk
        >>> chunk = RetrievedChunk(
        ...     chunk_id="doc.pdf#c1",
        ...     text_raw="Charles Sutton Medal",
        ...     parent_doc_id="file://doc.pdf",
        ... )
        >>> short, _, used = apply_chunk_evidence_fallback(
        ...     query_text="Charles Sutton",
        ...     short_answer="The information is not available.",
        ...     detailed_report="",
        ...     chunks=[chunk],
        ...     unavailable_answer="The information is not available.",
        ... )
        >>> used
        True
    """
    if not should_apply_chunk_evidence(
        short_answer,
        chunks,
        query_text,
        unavailable_answer,
        detailed_report=detailed_report,
        language=language,
        pipeline_runner=pipeline_runner,
        answer_morphosyntax=answer_morphosyntax,
        query_morphosyntax=query_morphosyntax,
        query_content_terms=query_content_terms,
    ):
        return short_answer, detailed_report, False

    evidence = build_chunk_evidence_answer(
        query_text,
        chunks,
        content_terms=query_content_terms,
    )
    if evidence is None:
        return short_answer, detailed_report, False
    short, detailed = evidence
    return short, detailed, True


def query_highlight_terms(
    query_text: str,
    chunks: list[RetrievedChunk],
    *,
    content_terms: set[str] | list[str] | None = None,
    morphosyntax: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Return query labels present in retrieved chunks for UI highlighting.

    Closed-class POS tokens (DET, PRON, CCONJ, …) are dropped when
    ``morphosyntax`` / ``content_terms`` from the NLP pipeline are provided.

    Example:
        >>> from thot.tools.search.app import RetrievedChunk
        >>> chunk = RetrievedChunk(
        ...     chunk_id="c1",
        ...     text_raw="Charles Sutton Medal",
        ...     parent_doc_id="doc",
        ... )
        >>> "Charles Sutton" in query_highlight_terms("Charles Sutton", [chunk])
        True
    """
    return highlight_query_terms_in_chunks(
        query_text,
        [chunk.text_raw for chunk in chunks],
        content_terms=content_terms,
        morphosyntax=morphosyntax,
    )


def _normalize_structured_markers(text: str) -> str:
    """Map markdown-style section headings to canonical parse markers.

    Example:
        >>> _normalize_structured_markers("**SHORT ANSWER:**\\nYes.")
        'SHORT_ANSWER:\\nYes.'
    """
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"(?i)\*{0,2}\s*SHORT\s+ANSWER", stripped):
            lines.append(_SHORT_ANSWER_MARKER)
            continue
        if re.match(r"(?i)\*{0,2}\s*DETAILED\s+REPORT", stripped):
            lines.append(_DETAILED_REPORT_MARKER)
            continue
        lines.append(line)
    return "\n".join(lines)


def parse_structured_generation(
    raw_text: str,
    *,
    unavailable_answer: str,
) -> tuple[str, str]:
    """Split an LLM response into a short answer and detailed report body.

    Args:
        raw_text: Raw model output expected to contain ``SHORT_ANSWER`` and
            ``DETAILED_REPORT`` sections.
        unavailable_answer: Fallback short answer when parsing fails.

    Returns:
        Tuple of ``(short_answer, detailed_report_markdown)``.

    Example:
        >>> text = "SHORT_ANSWER:\\nYes.\\n\\nDETAILED_REPORT:\\n## Detailed Analysis\\nMore."
        >>> short, detail = parse_structured_generation(text, unavailable_answer="N/A")
        >>> short
        'Yes.'
        >>> "## Detailed Analysis" in detail
        True
        >>> md = "**SHORT ANSWER:**\\nClaudio Miranda made the film.\\n\\n**DETAILED REPORT:**\\n## Filmography\\nDetails."
        >>> short, detail = parse_structured_generation(md, unavailable_answer="N/A")
        >>> short
        'Claudio Miranda made the film.'
        >>> "## Filmography" in detail
        True
    """
    cleaned = _normalize_structured_markers(raw_text.strip())
    if not cleaned:
        return unavailable_answer, ""

    upper = cleaned.upper()
    short_start = upper.find(_SHORT_ANSWER_MARKER)
    report_start = upper.find(_DETAILED_REPORT_MARKER)

    if short_start >= 0 and report_start > short_start:
        short_answer = cleaned[
            short_start + len(_SHORT_ANSWER_MARKER) : report_start
        ].strip()
        detailed_report = cleaned[
            report_start + len(_DETAILED_REPORT_MARKER) :
        ].strip()
        if short_answer:
            return short_answer, detailed_report

    if report_start >= 0:
        detailed_report = cleaned[
            report_start + len(_DETAILED_REPORT_MARKER) :
        ].strip()
        short_answer = cleaned[:report_start].strip() or unavailable_answer
        return short_answer, detailed_report

    paragraphs = [
        part.strip() for part in cleaned.split("\n\n") if part.strip()
    ]
    if not paragraphs:
        return unavailable_answer, ""
    if len(paragraphs) == 1:
        return paragraphs[0], ""
    return paragraphs[0], "\n\n".join(paragraphs[1:])


def extract_highlight_labels(
    ontology: dict[str, Any] | FusedOntology,
    *,
    max_entities: int = 20,
    max_keywords: int = 15,
    morphosyntax: list[dict[str, Any]] | None = None,
    content_terms: set[str] | list[str] | None = None,
    pipeline_runner: Any | None = None,
) -> tuple[list[str], list[str]]:
    """Return the most representative entity and keyword labels for highlighting.

    Single-token closed-class labels (DET / PRON / CCONJ / … such as ``and``)
    are dropped using UD morphosyntax from the query or a light NLP pass on
    the label itself.

    Example:
        >>> labels = extract_highlight_labels({
        ...     "entities": [{"label": "Acme", "type": "Company", "chunk_ids": ["c1", "c2"]}],
        ...     "keywords": [{"label": "launch", "chunk_ids": ["c1"]}],
        ... })
        >>> labels[0]
        ['Acme']
    """
    from thot.tools.search.query_analyzer import (
        content_terms_from_morphosyntax,
        morphosyntax_for_text,
    )
    from thot.tools.search.query_refiner import CLOSED_CLASS_POS

    entities = (
        ontology.get("entities", [])
        if isinstance(ontology, dict)
        else ontology.entities
    )
    keywords = (
        ontology.get("keywords", [])
        if isinstance(ontology, dict)
        else ontology.keywords
    )

    allowed: set[str] = {
        str(term).strip().lower()
        for term in content_terms or []
        if str(term).strip()
    }
    if morphosyntax:
        allowed |= {
            term.lower()
            for term in content_terms_from_morphosyntax(morphosyntax)
        }

    def _keep_label(raw: str) -> bool:
        label = raw.strip()
        if not label:
            return False
        parts = [
            part for part in re.findall(r"[A-Za-z0-9][A-Za-z0-9'._-]*", label)
        ]
        if not parts:
            return False
        # Multi-token phrases are kept (content spans).
        if len(parts) > 1:
            return True
        token = parts[0]
        key = token.lower()
        if allowed and key in allowed:
            return True
        # NLP pass on the label itself (DET/PRON/CCONJ → drop).
        label_morph = morphosyntax_for_text(
            token,
            pipeline_runner=pipeline_runner,
        )
        if label_morph:
            pos = str((label_morph[0] or {}).get("pos") or "").upper()
            if pos in CLOSED_CLASS_POS:
                return False
            return bool(content_terms_from_morphosyntax(label_morph))
        if (
            allowed
            and key not in allowed
            and token.isalpha()
            and token.islower()
        ):
            # Query morphosyntax saw this surface as non-content (e.g. "and").
            return False
        return True

    ranked_entities = sorted(
        entities,
        key=lambda item: (
            -len(
                item.get("chunk_ids", [])
                if isinstance(item, dict)
                else item.chunk_ids
            ),
            str(
                item.get("label", "") if isinstance(item, dict) else item.label
            ).lower(),
        ),
    )
    ranked_keywords = sorted(
        keywords,
        key=lambda item: (
            -len(
                item.get("chunk_ids", [])
                if isinstance(item, dict)
                else item.chunk_ids
            ),
            str(
                item.get("label", "") if isinstance(item, dict) else item.label
            ).lower(),
        ),
    )

    entity_labels = [
        str(
            item.get("label", "") if isinstance(item, dict) else item.label
        ).strip()
        for item in ranked_entities
        if _keep_label(
            str(
                item.get("label", "") if isinstance(item, dict) else item.label
            )
        )
    ][:max_entities]
    keyword_labels = [
        str(
            item.get("label", "") if isinstance(item, dict) else item.label
        ).strip()
        for item in ranked_keywords
        if _keep_label(
            str(
                item.get("label", "") if isinstance(item, dict) else item.label
            )
        )
    ][:max_keywords]
    return entity_labels, keyword_labels


def _format_relevance(relevance: float | None) -> str:
    """Format a Vespa relevance score for markdown display.

    Example:
        >>> _format_relevance(0.8123)
        '81.2%'
        >>> _format_relevance(None)
        'n/a'
    """
    if relevance is None:
        return "n/a"
    return f"{relevance * 100:.1f}%"


def _ontology_section_markdown(
    ontology: dict[str, Any] | FusedOntology,
) -> str:
    """Build the ontology section of a downloadable RAG report.

    Example:
        >>> md = _ontology_section_markdown({"entities": [], "keywords": []})
        >>> "## Key Entities" in md
        True
    """
    entities = (
        ontology.get("entities", [])
        if isinstance(ontology, dict)
        else ontology.entities
    )
    keywords = (
        ontology.get("keywords", [])
        if isinstance(ontology, dict)
        else ontology.keywords
    )

    grouped: dict[str, list[str]] = defaultdict(list)
    for entity in entities:
        label = str(
            entity.get("label", "")
            if isinstance(entity, dict)
            else entity.label
        ).strip()
        entity_type = str(
            entity.get("type", "") if isinstance(entity, dict) else entity.type
        ).strip()
        if label:
            grouped[entity_type or "Entity"].append(label)

    lines = ["## Key Entities", ""]
    if grouped:
        for entity_type in sorted(grouped):
            unique_labels = sorted(set(grouped[entity_type]), key=str.lower)
            lines.append(f"- **{entity_type}:** {', '.join(unique_labels)}")
    else:
        lines.append("- No named entities linked to retrieved chunks.")

    lines.extend(["", "## Key Keywords", ""])
    keyword_labels = sorted(
        {
            str(
                item.get("label", "") if isinstance(item, dict) else item.label
            ).strip()
            for item in keywords
            if str(
                item.get("label", "") if isinstance(item, dict) else item.label
            ).strip()
        },
        key=str.lower,
    )
    if keyword_labels:
        lines.append("- " + ", ".join(keyword_labels))
    else:
        lines.append("- No keywords linked to retrieved chunks.")

    return "\n".join(lines)


def _document_top_relevance(doc_chunks: list[RetrievedChunk]) -> float:
    """Return the highest relevance score within a document group.

    Example:
        >>> from thot.tools.search.app import RetrievedChunk
        >>> chunks = [RetrievedChunk(
        ...     chunk_id='c1',
        ...     text_raw='text',
        ...     parent_doc_id='file://doc.pdf',
        ...     relevance=0.9,
        ... )]
        >>> _document_top_relevance(chunks)
        0.9
    """
    return max((chunk.relevance or 0.0) for chunk in doc_chunks)


def _sources_section_markdown(chunks: list[RetrievedChunk]) -> str:
    """Build the retrieved-sources section of a downloadable RAG report.

    Example:
        >>> _sources_section_markdown([])
        '## Retrieved Sources\\n\\nNo chunks retrieved.'
    """
    lines = ["## Retrieved Sources", ""]
    if not chunks:
        lines.append("No chunks retrieved.")
        return "\n".join(lines)

    by_document: dict[str, list[RetrievedChunk]] = defaultdict(list)
    for chunk in chunks:
        by_document[chunk.parent_doc_id].append(chunk)

    for parent_doc_id, doc_chunks in sorted(
        by_document.items(),
        key=lambda item: (
            -_document_top_relevance(item[1]),
            _format_document_name(item[0]).lower(),
        ),
    ):
        display_name = _format_document_name(parent_doc_id)
        lines.append(f"### Document: `{display_name}`")
        lines.append("")
        lines.append(f"- Source URI: `{parent_doc_id}`")
        lines.append("")

        for chunk in sorted(
            doc_chunks,
            key=lambda item: item.relevance or 0.0,
            reverse=True,
        ):
            lines.append(
                f"#### Chunk `{chunk.chunk_id}` "
                f"(relevance: {_format_relevance(chunk.relevance)})"
            )
            lines.append("")
            excerpt = re.sub(r"\s+", " ", chunk.text_raw).strip()
            if len(excerpt) > 1200:
                excerpt = f"{excerpt[:1200].rstrip()}…"
            lines.append(f"> {excerpt}")
            lines.append("")

    return "\n".join(lines)


def build_fallback_detailed_report(
    *,
    focus_passages: str,
    chunk_excerpts: str,
) -> str:
    """Build a deterministic detailed report when the LLM body is empty.

    Example:
        >>> report = build_fallback_detailed_report(
        ...     focus_passages="- [c1] Fact one.",
        ...     chunk_excerpts="---\\nChunk body\\n---",
        ... )
        >>> "## Detailed Analysis" in report
        True
    """
    lines = [
        "## Detailed Analysis",
        "",
        "The following passages from retrieved chunks are most relevant to the query.",
        "",
    ]
    if (
        focus_passages.strip()
        and focus_passages != "No focused passages identified."
    ):
        lines.extend(["### Focus Passages", "", focus_passages, ""])
    if chunk_excerpts.strip():
        lines.extend(
            [
                "### Supporting Excerpts",
                "",
                "```text",
                chunk_excerpts,
                "```",
                "",
            ]
        )
    return "\n".join(lines).strip()


def format_input_prompt(system_prompt: str, user_prompt: str) -> str:
    """Combine system and user prompts for RAG result display.

    Example:
        >>> format_input_prompt("Be concise.", "Who is Alice?")
        '[SYSTEM]\\nBe concise.\\n\\n[USER]\\nWho is Alice?'
    """
    parts: list[str] = []
    if system_prompt.strip():
        parts.append("[SYSTEM]\n" + system_prompt.strip())
    if user_prompt.strip():
        parts.append("[USER]\n" + user_prompt.strip())
    return "\n\n".join(parts)


def assemble_report_markdown(
    *,
    query: str,
    language: str,
    short_answer: str,
    detailed_report: str,
    chunks: list[RetrievedChunk],
    ontology: dict[str, Any] | FusedOntology,
    vespa_hits: int,
    input_prompt: str = "",
    vespa_query: str = "",
) -> str:
    """Assemble the downloadable markdown report for a RAG query.

    Example:
        >>> from thot.tools.search.app import RetrievedChunk
        >>> report = assemble_report_markdown(
        ...     query="Who is Alice?",
        ...     language="en",
        ...     short_answer="Alice works at Acme.",
        ...     detailed_report="## Detailed Analysis\\nAlice is mentioned.",
        ...     chunks=[RetrievedChunk(chunk_id="c1", text_raw="Alice works at Acme.", parent_doc_id="doc")],
        ...     ontology={"entities": [], "keywords": []},
        ...     vespa_hits=1,
        ... )
        >>> "# T-KEIR RAG Report" in report
        True
    """
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    detailed = detailed_report.strip() or build_fallback_detailed_report(
        focus_passages="",
        chunk_excerpts="",
    )
    if not detailed.startswith("##"):
        detailed = f"## Detailed Analysis\n\n{detailed}"

    sections = [
        "# T-KEIR RAG Report",
        "",
        f"- **Generated:** {timestamp}",
        f"- **Language:** {language}",
        f"- **Vespa hits:** {vespa_hits}",
        "",
        "## Question",
        "",
        query.strip(),
        "",
        "## Short Answer",
        "",
        short_answer.strip(),
        "",
    ]
    # ``input_prompt`` and ``vespa_query`` stay on the API for the HMI
    # technical panel — keep them out of the downloadable report.
    _ = (input_prompt, vespa_query)
    sections.extend(
        [
            detailed,
            "",
            _ontology_section_markdown(ontology),
            "",
            _sources_section_markdown(chunks),
        ]
    )
    return "\n".join(sections).strip() + "\n"
