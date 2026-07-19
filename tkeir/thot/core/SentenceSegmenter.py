"""Language-aware sentence segmentation using pySBD."""

from __future__ import annotations

import re

import pysbd

# Languages supported by pySBD (ISO 639-1 codes).
PYSBD_SUPPORTED_LANGUAGES = {
    "am",
    "ar",
    "bg",
    "da",
    "de",
    "el",
    "en",
    "es",
    "et",
    "fa",
    "fi",
    "fr",
    "hi",
    "hy",
    "id",
    "it",
    "ja",
    "kk",
    "mr",
    "nl",
    "pl",
    "ru",
    "ur",
    "zh",
}

_SENTENCE_END_RE = re.compile(r'[.!?]["\']?\s*$')
_CONTINUATION_TAIL_RE = re.compile(
    r"(?:[,;:]\s*$|\b(?:with|and|or|the|a|an|to|for|of|in|on|at|by|as|from|"
    r"into|that|which|who|whose|where|when|while|but|if|because|although|"
    r"though|after|before|during|until|unless|since|than|so|yet|nor|not|is|"
    r"are|was|were|be|been|being|have|has|had|do|does|did|will|would|could|"
    r"should|may|might|must|shall|can|need|dare|ought|used)\s*$)",
    re.IGNORECASE,
)
_IMAGE_MARKER_RE = re.compile(
    r"^\[(?:Image|Scanned) page \d+\]", re.IGNORECASE
)


def normalize_language_code(language: str | None) -> str:
    """Normalize a locale code to a two-letter ISO 639-1 language code.

    Args:
        language: Locale or language code such as ``"fr-FR"``.

    Returns:
        Lower-case language code, defaulting to ``"en"`` when absent.

    Example:
        >>> from thot.core.SentenceSegmenter import normalize_language_code
        >>> normalize_language_code("fr-FR")
        'fr'
        >>> normalize_language_code(None)
        'en'
    """
    if not language:
        return "en"
    return language.lower().split("-")[0]


def pysbd_language(language: str | None) -> str:
    """Return a pySBD-supported language code with English fallback.

    Args:
        language: Requested language or locale code.

    Returns:
        Supported pySBD language code.

    Example:
        >>> from thot.core.SentenceSegmenter import pysbd_language
        >>> pysbd_language("fr")
        'fr'
        >>> pysbd_language("xx")
        'en'
    """
    code = normalize_language_code(language)
    if code in PYSBD_SUPPORTED_LANGUAGES:
        return code
    return "en"


def _collapse_inline_whitespace(text: str) -> str:
    """Collapse repeated whitespace and trim a text fragment.

    Args:
        text: Input text.

    Returns:
        Single-spaced trimmed text.

    Example:
        >>> from thot.core.SentenceSegmenter import _collapse_inline_whitespace
        >>> _collapse_inline_whitespace("  hello   world  ")
        'hello world'
    """
    return re.sub(r"\s+", " ", text).strip()


def _split_layout_blocks(text: str) -> list[str]:
    """Split text on page or paragraph boundaries from PDF or OCR output.

    Args:
        text: Raw extracted document text.

    Returns:
        Layout blocks with soft line breaks merged into paragraphs.

    Example:
        >>> from thot.core.SentenceSegmenter import _split_layout_blocks
        >>> _split_layout_blocks("Line one\\n\\nLine two")
        ['Line one', 'Line two']
    """
    normalized = text.replace("\f", "\n\n")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    blocks = []
    for block in re.split(r"\n\s*\n", normalized):
        block = re.sub(r"(?<!\n)\n(?!\n)", " ", block)
        block = _collapse_inline_whitespace(block)
        if block:
            blocks.append(block)
    return blocks


def _looks_like_table_fragment(text: str) -> bool:
    """Detect short infobox or table cells interleaved in PDF text.

    Args:
        text: Candidate layout block.

    Returns:
        ``True`` when the block looks like a table fragment.

    Example:
        >>> from thot.core.SentenceSegmenter import _looks_like_table_fragment
        >>> _looks_like_table_fragment("Production")
        True
        >>> _looks_like_table_fragment("This is a full sentence.")
        False
    """
    if _SENTENCE_END_RE.search(text):
        return False
    if _IMAGE_MARKER_RE.match(text):
        return False
    words = text.split()
    if len(words) > 6:
        return False
    if len(words) == 1:
        word = words[0]
        if word.isupper() and len(word) <= 6:
            return True
        if word.isalpha() and word.islower() and len(word) <= 12:
            return True
        if word[0].isupper() and word.isalpha() and len(word) <= 14:
            return True
    if len(words) <= 4 and all(
        word[0].isupper() or word.isupper() for word in words if word
    ):
        return True
    return False


