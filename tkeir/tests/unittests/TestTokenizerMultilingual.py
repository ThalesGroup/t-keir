# -*- coding: utf-8 -*-
"""Complex multilingual tokenizer integration tests."""

from __future__ import annotations

import copy
import os

import pytest

pytestmark = pytest.mark.slow

from thot.core.SentenceSegmenter import SentenceSegmenter, pysbd_language
from thot.core.SpacyModelLoader import MULTILINGUAL_MODEL
from thot.core.ThotLogger import LogUserContext, ThotLogger
from thot.tasks.tokenizer.Tokenizer import Tokenizer
from thot.tasks.tokenizer.TokenizerConfiguration import TokenizerConfiguration


def _resources_path() -> str:
    tests_dir = os.path.dirname(os.path.realpath(__file__))
    return os.path.abspath(
        os.path.join(tests_dir, "../../resources/modeling/tokenizer/en")
    )


def _base_config(language: str) -> dict:
    return {
        "logger": {"logging-level": "error"},
        "tokenizers": {
            "segmenters": [
                {
                    "language": language,
                    "resources-base-path": _resources_path(),
                    "normalization-rules": "tokenizer-rules.json",
                }
            ],
        },
    }


def _flatten_sentence_tokens(content_tokens: list) -> list[str]:
    return [
        token["token"]
        for paragraph in content_tokens
        for block in paragraph
        for sentence in block
        for token in sentence
    ]


def _sentence_token_lists(content_tokens: list) -> list[list[str]]:
    sentences: list[list[str]] = []
    for paragraph in content_tokens:
        for block in paragraph:
            for sentence in block:
                sentences.append([token["token"] for token in sentence])
    return sentences


def _count_sentences(content_tokens: list) -> int:
    return sum(
        len(block) for paragraph in content_tokens for block in paragraph
    )


def _validate_title_token_structure(title_tokens: list) -> None:
    for sentence in title_tokens:
        starts = [token["start_sentence"] for token in sentence]
        if sum(1 for flag in starts if flag) != 1:
            raise AssertionError(
                "Each title sentence must have exactly one start_sentence token"
            )
        for token in sentence:
            if not {"token", "start_sentence", "mwe"} <= set(token):
                raise AssertionError(
                    "Malformed title token entry: " + str(token)
                )


def _validate_content_token_structure(content_tokens: list) -> None:
    for paragraph in content_tokens:
        for block in paragraph:
            for sentence in block:
                starts = [token["start_sentence"] for token in sentence]
                self_assert = sum(1 for flag in starts if flag)
                if self_assert != 1:
                    raise AssertionError(
                        "Each sentence must have exactly one start_sentence token"
                    )
                for token in sentence:
                    if not {"token", "start_sentence", "mwe"} <= set(token):
                        raise AssertionError(
                            "Malformed token entry: " + str(token)
                        )
                    if "is-compound" not in token["mwe"]:
                        raise AssertionError("Missing mwe.is-compound flag")


class MultilingualFixture:
    def __init__(
        self,
        language: str,
        title: str,
        paragraphs: list[list[str]],
        expected_model: str,
        expected_pysbd_sentences: int,
        must_contain_tokens: list[str],
        first_sentence_prefix: list[str] | None = None,
    ):
        self.language = language
        self.title = title
        self.paragraphs = paragraphs
        self.expected_model = expected_model
        self.expected_pysbd_sentences = expected_pysbd_sentences
        self.must_contain_tokens = must_contain_tokens
        self.first_sentence_prefix = first_sentence_prefix


