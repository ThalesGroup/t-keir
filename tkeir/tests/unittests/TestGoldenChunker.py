# -*- coding: utf-8 -*-
"""Tests for golden chunking."""

import os

import pytest

from thot.core.TkeirPaths import configs_dir
from thot.tasks.golden_chunking.ChunkBuilder import (
    ChunkSettings,
    build_golden_chunks,
    build_sentence_chunk_ranges,
    extract_sentence_spans,
)
from thot.tasks.golden_chunking.GoldenChunker import GoldenChunker
from thot.tasks.golden_chunking.GoldenChunkerConfiguration import (
    GoldenChunkerConfiguration,
)


def _token(
    text: str,
    is_sent_start: bool = False,
    pos: str = "NOUN",
) -> dict:
    return {
        "text": text,
        "pos": pos,
        "lemma": text.lower(),
        "is_sent_start": is_sent_start,
    }


def _analyzed_document() -> dict:
    morphosyntax = [
        _token("Acme", True),
        _token("Corp"),
        _token("launched", pos="VERB"),
        _token("a", pos="DET"),
        _token("product"),
        _token(".", pos="PUNCT"),
        _token("It", True, pos="PRON"),
        _token("targets", pos="VERB"),
        _token("enterprise"),
        _token("customers"),
        _token(".", pos="PUNCT"),
        _token("The", True, pos="DET"),
        _token("company"),
        _token("expanded", pos="VERB"),
        _token("into", pos="ADP"),
        _token("Europe", pos="PROPN"),
        _token(".", pos="PUNCT"),
        _token("Microsoft", True, pos="PROPN"),
        _token("responded", pos="VERB"),
        _token("quickly", pos="ADV"),
        _token(".", pos="PUNCT"),
        _token("They", True, pos="PRON"),
        _token("acquired", pos="VERB"),
        _token("a", pos="DET"),
        _token("startup"),
        _token(".", pos="PUNCT"),
    ]
    ner = [
        {"start": 0, "end": 2, "label": "ORG", "text": "Acme Corp"},
        {"start": 17, "end": 18, "label": "ORG", "text": "Microsoft"},
    ]
    kg = [
        {
            "field_type": "content",
            "subject": {"content": ["Acme Corp"], "positions": [0, 1]},
            "property": {"content": ["launched"], "positions": [2]},
            "value": {"content": ["product"], "positions": [4]},
        },
        {
            "field_type": "content",
            "subject": {"content": ["Acme Corp"], "positions": [6]},
            "property": {"content": ["targets"], "positions": [7]},
            "value": {"content": ["customers"], "positions": [9]},
        },
        {
            "field_type": "content",
            "subject": {"content": ["Microsoft"], "positions": [17]},
            "property": {"content": ["responded"], "positions": [18]},
            "value": {"content": ["quickly"], "positions": [19]},
        },
        {
            "field_type": "content",
            "subject": {"content": ["Microsoft"], "positions": [21]},
            "property": {"content": ["acquired"], "positions": [22]},
            "value": {"content": ["startup"], "positions": [24]},
        },
    ]
    return {
        "source_doc_id": "doc-001",
        "content_morphosyntax": morphosyntax,
        "content_ner": ner,
        "content_deps": [{} for _ in morphosyntax],
        "kg": kg,
    }