def _should_merge_prose(previous: str, current: str) -> bool:
    """Return whether two prose blocks should be merged.

    Args:
        previous: Earlier layout block.
        current: Following layout block.

    Returns:
        ``True`` when the blocks belong to the same sentence or paragraph.

    Example:
        >>> from thot.core.SentenceSegmenter import _should_merge_prose
        >>> _should_merge_prose("This continues", "with more text")
        True
        >>> _should_merge_prose("Sentence ends.", "New sentence")
        False
    """
    if not previous or not current:
        return False
    if previous.endswith("-"):
        return True
    if _SENTENCE_END_RE.search(previous):
        return False
    if _CONTINUATION_TAIL_RE.search(previous):
        return True
    if current[0].islower():
        return True
    return False


def _merge_layout_blocks(blocks: list[str]) -> list[str]:
    """Rebuild prose paragraphs broken apart by PDF layout extraction.

    Args:
        blocks: Layout blocks produced by ``_split_layout_blocks``.

    Returns:
        Merged paragraph strings ready for sentence segmentation.

    Example:
        >>> from thot.core.SentenceSegmenter import _merge_layout_blocks
        >>> _merge_layout_blocks(["There was a bidding", "war for the show"])
        ['There was a bidding war for the show']
    """
    paragraphs: list[str] = []
    prose_buffer = ""

    for block in blocks:
        if _looks_like_table_fragment(block):
            paragraphs.append(block)
            continue

        if not prose_buffer:
            prose_buffer = block
            continue

        if prose_buffer.endswith("-"):
            if _looks_like_table_fragment(block) or (
                block and block[0].isupper()
            ):
                paragraphs.append(block)
                continue
            prose_buffer = prose_buffer + block
            continue

        if _should_merge_prose(prose_buffer, block):
            prose_buffer = prose_buffer + " " + block
        else:
            paragraphs.append(prose_buffer)
            prose_buffer = block

    if prose_buffer:
        paragraphs.append(prose_buffer)
    return paragraphs


def prepare_text_for_segmentation(text: str) -> list[str]:
    """Normalize PDF or OCR layout artifacts before sentence splitting.

    Args:
        text: Raw extracted document text.

    Returns:
        Paragraph strings ready for sentence segmentation.

    Example:
        >>> from thot.core.SentenceSegmenter import prepare_text_for_segmentation
        >>> prepare_text_for_segmentation("Wraps here\\nonto next line.")
        ['Wraps here onto next line.']
    """
    return _merge_layout_blocks(_split_layout_blocks(text))


def _consolidate_footnotes(sentences: list[str]) -> list[str]:
    """Merge standalone footnote markers into the previous sentence.

    Args:
        sentences: Candidate sentence strings.

    Returns:
        Sentences with inline footnote markers consolidated.

    Example:
        >>> from thot.core.SentenceSegmenter import _consolidate_footnotes
        >>> _consolidate_footnotes(["See note.", "[1]"])
        ['See note[1]']
    """
    merged: list[str] = []
    for sentence in sentences:
        stripped = sentence.strip()
        if merged and re.fullmatch(r"\[\d+\]\.?", stripped):
            merged[-1] = merged[-1].rstrip(".") + stripped
        else:
            merged.append(sentence)
    return merged


class SentenceSegmenter:
    """Split text into sentences using pySBD rules for the given language."""

    def __init__(self, language: str | None = "en"):
        """Create a language-aware sentence segmenter.

        Args:
            language: Requested language or locale code.

        Example:
            >>> from thot.core.SentenceSegmenter import SentenceSegmenter
            >>> segmenter = SentenceSegmenter("fr")
            >>> segmenter.language
            'fr'
        """
        self.language = pysbd_language(language)
        self._segmenter = pysbd.Segmenter(language=self.language, clean=False)

    def segment(self, text: str) -> list[str]:
        """Split text into sentences.

        Args:
            text: Input document text.

        Returns:
            Ordered list of sentence strings.

        Example:
            >>> from thot.core.SentenceSegmenter import SentenceSegmenter
            >>> segmenter = SentenceSegmenter("en")
            >>> segmenter.segment("Hello world. Second sentence.")
            ['Hello world. ', 'Second sentence.']
        """
        if not text or not text.strip():
            return []
        sentences: list[str] = []
        for paragraph in prepare_text_for_segmentation(text):
            if _looks_like_table_fragment(paragraph):
                sentences.append(paragraph)
                continue
            sentences.extend(self._segmenter.segment(paragraph))
        return _consolidate_footnotes(sentences)