MULTILINGUAL_FIXTURES: dict[str, MultilingualFixture] = {
    "en": MultilingualFixture(
        language="en",
        title="Access to UBSWenergy Production Environment",
        paragraphs=[
            [
                (
                    "Dr. Smith emailed user@example.com at 3:30 p.m.; "
                    "visit https://example.org/path?q=1. "
                    'He said: "Wait—really?" '
                    "The cost is $1,234.56."
                ),
                (
                    " this is a __underscored text__ with _ and __ to use a "
                    "sp_lit. stars for news * research and development * list."
                ),
            ]
        ],
        expected_model="en_core_web_sm",
        expected_pysbd_sentences=4,
        must_contain_tokens=[
            "Dr.",
            "Smith",
            "user@example.com",
            "3:30",
            "p.m.",
            "https:",
            "example.org",
            "Wait—really",
            "$",
            "234.56",
            "_",
            "underscored",
            "sp_lit",
            "*",
            "development",
        ],
        first_sentence_prefix=["Dr.", "Smith", "emailed", "user@example.com"],
    ),
    "fr": MultilingualFixture(
        language="fr",
        title="Accès à l'environnement de production",
        paragraphs=[
            [
                (
                    "M. Dupont est arrivé à Paris. "
                    "L'intelligence artificielle transforme l'Europe ! "
                    "Contact : contact@exemple.fr ; le prix est de 1 234,56 €."
                ),
                (
                    "Les chercheurs du MRC Laboratory of Molecular Biology "
                    "ont publié leurs résultats ; voir https://exemple.fr/a=b."
                ),
            ]
        ],
        expected_model="fr_core_news_sm",
        expected_pysbd_sentences=3,
        must_contain_tokens=[
            "M.",
            "Dupont",
            "Paris",
            "intelligence",
            "artificielle",
            "Europe",
            "contact@exemple.fr",
            "234",
            "56",
            "€",
            "Laboratory",
            "https:",
        ],
        first_sentence_prefix=["M.", "Dupont", "est", "arrivé"],
    ),
    "de": MultilingualFixture(
        language="de",
        title="Zugang zur Produktionsumgebung",
        paragraphs=[
            [
                (
                    "Prof. Müller erklärte z.B. die "
                    "Donaudampfschifffahrtsgesellschaftskapitänspension. "
                    "Besuchen Sie https://beispiel.de! "
                    "Kosten: 1.234,56 €."
                ),
            ]
        ],
        expected_model=MULTILINGUAL_MODEL,
        expected_pysbd_sentences=3,
        must_contain_tokens=[
            "Prof",
            "Müller",
            "z.",
            "B.",
            "Donaudampfschifffahrtsgesellschaftskapitänspension",
            "https:",
            "beispiel.de",
            "1.234",
            "€",
        ],
        first_sentence_prefix=["Prof", ".", "Müller", "erklärte"],
    ),
    "es": MultilingualFixture(
        language="es",
        title="Acceso al entorno de producción",
        paragraphs=[
            [
                (
                    "¿Cómo está usted? "
                    "El Dr. García visitó Madrid. "
                    "¡Qué sorpresa! "
                    "Email: user@ejemplo.es."
                ),
            ]
        ],
        expected_model=MULTILINGUAL_MODEL,
        expected_pysbd_sentences=4,
        must_contain_tokens=[
            "¿",
            "Cómo",
            "está",
            "Dr",
            "García",
            "Madrid",
            "¡",
            "Qué",
            "user@ejemplo.es",
        ],
        first_sentence_prefix=["¿", "Cómo", "está"],
    ),
    "it": MultilingualFixture(
        language="it",
        title="Accesso all'ambiente di produzione",
        paragraphs=[
            [
                (
                    "Il Prof. Rossi disse: «L'Italia è bella.» "
                    "Visitate https://esempio.it; costo: 1.234,56 €."
                ),
            ]
        ],
        expected_model=MULTILINGUAL_MODEL,
        expected_pysbd_sentences=1,
        must_contain_tokens=[
            "Prof",
            "Rossi",
            "L'Italia",
            "bella",
            "https:",
            "esempio.it",
            "1.234",
            "€",
        ],
        first_sentence_prefix=["Il", "Prof", ".", "Rossi"],
    ),
    "zh": MultilingualFixture(
        language="zh",
        title="生产环境访问",
        paragraphs=[
            [
                (
                    "王先生说：「人工智能很重要。」"
                    "请访问 https://example.cn ；价格是 1,234.56 元。"
                ),
            ]
        ],
        expected_model=MULTILINGUAL_MODEL,
        expected_pysbd_sentences=1,
        must_contain_tokens=[
            "王先生说",
            "人工智能",
            "https:",
            "example.cn",
            "234.56",
            "元",
        ],
        first_sentence_prefix=None,
    ),
    "sv": MultilingualFixture(
        language="sv",
        title="Åtkomst till produktionsmiljön",
        paragraphs=[
            [
                (
                    'Prof. Andersson sa: "AI är viktigt." '
                    "Besök https://exempel.se; priset är 1 234,56 kr."
                ),
            ]
        ],
        expected_model=MULTILINGUAL_MODEL,
        expected_pysbd_sentences=2,
        must_contain_tokens=[
            "Prof",
            "Andersson",
            "viktigt",
            "https:",
            "exempel.se",
            "234",
            "56",
            "kr",
        ],
        first_sentence_prefix=["Prof", ".", "Andersson", "sa"],
    ),
}


