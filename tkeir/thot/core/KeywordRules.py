"""Title: Keyword Rules

Shared keyword label validation rules for extraction and RAG export.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

DEFAULT_MIN_KEYWORD_LENGTH = 3


def is_valid_keyword_label(
    label: str,
    *,
    min_length: int = DEFAULT_MIN_KEYWORD_LENGTH,
) -> bool:
    """Return whether a keyword label meets the minimum character length.

    Args:
        label: Keyword text from extraction or ontology export.
        min_length: Minimum number of characters required after trimming.

    Returns:
        ``True`` when the label is long enough to be kept.

    Example:
        >>> is_valid_keyword_label("launch")
        True
        >>> is_valid_keyword_label("e", min_length=3)
        False
    """
    return len(label.strip()) >= max(1, min_length)
