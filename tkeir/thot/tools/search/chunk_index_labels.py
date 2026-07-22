"""Title: Chunk index labels

Fixed protocol labels emitted by golden-chunk indexing (not document language).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re

# Labels written by ChunkBuilder._summarize_chunk — keep in sync with that task.
LABEL_ACTIVE_ENTITIES = "Active entities"
LABEL_UPCOMING_ENTITIES = "Upcoming entities"
LABEL_TOPIC = "Topic"
LABEL_PREVIOUS_CONTEXT = "Previous context"
LABEL_NEXT_FOCUS = "Next focus"
LABEL_CONTINUES_WITH = "Continues with"

CHUNK_CONTEXT_PREFIXES: tuple[str, ...] = (
    LABEL_ACTIVE_ENTITIES,
    LABEL_UPCOMING_ENTITIES,
    LABEL_TOPIC,
    LABEL_PREVIOUS_CONTEXT,
    LABEL_NEXT_FOCUS,
    LABEL_CONTINUES_WITH,
)


def is_chunk_protocol_sentence(sentence: str) -> bool:
    """Return whether a sentence starts with a chunk-indexing protocol label.

    Example:
        >>> is_chunk_protocol_sentence("Topic: critic Jon Landau regards song")
        True
        >>> is_chunk_protocol_sentence("Claudio Miranda is a cinematographer.")
        False
    """
    stripped = (sentence or "").strip()
    if not stripped:
        return False
    for prefix in CHUNK_CONTEXT_PREFIXES:
        if stripped.lower().startswith(f"{prefix.lower()}:"):
            return True
        if stripped.lower().startswith(prefix.lower()):
            return True
    return False


def strip_chunk_index_protocol(text: str) -> str:
    """Remove chunk-indexing protocol blocks from text for LLM prompts.

    Example:
        >>> sample = (
        ...     "Active entities: Taylor. Topic: critic regards song "
        ...     "George Harrison liked Abbey Road."
        ... )
        >>> cleaned = strip_chunk_index_protocol(sample)
        >>> "Active entities" not in cleaned
        True
        >>> "George Harrison" in cleaned
        True
    """
    cleaned = text or ""
    for prefix in (
        LABEL_ACTIVE_ENTITIES,
        LABEL_UPCOMING_ENTITIES,
        LABEL_PREVIOUS_CONTEXT,
        LABEL_NEXT_FOCUS,
        LABEL_CONTINUES_WITH,
    ):
        cleaned = re.sub(
            rf"{re.escape(prefix)}:[^.]*\.\s*",
            "",
            cleaned,
            flags=re.I,
        )
    cleaned = re.sub(
        rf"{re.escape(LABEL_TOPIC)}:\s*", "", cleaned, count=1, flags=re.I
    )
    cleaned = re.sub(r"\[\s*edit\s*\]", ". ", cleaned, flags=re.I)
    return cleaned.strip()
