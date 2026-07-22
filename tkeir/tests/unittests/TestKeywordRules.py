"""Title: Keyword Rules

Tests for shared keyword label validation.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.core.KeywordRules import (
    DEFAULT_MIN_KEYWORD_LENGTH,
    is_valid_keyword_label,
)


def test_default_min_keyword_length_is_three():
    assert DEFAULT_MIN_KEYWORD_LENGTH == 3


def test_is_valid_keyword_label_rejects_single_letter():
    assert not is_valid_keyword_label("e", min_length=3)
    assert is_valid_keyword_label("end", min_length=3)
