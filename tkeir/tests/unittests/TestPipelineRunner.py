# -*- coding: utf-8 -*-

# -*- coding: utf-8 -*-
"""Tests for pipeline runner orchestration."""

import base64
import os
from unittest.mock import patch

import pytest

from thot.core.TkeirPaths import configs_dir
from thot.tasks.pipeline.PipelineConfiguration import PipelineConfiguration
from thot.tasks.pipeline.PipelineRunner import PipelineRunner


class TestPipelineRunner:
    @pytest.fixture(autouse=True)
    def _pipeline_config(self):
        self.config = PipelineConfiguration()
        with open(
            os.path.join(configs_dir(), "pipeline.json"), encoding="utf-8"
        ) as handle:
            self.config.load(handle)

    @patch.object(PipelineRunner, "_get_chunk_questions")
    @patch.object(PipelineRunner, "_get_ontology")
    @patch.object(PipelineRunner, "_get_chunking")
    @patch.object(PipelineRunner, "_get_keywords")
    @patch.object(PipelineRunner, "_get_syntax")
    @patch.object(PipelineRunner, "_get_ner")
    @patch.object(PipelineRunner, "_get_morphosyntax")
    @patch.object(PipelineRunner, "_get_tokenizer")
    @patch.object(PipelineRunner, "_get_converter")
    def test_run_calls_all_steps(
        self,
        mock_converter,
        mock_tokenizer,
        mock_morphosyntax,
        mock_ner,
        mock_syntax,
        mock_keywords,
        mock_chunking,
        mock_ontology,
        mock_chunk_questions,
    ):
        mock_converter.return_value.convert.return_value = {
            "title": "",
            "content": ["English pipeline text for testing purposes."],
            "kg": [],
        }
        enriched = {
            "title": "",
            "content": ["English pipeline text for testing purposes."],
            "content_tokens": [[]],
            "language-detection": {"language": "en", "confidence": 0.99},
            "resource-selection": {
                "detected-language": "en",
                "processing-language": "en",
                "resources-base-path": None,
                "available-languages": ["en"],
            },
        }
        mock_tokenizer.return_value.run.return_value = enriched
        mock_morphosyntax.return_value.run.return_value = {
            **enriched,
            "content_morphosyntax": [],
        }
        mock_ner.return_value.run.return_value = {
            **enriched,
            "content_ner": [],
        }
        mock_syntax.return_value.run.return_value = {
            **enriched,
            "content_deps": [],
        }
        mock_keywords.return_value.run.return_value = {
            **enriched,
            "keywords": [],
        }
        mock_chunking.return_value.run.return_value = {
            **enriched,
            "keywords": [],
            "golden_chunks": [],
        }
        mock_ontology.return_value.run.return_value = {
            **enriched,
            "golden_chunks": [],
            "document_ontology": {
                "json_ld": '[{"@id": "http://tkeir.local/ontology/Document"}]',
                "shacl_status": "PASSED",
                "incoherences": {"total": 0, "unresolved": 0, "auto_fixed": 0},
            },
        }
        mock_chunk_questions.return_value.run.return_value = {
            **enriched,
            "keywords": [],
            "golden_chunks": [],
            "document_ontology": {
                "json_ld": '[{"@id": "http://tkeir.local/ontology/Document"}]',
                "shacl_status": "PASSED",
                "incoherences": {"total": 0, "unresolved": 0, "auto_fixed": 0},
            },
            "chunk_questions_ready": True,
        }

        runner = PipelineRunner(self.config)
        payload = {
            "datatype": "raw",
            "data": (
                base64.b64encode(
                    b"English pipeline text for testing purposes."
                ).decode()
            ),
            "source": "file://sample.txt",
        }
        result = runner.run(payload)

        mock_converter.return_value.convert.assert_called_once()
        mock_tokenizer.return_value.run.assert_called_once()
        mock_morphosyntax.return_value.run.assert_called_once()
        mock_ner.return_value.run.assert_called_once()
        mock_syntax.return_value.run.assert_called_once()
        mock_keywords.return_value.run.assert_called_once()
        mock_chunking.return_value.run.assert_called_once()
        mock_ontology.return_value.run.assert_called_once()
        mock_chunk_questions.return_value.run.assert_called_once()
        assert "keywords" in result
        assert "golden_chunks" in result
        assert "document_ontology" in result
        assert result.get("chunk_questions_ready") is True

    @patch.object(PipelineRunner, "_get_morphosyntax")
    @patch.object(PipelineRunner, "_get_tokenizer")
    @patch.object(PipelineRunner, "_get_converter")
    def test_run_with_tasks_runs_dependencies_only(
        self, mock_converter, mock_tokenizer, mock_morphosyntax
    ):
        mock_converter.return_value.convert.return_value = {
            "title": "",
            "content": ["English pipeline text for testing purposes."],
            "kg": [],
        }
        tokenized = {
            "title": "",
            "content": ["English pipeline text for testing purposes."],
            "content_tokens": [[]],
            "language-detection": {"language": "en", "confidence": 0.99},
            "resource-selection": {
                "detected-language": "en",
                "processing-language": "en",
                "resources-base-path": None,
                "available-languages": ["en"],
            },
        }
        mock_tokenizer.return_value.run.return_value = tokenized
        mock_morphosyntax.return_value.run.return_value = {
            **tokenized,
            "content_morphosyntax": [],
        }

        runner = PipelineRunner(self.config)
        payload = {
            "datatype": "raw",
            "data": (
                base64.b64encode(
                    b"English pipeline text for testing purposes."
                ).decode()
            ),
            "source": "file://sample.txt",
        }
        result = runner.run(payload, tasks=["morphosyntax"])

        mock_converter.return_value.convert.assert_called_once()
        mock_tokenizer.return_value.run.assert_called_once()
        mock_morphosyntax.return_value.run.assert_called_once()
        assert "content_morphosyntax" in result

    @patch.object(PipelineRunner, "_get_chunk_questions")
    @patch.object(PipelineRunner, "_get_ontology")
    @patch.object(PipelineRunner, "_get_chunking")
    @patch.object(PipelineRunner, "_get_keywords")
    @patch.object(PipelineRunner, "_get_syntax")
    @patch.object(PipelineRunner, "_get_ner")
    @patch.object(PipelineRunner, "_get_morphosyntax")
    @patch.object(PipelineRunner, "_get_tokenizer")
    @patch.object(PipelineRunner, "_get_converter")
    def test_run_converted_skips_converter(
        self,
        mock_converter,
        mock_tokenizer,
        mock_morphosyntax,
        mock_ner,
        mock_syntax,
        mock_keywords,
        mock_chunking,
        mock_ontology,
        mock_chunk_questions,
    ):
        document = {
            "title": "",
            "content": ["English pipeline text for testing purposes."],
            "content_tokens": [[]],
            "language-detection": {"language": "en", "confidence": 0.99},
            "resource-selection": {
                "detected-language": "en",
                "processing-language": "en",
                "resources-base-path": None,
                "available-languages": ["en"],
            },
        }
        mock_tokenizer.return_value.run.return_value = document
        mock_morphosyntax.return_value.run.return_value = document
        mock_ner.return_value.run.return_value = document
        mock_syntax.return_value.run.return_value = document
        mock_keywords.return_value.run.return_value = {
            **document,
            "keywords": [],
        }
        mock_chunking.return_value.run.return_value = {
            **document,
            "keywords": [],
            "golden_chunks": [],
        }
        mock_ontology.return_value.run.return_value = {
            **document,
            "golden_chunks": [],
            "document_ontology": {
                "shacl_status": "PASSED",
                "incoherences": {"total": 0, "unresolved": 0, "auto_fixed": 0},
            },
        }
        mock_chunk_questions.return_value.run.return_value = {
            **document,
            "keywords": [],
            "golden_chunks": [],
            "document_ontology": {
                "shacl_status": "PASSED",
                "incoherences": {"total": 0, "unresolved": 0, "auto_fixed": 0},
            },
            "chunk_questions_ready": True,
        }

        runner = PipelineRunner(self.config)
        result = runner.run_converted(document)
        mock_converter.assert_not_called()
        assert "keywords" in result
        assert "golden_chunks" in result
        assert "document_ontology" in result
        assert result.get("chunk_questions_ready") is True

    @patch("thot.tasks.pipeline.PipelineRunner.Converter")
    def test_get_converter_is_cached(self, mock_converter_cls):
        mock_converter_cls.return_value.convert.return_value = {
            "title": "T",
            "content": ["body"],
            "kg": [],
        }
        runner = PipelineRunner(self.config)
        assert runner._get_converter() is runner._get_converter()
        mock_converter_cls.assert_called_once()

    @patch("thot.tasks.pipeline.PipelineRunner.KeywordsExtractor")
    @patch("thot.tasks.pipeline.PipelineRunner.SyntacticTagger")
    @patch("thot.tasks.pipeline.PipelineRunner.NERTagger")
    @patch("thot.tasks.pipeline.PipelineRunner.MorphoSyntacticTagger")
    @patch("thot.tasks.pipeline.PipelineRunner.Tokenizer")
    def test_task_getters_are_cached(
        self,
        mock_tokenizer_cls,
        mock_morphosyntax_cls,
        mock_ner_cls,
        mock_syntax_cls,
        mock_keywords_cls,
    ):
        runner = PipelineRunner(self.config)
        assert runner._get_tokenizer() is runner._get_tokenizer()
        assert runner._get_morphosyntax() is runner._get_morphosyntax()
        assert runner._get_ner() is runner._get_ner()
        assert runner._get_syntax() is runner._get_syntax()
        assert runner._get_keywords() is runner._get_keywords()
        mock_tokenizer_cls.assert_called_once()
        mock_morphosyntax_cls.assert_called_once()
        mock_ner_cls.assert_called_once()
        mock_syntax_cls.assert_called_once()
        mock_keywords_cls.assert_called_once()

    @patch("thot.tasks.pipeline.PipelineRunner.MorphoSyntacticTagger")
    def test_morphosyntax_not_reloaded_for_same_language(
        self, mock_morphosyntax_cls
    ):
        mock_morphosyntax_cls.return_value.run.side_effect = lambda doc: doc
        runner = PipelineRunner(self.config)
        doc = {
            "content": ["English pipeline text for testing purposes."],
            "language-detection": {"language": "en", "confidence": 0.99},
            "resource-selection": {
                "detected-language": "en",
                "processing-language": "en",
                "spacy-language": "en",
                "resources-base-path": None,
                "available-languages": ["en"],
            },
            "content_tokens": [{"token": "English", "start_sentence": True}],
        }
        runner.run(doc, skip_converter=True, tasks=["morphosyntax"])
        runner.run(doc, skip_converter=True, tasks=["morphosyntax"])
        mock_morphosyntax_cls.assert_called_once()
