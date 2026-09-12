"""Title: Document-level index tags, simhash, and weighted search blend."""

from __future__ import annotations

from thot.tools.ingest.document_index import (
    DocumentIndexMeta,
    corpus_doc_docid,
    infer_data_kind,
    pick_near_duplicate,
)
from thot.tools.search.fusion import blend_chunk_and_document_scores


def test_chunk_parent_matches_indexed_document_id():
    source = "geomaps/record-1"
    meta = DocumentIndexMeta.from_document(
        {
            "source_doc_id": source,
            "title": "Carte du Suez",
            "dataset": "geomaps",
            "content_ner": [{"text": "Suez", "label": "location"}],
            "metadata": {"author": "Analyst A", "file_type": "geojson"},
        },
        ["A map of the canal region near Suez."],
    )
    assert meta.document_id == corpus_doc_docid(source)
    assert meta.author == "Analyst A"
    assert meta.data_kind == "carte"
    assert "Suez" in meta.location_tags
    assert meta.simhash_hex
    assert infer_data_kind({"title": "Meeting notes", "metadata": {}}) == "texte"


def test_simhash_skips_self_and_detects_neighbor():
    assert (
        pick_near_duplicate(
            0xF,
            [{"source_ref": "self", "simhash_hex": "000000000000000f"}],
            source_ref="self",
        )
        == ""
    )
    assert (
        pick_near_duplicate(
            0xF,
            [{"source_ref": "other", "simhash_hex": "000000000000000f"}],
            source_ref="self",
        )
        == "other"
    )


def test_weighted_document_arm_boosts_matching_chunks():
    blended = blend_chunk_and_document_scores(
        {"c1": 1.0, "c2": 0.2},
        {"c1": ["docA"], "c2": ["docB"]},
        {"docA": 0.0, "docB": 1.0},
        chunk_weight=0.5,
        document_weight=0.5,
    )
    assert blended["c2"] > blended["c1"]
