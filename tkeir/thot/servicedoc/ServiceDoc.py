# -*- coding: utf-8 -*-
"""Sanic documentation

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
from sanic_openapi import doc
from thot.servicedoc.EmbeddingsDoc import EmbeddingItem


class KGTripleEntry:
    content: doc.String(description="Content of triple item")
    lemma_content: doc.String(description="Lemmatized content")
    label: doc.String(description="label of the content")
    pos: doc.List(doc.String(description="POS tag"), "list of Part Of Speech Tags")
    positions: doc.List(doc.Integer(description="Position in document"), description="List of position of tokens in document")
    class_: doc.Integer(description="Semantic class, comming from clustering prediction")


class KGItem:
    subject: doc.Object(KGTripleEntry, description="subject of the item (e.g. John Doe)")
    property: doc.Object(KGTripleEntry, description="property of the item (e.g. <instanceof>)")
    value: doc.Object(KGTripleEntry, description="value of the item (e.g. person)")


class POSTag:
    pos: doc.String(description="Part Of Speech")
    lemma: doc.String(description="lemma of token - the form")


class NERTag:
    start: doc.Integer(description="start offset of the token of the named entity")
    end: doc.Integer(description="end offset of the token of the named entity")
    text: doc.String(description="text of the named entity")
    label: doc.String(description="label of the named entity")


class Keyword:
    start: doc.Integer(description="start offset of the token of the keyword")
    end: doc.Integer(description="end offset of the token of the keyword")
    score: doc.Float(description="score of keyword")
    text: doc.String(description="text of the named entity")
    class_: doc.String(description="Cluster class")


# TODO DOC
class ZeroShotClassificationTag:
    document: doc.Integer(description="label with their probabilitier")
    title_sentences: doc.Integer(description="list of sentences")
    content_sentences: doc.Float(description="list fo sentences")


class DepsTag:
    dep: doc.String(description="Dependency name")
    head: doc.Integer(description="Head position")
    lefts: doc.List(doc.Integer(description="position"), description="List of lefts positions")
    rights: doc.List(doc.Integer(description="position"), description="List of rights positions")
    lemma: doc.String(description="lemmatized value")
    pos: doc.String(description="part of speech")
    text: doc.String(description="form of token")


# TODO doc
class QAItem:
    query: doc.String("The query")


class SentimentItem:
    label: doc.String(description="positibe or negative")
    score: doc.Float(description="score of label")
    sentence: doc.String(description="sentence")


class SummaryItem:
    block: doc.String(description="Initial data")
    summary: doc.String(description="Summarized data")


class SearchInput:
    from_: doc.Integer(description="Start of ranked list")
    size: doc.Integer(description="number of documents")
    content: doc.String(description="document/query content")


class SentenceSearchInputOption:
    disable: doc.List(
        doc.String(description="Disable algorithms qa and/or aggregator"), description="list of disable algorithm"
    )
    exclude: doc.List(doc.String(description="exclude field form index"), description="list of index index field")


class SentenceSearchInputClause:
    type: doc.String("must or should clause")
    clause: doc.String("E.S clause to add")


class SentenceSearchInput:
    from_: doc.Integer(description="Start of ranked list")
    size: doc.Integer(description="number of documents")
    content: doc.String(description="document/query content")
    options: doc.Object(SentenceSearchInputOption, description="Option for search")
    add_clause: doc.Object(SentenceSearchInputClause, description="Add clause to search")


class TKeirResult:
    data_source: doc.String(description="source of the document (could be host file system, web, ...")
    source_doc_id: doc.String(description="uniq id of the document")
    title: doc.String(description="title of document")
    content: doc.String(description="nested array of text representing the content of the document")
    title_tokens: doc.List(
        doc.String(description="a token, possibly MWE"),
        description="list of token from title (obtained after tokenizer service)",
    )
    content_tokens: doc.List(
        doc.String(description="a token, possibly MWE"),
        description="list of token from content (obtained after tokenizer service)",
    )
    title_morphosyntax: doc.List(
        POSTag,
        description="list of tagged (morpho syntactic) tokens from title (obtained after morphosyntactic tagger - mstagger -  service)",
    )
    content_morphosyntax: doc.List(
        POSTag,
        description="list of tagged (morpho syntactic) tokens from content (obtained after morphosyntactic tagger - mstagger -  service)",
    )
    title_ner: doc.List(
        NERTag, description="list of tagged (ner) tokens from title (obtained after ner tagger - nertagger -  service)"
    )
    content_ner: doc.List(
        NERTag, description="list of tagged (ner) tokens from content (obtained after ner tagger - nertagger -  service)"
    )
    title_deps: doc.List(
        DepsTag,
        description="list of tagged (deps) tokens from title (obtained after syntactic tagger - syntactictagger -  service)",
    )
    content_deps: doc.List(
        DepsTag,
        description="list of tagged (deps) tokens from content (obtained after syntactic tagger - syntactictagger -  service)",
    )
    keywords: doc.List(Keyword, description="list of keywords (obtained after keywords - keywords extracror -  service)")
    kg: doc.List(KGItem)
    embeddings: doc.List(EmbeddingItem)
    qa: doc.List(QAItem)
    zero_shot_classify: doc.Object(ZeroShotClassificationTag)
    sentiment: doc.List(SentimentItem)
    summaries: doc.List(SummaryItem)


class RankedList:
    items: doc.List(TKeirResult, description="list of documents")
    answer: doc.String("Short answer of the query [not alway present]")
    query: doc.String("The query formulated")
    total_docs: doc.Integer(description="total number of documents")


class TKeirDoc:
    result: doc.Object(TKeirResult)
    info: doc.String(description="service info id")
    config: doc.String(description="service configuration file")
    version: doc.String(description="version of the service")
    date: doc.String(description="release date of the service")


class QTKeirDoc:
    query: doc.String(description="document query")
    doc: doc.Object(TKeirResult)


class QTKeirSentences:
    query: doc.String(description="document query")
    texts: doc.List(doc.String(description="Sentence"), description="List of sentences")


class STKeirDoc:
    min_length: doc.Integer(description="minimum summary block length")
    max_length: doc.Integer(description="maximum summary block length")
    doc: doc.Object(TKeirResult)


class ClassifyTKeirDoc:
    classes: doc.List(doc.String(description="sub class name"), description="list of sub classes")
    map_classes: doc.String("Description is a dictionary of vector of subclasses")
    doc: doc.Object(TKeirDoc)


class TKeirErrorDoc:
    error: doc.String(description="description of the error")
    exception: doc.String(description="exception raised value")
    trace: doc.String(description="trace in the code of the error")
    info: doc.String(description="service info id")
    config: doc.String(description="service configuration file")
    version: doc.String(description="version of the service")
    date: doc.String(description="release date of the service")


class TKeirBadParameterDoc:
    error: doc.String(description="description of the error")
    info: doc.String(description="service info id")
    config: doc.String(description="service configuration file")
    version: doc.String(description="version of the service")
    date: doc.String(description="release date of the service")


class HealthDoc:
    health: doc.String(description="ok if service is healthy")
    info: doc.String(description="service uniq id")
    config: doc.String(description="configuration file path")
    version: doc.String(description="version of the service")
    date: doc.String(description="service development date")


class HealthErrorDoc:
    error: doc.String(description="error description")
    version: doc.String(description="version of the service")
    date: doc.String(description="service development date")


class NotFoundErrorDoc:
    error: doc.String(description="error description")
    info: doc.String(description="service uniq id")
    config: doc.String(description="configuration file path")
    version: doc.String(description="version of the service")
