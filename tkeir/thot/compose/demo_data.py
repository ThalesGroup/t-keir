"""Title: Demo data

Demo Turtle fixtures for offline ``make compose`` / unit tests.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

DEMO_TURTLE = """
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix tkeir: <http://tkeir.local/ontology/> .
@prefix tkeirdoc: <http://tkeir.local/doc/> .

tkeirdoc:doc_a a tkeir:Document ;
    tkeir:hasChunk <http://tkeir.local/doc/doc_a/Chunk/chunk_1> ;
    tkeir:hasKeyword <http://tkeir.local/doc/doc_a/Keyword/streaming_service> ;
    tkeir:hasMention <http://tkeir.local/doc/doc_a/Company/acme-aaa> .

<http://tkeir.local/doc/doc_a/Keyword/streaming_service> a tkeir:Keyword ;
    rdfs:label "msn video streaming service" .

<http://tkeir.local/doc/doc_a/Chunk/chunk_1> a tkeir:DocumentChunk ;
    rdfs:label "doc.pdf#chunk-1-abc" ;
    tkeir:hasMention <http://tkeir.local/doc/doc_a/Company/acme-aaa> ;
    tkeir:hasMention <http://tkeir.local/doc/doc_a/Date/jan-2001> ;
    tkeir:hasStatement <http://tkeir.local/doc/doc_a/Company/acme-aaa> .

<http://tkeir.local/doc/doc_a/Company/acme-aaa> a tkeir:Company ;
    rdfs:label "Acme" ;
    tkeir:createdBy <http://tkeir.local/doc/doc_a/Product/widget-bbb> .

<http://tkeir.local/doc/doc_a/Date/jan-2001> a tkeir:Date ;
    rdfs:label "January 2001" .

<http://tkeir.local/doc/doc_a/Product/widget-bbb> a tkeir:Product ;
    rdfs:label "Widget" .
""".strip()


def demo_turtles() -> list[str]:
    """Return the bundled demo Turtle documents.

    Example:
        >>> from thot.compose.demo_data import demo_turtles
        >>> "Acme" in demo_turtles()[0]
        True
    """
    return [DEMO_TURTLE]
