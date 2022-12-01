# -*- coding: utf-8 -*-
"""Sanic documentation


Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.

"""
from os import posix_fadvise
from sanic_openapi import doc


class SentencePosition:
    start: doc.Integer(description="start offset of the sentence")
    length: doc.Integer(description="length of the sentence")


class EmbeddingItem:
    field: doc.String("Field from which the embedding is computed (can be empty)")
    content: doc.String(description="text of the sentence")
    embeding: doc.List(doc.Integer(description="embedding feature"), description="embedding vector")
    position: doc.Object(SentencePosition)


class SentenceEntryDoc:
    sentences: doc.List(doc.String(description="sentence to analyze"))


class EmbeddingsTableDoc:
    result: doc.List(EmbeddingItem)
    info: doc.String(description="service info id")
    config: doc.String(description="service configuration file")
    version: doc.String(description="version of the service")
    date: doc.String(description="release date of the service")
