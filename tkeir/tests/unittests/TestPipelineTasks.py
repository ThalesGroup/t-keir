# -*- coding: utf-8 -*-
"""Tests for pipeline task dependency resolution."""

import pytest

from thot.tasks.pipeline.PipelineTasks import (
    expand_tasks,
    parse_tasks,
    task_output_present,
    validate_tasks,
)


class TestPipelineTasks:
    def test_expand_tasks_includes_dependencies(self):
        assert expand_tasks(["ner"]) == [
            "converter",
            "tokenizer",
            "morphosyntax",
            "ner",
        ]

    def test_expand_tasks_syntax_includes_ner(self):
        assert expand_tasks(["syntax"]) == [
            "converter",
            "tokenizer",
            "morphosyntax",
            "ner",
            "syntax",
        ]

    def test_expand_tasks_chunking_includes_syntax(self):
        assert expand_tasks(["chunking"]) == [
            "converter",
            "tokenizer",
            "morphosyntax",
            "ner",
            "syntax",
            "chunking",
        ]

    def test_expand_tasks_chunk_questions_includes_ontology(self):
        assert expand_tasks(["chunk-questions"]) == [
            "converter",
            "tokenizer",
            "morphosyntax",
            "ner",
            "syntax",
            "chunking",
            "ontology",
            "chunk-questions",
        ]

    def test_expand_tasks_skip_converter(self):
        assert expand_tasks(["tokenizer"], skip_converter=True) == [
            "tokenizer"
        ]

    def test_expand_tasks_unknown_task(self):
        with pytest.raises(ValueError):
            validate_tasks(["unknown-task"])

    def test_parse_tasks(self):
        assert parse_tasks("ner, syntax") == ["ner", "syntax"]
        assert parse_tasks(None) is None

    def test_task_output_present(self):
        document = {"content_tokens": [[]], "content_morphosyntax": [[]]}
        assert task_output_present(document, "tokenizer")
        assert task_output_present(document, "morphosyntax")
        assert not task_output_present(document, "ner")
