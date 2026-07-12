# -*- coding: utf-8 -*-
"""Tests for pySBD sentence segmentation."""

from thot.core.SentenceSegmenter import (
    SentenceSegmenter,
    prepare_text_for_segmentation,
    pysbd_language,
)


class TestSentenceSegmenter:
    def test_french_sentences(self):
        segmenter = SentenceSegmenter("fr")
        sentences = segmenter.segment("Bonjour le monde. Ceci est une phrase.")
        assert len(sentences) == 2
        assert sentences[0].startswith("Bonjour")

    def test_english_sentences(self):
        segmenter = SentenceSegmenter("en")
        sentences = segmenter.segment("Hello world. This is a test.")
        assert len(sentences) == 2

    def test_unsupported_language_falls_back_to_english(self):
        assert pysbd_language("xx") == "en"
        segmenter = SentenceSegmenter("xx")
        assert segmenter.language == "en"

    def test_merges_pdf_line_breaks_in_prose(self):
        text = (
            "There was a bidding war for the show between Fox and NBC, with\n\n"
            "the show ultimately selling to Fox as a put pilot with a six-\n\n"
            "figure penalty.[17]"
        )
        segmenter = SentenceSegmenter("en")
        sentences = segmenter.segment(text)
        assert len(sentences) == 1
        assert "six-figure penalty" in sentences[0]

    def test_does_not_split_on_table_fragments_in_prose_flow(self):
        text = (
            "There was a bidding war for the show between Fox and NBC, with\n\n"
            "Production\n\n"
            "Imagine Television\n\n"
            "the show ultimately selling to Fox as a put pilot with a six-\n\n"
            "companies\n\n"
            "The Hurwitz Company 20th Century Fox Television\n\n"
            "figure penalty.[17]"
        )
        segmenter = SentenceSegmenter("en")
        sentences = segmenter.segment(text)
        prose = [
            sentence for sentence in sentences if "bidding war" in sentence
        ]
        assert len(prose) == 1
        assert "six-figure penalty" in prose[0]
        assert "Production" not in prose[0]

    def test_prepare_text_for_segmentation_unwraps_soft_line_breaks(self):
        paragraphs = prepare_text_for_segmentation(
            "This is a long sentence that wraps\n"
            "onto the next line without ending."
        )
        assert len(paragraphs) == 1
        assert "wraps onto the next line" in paragraphs[0]
