# -*- coding: utf-8 -*-
"""Tests for chunk-level synthetic question generation."""

import os

import pytest

from thot.core.TkeirPaths import configs_dir
from thot.tasks.chunk_questions.ChunkQuestionGenerator import (
    ChunkQuestionGenerator,
)
from thot.tasks.chunk_questions.QuestionBuilder import (
    QuestionGenerationSettings,
    enrich_golden_chunks_with_questions,
    generate_chunk_questions,
)


def _golden_chunk() -> dict:
    return {
        "chunk_id": "doc#chunk-0",
        "text_raw": (
            "Acme Corp launched Widget Pro. It targets enterprise buyers."
        ),
        "metadata": {
            "svo_triplets": [
                ["Acme Corp", "launched", "Widget Pro"],
                ["Widget Pro", "targets", "enterprise buyers"],
            ],
            "primary_entities": {
                "organization": ["Acme Corp"],
                "product": ["Widget Pro"],
            },
        },
    }


class TestQuestionBuilder:
    def test_generate_chunk_questions_types(self):
        questions = generate_chunk_questions(
            _golden_chunk(),
            language="en",
            settings=QuestionGenerationSettings(
                min_questions=3, max_questions=5
            ),
        )
        assert 3 <= len(questions) <= 5
        types = {item["question_type"] for item in questions}
        assert "SVO-driven" in types
        assert "Entity-driven" in types
        assert "Summary-driven" in types

    def test_enrich_golden_chunks_with_questions(self):
        document = {
            "language-detection": {"language": "en"},
            "golden_chunks": [_golden_chunk()],
        }
        chunks = enrich_golden_chunks_with_questions(document)
        assert chunks[0]["synthetic_questions"]


class TestChunkQuestionGenerator:
    def _load_config(self):
        from thot.tasks.chunk_questions.ChunkQuestionGeneratorConfiguration import (
            ChunkQuestionGeneratorConfiguration,
        )

        config = ChunkQuestionGeneratorConfiguration()
        with open(
            os.path.join(configs_dir(), "chunk-questions.json"),
            encoding="utf-8",
        ) as handle:
            config.load(handle)
        return config

    def test_generate_updates_chunks(self):
        generator = ChunkQuestionGenerator(config=self._load_config())
        document = {
            "golden_chunks": [_golden_chunk()],
            "language-detection": {"language": "en"},
        }
        result = generator.run(document)
        assert result["chunk_questions_ready"] is True
        assert result["golden_chunks"][0]["synthetic_questions"]

    def test_generate_requires_golden_chunks(self):
        generator = ChunkQuestionGenerator(config=self._load_config())
        with pytest.raises(ValueError):
            generator.run({"content": ["text"]})