class TestTokenizerMultilingual:
    log_context = LogUserContext("multilingual-tokenizer-test")

    @classmethod
    def setup_class(cls):
        ThotLogger.loads({"logger": {"logging-level": "error"}})

    def _make_tokenizer(self, language: str) -> Tokenizer:
        config = TokenizerConfiguration()
        config.loads(_base_config(language))
        return Tokenizer(config=config, call_context=self.log_context)

    def _tokenize_fixture(self, fixture: MultilingualFixture) -> dict:
        tokenizer = self._make_tokenizer(fixture.language)
        document = {
            "data_source": "tokenizer-multilingual-test",
            "source_doc_id": "file://multilingual.txt",
            "title": fixture.title,
            "content": fixture.paragraphs,
        }
        return tokenizer.tokenize(document, call_context=self.log_context)

    def test_multilingual_complex_corpus(self):
        """End-to-end tokenization across languages with rich text."""
        for language, fixture in MULTILINGUAL_FIXTURES.items():
            result = self._tokenize_fixture(fixture)
            assert not result.get("error")
            assert "content_tokens" in result
            assert "title_tokens" in result
            _validate_content_token_structure(result["content_tokens"])
            _validate_title_token_structure(result["title_tokens"])

            tokenizer = self._make_tokenizer(language)
            assert (
                tokenizer._spacyTokenizer._spacy_model
                == fixture.expected_model
            )
            assert (
                tokenizer._spacyTokenizer._sent_segmenter.language
                == pysbd_language(language)
            )

            primary_text = fixture.paragraphs[0][0]
            pysbd_count = len(
                SentenceSegmenter(language).segment(primary_text)
            )
            assert pysbd_count == fixture.expected_pysbd_sentences
            assert (
                len(result["content_tokens"][0][0])
                == fixture.expected_pysbd_sentences
            )

            flat_tokens = _flatten_sentence_tokens(result["content_tokens"])
            for expected_token in fixture.must_contain_tokens:
                token_found = expected_token in flat_tokens or any(
                    expected_token in token for token in flat_tokens
                )
                assert token_found

            if fixture.first_sentence_prefix:
                first_sentence = result["content_tokens"][0][0][0]
                first_tokens = [t["token"] for t in first_sentence]
                assert (
                    first_tokens[: len(fixture.first_sentence_prefix)]
                    == fixture.first_sentence_prefix
                )
            assert len(result["title_tokens"][0]) > 0

    def test_english_detailed_sentence_and_url_boundaries(self):
        """English: abbreviations, URL query strings, quotes, currency."""
        fixture = MULTILINGUAL_FIXTURES["en"]
        result = self._tokenize_fixture(fixture)
        sentences = _sentence_token_lists(result["content_tokens"])

        assert len(sentences) == 6
        assert sentences[0][:4] == [
            "Dr.",
            "Smith",
            "emailed",
            "user@example.com",
        ]
        assert sentences[1] == ["q=1", "."]
        assert sentences[2][:3] == ["He", "said", ":"]
        assert "Wait—really" in sentences[2]
        assert sentences[3][:4] == ["The", "cost", "is", "$"]
        assert sentences[3][-2:] == ["234.56", "."]
        assert sentences[4][0] == "this"
        assert sentences[5][0] == "stars"
        assert "*" in sentences[5]

    def test_german_compound_word_and_decimal_tokenization(self):
        """German: long compounds, z.B., European decimal format."""
        fixture = MULTILINGUAL_FIXTURES["de"]
        result = self._tokenize_fixture(fixture)
        sentences = _sentence_token_lists(result["content_tokens"])

        assert len(sentences) == 3
        compound = "Donaudampfschifffahrtsgesellschaftskapitänspension"
        assert compound in sentences[0]
        assert "beispiel.de" in sentences[1]
        assert "1.234" in sentences[2]
        assert "€" in sentences[2]

    def test_french_elision_and_guillemets(self):
        """French: M., elisions, exclamation, euro amounts."""
        fixture = MULTILINGUAL_FIXTURES["fr"]
        result = self._tokenize_fixture(fixture)
        sentences = _sentence_token_lists(result["content_tokens"])

        assert len(sentences) == 4
        assert "M." in sentences[0]
        assert "Paris" in sentences[0]
        assert any("intelligence" in token for token in sentences[1])
        assert "contact@exemple.fr" in _flatten_sentence_tokens(
            result["content_tokens"]
        )

    def test_spanish_inverted_punctuation(self):
        """Spanish: ¿? and ¡! markers preserved as tokens."""
        fixture = MULTILINGUAL_FIXTURES["es"]
        result = self._tokenize_fixture(fixture)
        flat = _flatten_sentence_tokens(result["content_tokens"])

        assert "¿" in flat
        assert "?" in flat
        assert "¡" in flat
        assert "!" in flat
        assert "García" in flat

    def test_multi_paragraph_structure_preserved(self):
        """Nested content arrays must mirror paragraph/sentence hierarchy."""
        fixture = copy.deepcopy(MULTILINGUAL_FIXTURES["en"])
        result = self._tokenize_fixture(fixture)

        assert len(result["content_tokens"]) == 1
        assert len(result["content_tokens"][0]) == 2
        assert len(result["content_tokens"][0][0]) == 4
        assert len(result["content_tokens"][0][1]) == 2
        assert _count_sentences(result["content_tokens"]) == 6

    def test_unsupported_pysbd_language_falls_back_to_english_rules(self):
        assert pysbd_language("sv") == "en"
        fixture = MULTILINGUAL_FIXTURES["sv"]
        tokenizer = self._make_tokenizer("sv")
        assert tokenizer._spacyTokenizer._sent_segmenter.language == "en"
        primary = fixture.paragraphs[0][0]
        assert len(SentenceSegmenter("sv").segment(primary)) == len(
            SentenceSegmenter("en").segment(primary)
        )
