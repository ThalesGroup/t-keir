# -*- coding: utf-8 -*-
"""Tests for pipeline summary metadata."""

from thot.tasks.pipeline.PipelineSummary import (
    annotate_pipeline_summary,
    count_document_tokens,
)


class TestPipelineSummary:
    def test_count_document_tokens_nested_structure(self):
        document = {
            "title_tokens": [[{"token": "Title", "start_sentence": True}]],
            "content_tokens": [
                [
                    [
                        [
                            {"token": "Hello", "start_sentence": True},
                            {"token": "world", "start_sentence": False},
                        ]
                    ]
                ]
            ],
        }
        counts = count_document_tokens(document)
        assert counts["title-token-count"] == 1
        assert counts["content-token-count"] == 2
        assert counts["token-count"] == 3

    def test_annotate_pipeline_summary(self):
        document = {
            "content": ["text"],
            "content_tokens": [
                [[[{"token": "text", "start_sentence": True}]]]
            ],
            "conversion-info": {
                "source-size-bytes": 2048,
                "image-extraction": {
                    "enabled": True,
                    "used": True,
                    "mode": "tesseract",
                    "image-regions": 2,
                    "scanned-pages": 0,
                },
            },
        }
        result = annotate_pipeline_summary(
            document,
            {"source-file-size-bytes": 2048},
            {"converter": 1.5, "tokenizer": 2.25},
        )
        assert result["content-token-count"] == 1
        assert result["source-file-size-bytes"] == 2048
        assert result["image-extraction"]["image-regions"] == 2
        assert result["pipeline-timing"]["elapsed-seconds"] == 3.75
        assert result["pipeline-timing"]["tasks"]["tokenizer"] == 2.25

    def test_annotate_pipeline_summary_uses_conversion_info_size(self):
        document = {
            "content": ["text"],
            "conversion-info": {"source-size-bytes": 1024},
        }
        result = annotate_pipeline_summary(document, None, {"converter": 1.0})
        assert result["source-file-size-bytes"] == 1024
