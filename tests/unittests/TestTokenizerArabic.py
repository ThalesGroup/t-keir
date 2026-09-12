"""Title: Arabic Tokenizer

Arabic tokenization must use spaCy's blank Arabic pipeline, not Latin infix rules.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os

from thot.core.SpacyModelLoader import blank_model_name
from thot.core.ThotLogger import LogUserContext, ThotLogger
from thot.tasks.tokenizer.Tokenizer import (
    Tokenizer,
    uses_custom_latin_tokenizer,
)
from thot.tasks.tokenizer.TokenizerConfiguration import TokenizerConfiguration

ARABIC_TEXT = "الجيش اللبناني أعلن حالة التأهب في بيروت بعد الحادث."


def _flatten_token_strings(node) -> list[str]:
    """Collect token strings from nested tokenizer output.

    Example:
        >>> _flatten_token_strings([[[{"token": "a"}]]])
        ['a']
    """
    if isinstance(node, dict) and "token" in node:
        return [str(node["token"])]
    if isinstance(node, list):
        tokens: list[str] = []
        for item in node:
            tokens.extend(_flatten_token_strings(item))
        return tokens
    return []


def _resources_path() -> str:
    tests_dir = os.path.dirname(os.path.realpath(__file__))
    return os.path.abspath(
        os.path.join(tests_dir, "../../tkeir/resources/modeling/tokenizer/en")
    )


class TestTokenizerArabic:
    def setup_method(self):
        ThotLogger.loads({"logger": {"logging-level": "error"}})

    def test_latin_tokenizer_not_used_for_arabic(self):
        assert uses_custom_latin_tokenizer("ar") is False
        assert uses_custom_latin_tokenizer("fr") is True

    def test_arabic_tokens_are_words(self):
        config = TokenizerConfiguration()
        config.loads(
            {
                "logger": {"logging-level": "error"},
                "tokenizers": {
                    "segmenters": [
                        {
                            "language": "ar",
                            "resources-base-path": _resources_path(),
                            "normalization-rules": "tokenizer-rules.json",
                        }
                    ],
                },
            }
        )
        tokenizer = Tokenizer(
            config=config,
            call_context=LogUserContext("arabic-tokenizer-test"),
        )
        assert tokenizer._spacyTokenizer._spacy_model == blank_model_name("ar")
        document = tokenizer.tokenize(
            {
                "title": "",
                "content": [ARABIC_TEXT],
            }
        )
        tokens = _flatten_token_strings(document["content_tokens"])
        assert "الجيش" in tokens
        assert "اللبناني" in tokens
        assert "بيروت" in tokens
        assert document["error"] is False