class TestChunkBuilder:
    def test_extract_sentence_spans(self):
        document = _analyzed_document()
        sentences = extract_sentence_spans(document["content_morphosyntax"])
        assert len(sentences) == 5
        assert sentences[0].start == 0
        assert sentences[0].end == 6

    def test_never_splits_inside_sentence(self):
        document = _analyzed_document()
        sentences = extract_sentence_spans(document["content_morphosyntax"])
        ranges = build_sentence_chunk_ranges(
            sentences,
            document["content_ner"],
            ChunkSettings(target_min_tokens=1, target_max_tokens=4),
        )
        for start, end in ranges:
            assert end > start

    def test_build_golden_chunks_structure(self):
        chunks = build_golden_chunks(
            _analyzed_document(),
            settings=ChunkSettings(
                target_min_tokens=1,
                target_max_tokens=8,
                high_ner_density_max_tokens=4,
                ner_density_threshold=1,
            ),
        )
        assert chunks
        chunk = chunks[0]
        assert chunk["parent_doc_id"] == "doc-001"
        assert chunk["chunk_id"].startswith("doc-001#chunk-0-")
        assert chunk["text_raw"]
        assert chunk["text_raw"] in chunk["search_vector_payload"]
        assert "metadata" in chunk
        assert "implicit_subjects" in chunk["metadata"]
        assert "primary_entities" in chunk["metadata"]
        assert "svo_triplets" in chunk["metadata"]
        assert "context_summary_before" in chunk["metadata"]
        assert "context_summary_after" in chunk["metadata"]

    def test_context_padding_in_search_payload(self):
        chunks = build_golden_chunks(
            _analyzed_document(),
            settings=ChunkSettings(
                target_min_tokens=1,
                target_max_tokens=6,
                high_ner_density_max_tokens=4,
                ner_density_threshold=2,
            ),
        )
        assert len(chunks) >= 2
        middle = chunks[1]
        assert "[CONTEXT_BEFORE]" in middle["search_vector_payload"]
        assert middle["metadata"]["context_summary_before"]
        if len(chunks) > 2:
            assert "[CONTEXT_AFTER]" in middle["search_vector_payload"]

    def test_implicit_subjects_from_pronouns(self):
        chunks = build_golden_chunks(
            _analyzed_document(),
            settings=ChunkSettings(
                target_min_tokens=1,
                target_max_tokens=20,
            ),
        )
        pronoun_chunk = next(
            chunk for chunk in chunks if "It targets" in chunk["text_raw"]
        )
        assert "Acme Corp" in pronoun_chunk["metadata"]["implicit_subjects"]

    def test_implicit_subjects_from_company_reference(self):
        chunks = build_golden_chunks(
            _analyzed_document(),
            settings=ChunkSettings(
                target_min_tokens=1,
                target_max_tokens=20,
            ),
        )
        company_chunk = next(
            chunk
            for chunk in chunks
            if "The company expanded" in chunk["text_raw"]
        )
        resolved = company_chunk["metadata"]["implicit_subjects"]
        assert any("The company" in item for item in resolved)

    def test_context_summary_prioritizes_people_over_dates(self):
        document = {
            "source_doc_id": "doc-afl",
            "content_morphosyntax": (
                [
                    _token(str(index), is_sent_start=index == 0, pos="NUM")
                    for index in range(40)
                ]
                + [
                    _token("Charles", True, pos="PROPN"),
                    _token("Sutton"),
                    _token("Medal"),
                    _token("."),
                ]
            ),
            "content_ner": [
                {
                    "start": 10,
                    "end": 12,
                    "label": "date",
                    "text": "86.4 34",
                },
                {
                    "start": 12,
                    "end": 14,
                    "label": "date",
                    "text": "8 13 1 1974",
                },
                {
                    "start": 20,
                    "end": 22,
                    "label": "location",
                    "text": "Melbourne",
                },
                {
                    "start": 30,
                    "end": 32,
                    "label": "organization",
                    "text": "Brisbane Lions",
                },
                {
                    "start": 40,
                    "end": 43,
                    "label": "person",
                    "text": "Charles Sutton",
                },
            ],
            "content_deps": [],
            "kg": [],
        }
        chunks = build_golden_chunks(
            document,
            settings=ChunkSettings(target_min_tokens=1, target_max_tokens=50),
        )
        assert len(chunks) >= 2
        person_chunk = chunks[-1]
        previous_chunk = chunks[-2]
        assert (
            "Charles Sutton"
            in person_chunk["metadata"]["primary_entities"]["person"]
        )
        context_after = previous_chunk["metadata"]["context_summary_after"]
        assert "Charles Sutton" in context_after
        assert "[CONTEXT_AFTER]" in previous_chunk["search_vector_payload"]
        assert "Charles Sutton" in previous_chunk["search_vector_payload"]

    def test_implicit_subjects_language_agnostic_french(self):
        document = {
            "source_doc_id": "doc-fr",
            "content_morphosyntax": [
                _token("Acme", True, pos="PROPN"),
                _token("a", pos="VERB"),
                _token("lancé", pos="VERB"),
                _token("un", pos="DET"),
                _token("produit", pos="NOUN"),
                _token(".", pos="PUNCT"),
                _token("Il", True, pos="PRON"),
                _token("cible", pos="VERB"),
                _token("les", pos="DET"),
                _token("clients", pos="NOUN"),
                _token(".", pos="PUNCT"),
                _token("La", True, pos="DET"),
                _token("société", pos="NOUN"),
                _token("a", pos="AUX"),
                _token("grandi", pos="VERB"),
                _token(".", pos="PUNCT"),
            ],
            "content_ner": [
                {"start": 0, "end": 1, "label": "ORG", "text": "Acme"},
            ],
            "content_deps": [],
            "kg": [
                {
                    "field_type": "content",
                    "subject": {"content": ["Acme"], "positions": [0]},
                    "property": {"content": ["a lancé"], "positions": [1, 2]},
                    "value": {"content": ["produit"], "positions": [4]},
                },
                {
                    "field_type": "content",
                    "subject": {"content": ["Acme"], "positions": [6]},
                    "property": {"content": ["cible"], "positions": [7]},
                    "value": {"content": ["clients"], "positions": [9]},
                },
            ],
        }
        chunks = build_golden_chunks(
            document,
            settings=ChunkSettings(target_min_tokens=1, target_max_tokens=20),
        )
        pronoun_chunk = next(
            chunk for chunk in chunks if "Il cible" in chunk["text_raw"]
        )
        assert "Acme" in pronoun_chunk["metadata"]["implicit_subjects"]
        company_chunk = next(
            chunk
            for chunk in chunks
            if "La société a grandi" in chunk["text_raw"]
        )
        assert any(
            "La société" in item
            for item in company_chunk["metadata"]["implicit_subjects"]
        )


class TestGoldenChunker:
    def _load_config(self) -> GoldenChunkerConfiguration:
        config = GoldenChunkerConfiguration()
        with open(
            os.path.join(configs_dir(), "golden-chunking.json"),
            encoding="utf-8",
        ) as handle:
            config.load(handle)
        return config

    def test_chunker_run(self):
        chunker = GoldenChunker(config=self._load_config())
        document = _analyzed_document()
        result = chunker.run(document)
        assert "golden_chunks" in result
        assert result["golden_chunks"]
        assert any(
            info.get("task-name") == "golden-chunking"
            for info in result.get("tasks-info", [])
        )

    def test_chunker_requires_analyzed_fields(self):
        chunker = GoldenChunker(config=self._load_config())
        with pytest.raises(ValueError):
            chunker.run({"content": "raw text only"})

    def test_configuration_load(self):
        config = self._load_config()
        assert "chunkers" in config.configuration
        assert config.configuration["chunkers"][0]["language"] == "en"
