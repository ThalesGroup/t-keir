"""Title: SpaCy text normalizer for document-arm BM25 (lemma then optional asciifold).

Used at **ingestion** (``title_lemmatized`` / ``content_lemmatized``) and at
**query time** (document retrieval arm + ontology label index). Both paths MUST
call the helpers in this module so lexical matching stays consistent.

Order is critical: lemmatize **with** diacritics, then ASCII-fold when enabled.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import unicodedata
from typing import Any, Iterable

import spacy
from spacy.language import Language

from thot.tools.search.dual_hybrid_config import PreprocessingConfig

LOGGER = logging.getLogger(__name__)

# Cache TextNormalizer instances by (model, asciifold, min_len, drop_numbers).
_NORMALIZER_CACHE: dict[tuple[Any, ...], "TextNormalizer"] = {}


class TextNormalizer:
    """Lemmatize with spaCy, drop stopwords/noise, optionally ASCII-fold."""

    def __init__(
        self,
        model: str,
        *,
        extra_stopwords: set[str] | None = None,
        min_token_length: int = 3,
        drop_numbers: bool = True,
        asciifold: bool = True,
        disable: tuple[str, ...] = ("parser", "ner"),
        nlp: Language | None = None,
    ) -> None:
        """Load a spaCy model once for reuse.

        Args:
            model: spaCy model name (e.g. ``en_core_web_md``).
            extra_stopwords: Domain stopwords added to the model defaults.
            min_token_length: Drop lemmas shorter than this.
            drop_numbers: Drop ``like_num`` tokens when True.
            asciifold: When True, strip diacritics after lemmatization.
            disable: Pipeline components to disable for throughput.
            nlp: Optional pre-loaded Language (skips ``spacy.load``).
        """
        self.model = model
        self.min_token_length = min_token_length
        self.drop_numbers = drop_numbers
        self.asciifold_enabled = asciifold
        self.nlp: Language = nlp or spacy.load(model, disable=list(disable))
        if extra_stopwords:
            self.nlp.Defaults.stop_words |= set(extra_stopwords)
        LOGGER.info(
            "TextNormalizer ready model=%s min_len=%d drop_numbers=%s "
            "asciifold=%s",
            model,
            min_token_length,
            drop_numbers,
            asciifold,
        )

    @classmethod
    def for_language(
        cls,
        prep: PreprocessingConfig,
        language: str | None,
    ) -> TextNormalizer:
        """Build (or reuse) a normalizer for the detected language.

        Args:
            prep: Dual-hybrid preprocessing config.
            language: ISO language code from detection / request.

        Returns:
            Cached :class:`TextNormalizer` for the resolved spaCy model.
        """
        entry = prep.resolve_model(language)
        cache_key = (
            entry.model,
            prep.asciifold,
            prep.min_token_length,
            prep.drop_numbers,
            tuple(sorted(prep.extra_stopwords)),
        )
        cached = _NORMALIZER_CACHE.get(cache_key)
        if cached is not None:
            return cached
        normalizer = cls(
            entry.model,
            extra_stopwords=set(prep.extra_stopwords),
            min_token_length=prep.min_token_length,
            drop_numbers=prep.drop_numbers,
            asciifold=prep.asciifold,
        )
        _NORMALIZER_CACHE[cache_key] = normalizer
        return normalizer

    def normalize(self, text: str) -> str:
        """Lemmatize then optionally ASCII-fold a single string.

        This is the single code path used at index time and query time.
        """
        if not (text or "").strip():
            return ""
        doc = self.nlp(text)
        tokens = self._tokens_from_doc(doc)
        joined = " ".join(tokens)
        return self.asciifold(joined) if self.asciifold_enabled else joined

    def normalize_many(self, texts: Iterable[str]) -> list[str]:
        """Normalize many strings with ``nlp.pipe`` batching."""
        items = list(texts)
        if not items:
            return []
        out: list[str] = []
        for doc in self.nlp.pipe(items, batch_size=32):
            joined = " ".join(self._tokens_from_doc(doc))
            out.append(
                self.asciifold(joined) if self.asciifold_enabled else joined
            )
        return out

    def _tokens_from_doc(self, doc: Any) -> list[str]:
        tokens: list[str] = []
        for tok in doc:
            if tok.is_stop or tok.is_punct or tok.is_space:
                continue
            if self.drop_numbers and tok.like_num:
                continue
            lemma = (tok.lemma_ or "").lower().strip()
            if len(lemma) < self.min_token_length:
                continue
            tokens.append(lemma)
        return tokens

    @staticmethod
    def asciifold(text: str) -> str:
        """Strip combining marks after NFD decomposition."""
        decomposed = unicodedata.normalize("NFD", text)
        return "".join(
            char for char in decomposed if unicodedata.category(char) != "Mn"
        )


def document_language(document: dict[str, Any] | None) -> str:
    """Resolve language from a pipeline document (index-time).

    Prefers ``language-detection.language`` written by LanguageDetector.
    """
    if not document:
        return "en"
    nested = document.get("language-detection")
    if isinstance(nested, dict) and nested.get("language"):
        return str(nested["language"]).strip().lower() or "en"
    for key in ("lang", "language", "detected_language"):
        value = document.get(key)
        if value:
            return str(value).strip().lower() or "en"
    return "en"


def normalizer_for_language(language: str | None) -> TextNormalizer:
    """Shared factory: load preprocessing from ``rag.yaml`` and resolve model.

    Used by indexing and by DualHybridPipeline query path.
    """
    from thot.tools.search.rag_config import load_rag_config

    prep = load_rag_config().dual_hybrid.preprocessing
    return TextNormalizer.for_language(prep, language)


def normalize_document_fields(
    *,
    title: str,
    content: list[str] | str,
    language: str | None,
    normalizer: TextNormalizer | None = None,
) -> tuple[str, list[str]]:
    """Normalize title + content segments for Vespa lemmatized fields (index).

    Args:
        title: Raw document title.
        content: Raw content segments (array preserved 1:1).
        language: Detected language code.
        normalizer: Optional pre-built normalizer (tests / reuse).

    Returns:
        ``(title_lemmatized, content_lemmatized)``.
    """
    if isinstance(content, str):
        segments = [content]
    else:
        segments = [str(part) for part in (content or [])]
    nlp = normalizer or normalizer_for_language(language)
    title_lem = nlp.normalize(title or "")
    content_lem = nlp.normalize_many(segments)
    if (title or "").strip() and not title_lem:
        LOGGER.warning(
            "title_lemmatized empty after normalize language=%s model=%s",
            language,
            nlp.model,
        )
    nonempty_in = sum(1 for part in segments if (part or "").strip())
    nonempty_out = sum(1 for part in content_lem if part)
    if nonempty_in and not nonempty_out:
        LOGGER.warning(
            "content_lemmatized empty after normalize language=%s model=%s",
            language,
            nlp.model,
        )
    return title_lem, content_lem


def normalize_query_texts(
    texts: Iterable[str],
    *,
    language: str | None,
    normalizer: TextNormalizer | None = None,
) -> list[str]:
    """Normalize query / expansion strings for lemmatized Vespa fields (query).

    Same ``TextNormalizer.normalize`` path as :func:`normalize_document_fields`.
    """
    nlp = normalizer or normalizer_for_language(language)
    return [nlp.normalize(text) for text in texts if (text or "").strip()]
