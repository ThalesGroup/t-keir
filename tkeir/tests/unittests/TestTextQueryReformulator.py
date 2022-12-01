# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.searching.TextQueryReformulator import TextQueryReformulator
import json
import os
import unittest


class TestTextQueryReformatulator(unittest.TestCase):
    tkeir_doc = {
        "data_source": "user-query",
        "source_doc_id": "user",
        "title": "",
        "content": [
            "(CN111004497)|1. The electroplating nylon material is characterized by comprising the following components in parts by weight: 50-80 parts of polyamide 20-50 parts of modified mineral 2-8 parts of a compatilizer."
        ],
        "kg": [
            {
                "subject": {"content": ["part"], "lemma_content": ["part"], "label": "", "class": 27, "positions": [0, 0]},
                "property": {
                    "content": ["rel:is_a"],
                    "lemma_content": ["rel:is_a"],
                    "label": "",
                    "class": -1,
                    "positions": [-1],
                },
                "value": {"content": ["keyword"], "lemma_content": ["keyword"], "label": "", "class": -1, "positions": [-1]},
                "automatically_fill": True,
                "confidence": 0.0,
                "weight": 0.0,
                "field_type": "keywords",
            }
        ],
        "error": False,
        "content_tokens": [
            [
                [
                    {"token": "(", "start_sentence": True},
                    {"token": "CN111004497", "start_sentence": False},
                    {"token": ")", "start_sentence": False},
                    {"token": "|1", "start_sentence": False},
                    {"token": ".", "start_sentence": False},
                ],
                [
                    {"token": "The", "start_sentence": True},
                    {"token": "electroplating", "start_sentence": False},
                    {"token": "nylon", "start_sentence": False},
                    {"token": "material", "start_sentence": False},
                    {"token": "is", "start_sentence": False},
                    {"token": "characterized", "start_sentence": False},
                    {"token": "by", "start_sentence": False},
                    {"token": "comprising", "start_sentence": False},
                    {"token": "the", "start_sentence": False},
                    {"token": "following", "start_sentence": False},
                    {"token": "components", "start_sentence": False},
                    {"token": "in", "start_sentence": False},
                    {"token": "parts", "start_sentence": False},
                    {"token": "by", "start_sentence": False},
                    {"token": "weight", "start_sentence": False},
                    {"token": ":", "start_sentence": False},
                    {"token": "50-80", "start_sentence": False},
                    {"token": "parts", "start_sentence": False},
                    {"token": "of", "start_sentence": False},
                    {"token": "polyamide", "start_sentence": False},
                    {"token": "20-50", "start_sentence": False},
                    {"token": "parts", "start_sentence": False},
                    {"token": "of", "start_sentence": False},
                    {"token": "modified", "start_sentence": False},
                    {"token": "mineral", "start_sentence": False},
                    {"token": "2-8", "start_sentence": False},
                    {"token": "parts", "start_sentence": False},
                    {"token": "of", "start_sentence": False},
                    {"token": "a", "start_sentence": False},
                    {"token": "compatilizer", "start_sentence": False},
                    {"token": ".", "start_sentence": False},
                ],
            ]
        ],
        "tasks-info": [
            {
                "os": [
                    "Linux",
                    "ce6ecd80a5ef",
                    "5.8.0-55-generic",
                    "#62~20.04.1-Ubuntu SMP Wed Jun 2 08:55:04 UTC 2021",
                    "x86_64",
                ],
                "hostname": "ce6ecd80a5ef",
                "host": "172.18.0.3",
                "execution-date": "Jul 01 2021 08:48:02",
                "task-version": "1.0.0",
                "task-development-date": "2021/03",
                "task-name": "tokenizer",
            },
            {
                "os": [
                    "Linux",
                    "ce6ecd80a5ef",
                    "5.8.0-55-generic",
                    "#62~20.04.1-Ubuntu SMP Wed Jun 2 08:55:04 UTC 2021",
                    "x86_64",
                ],
                "hostname": "ce6ecd80a5ef",
                "host": "172.18.0.3",
                "execution-date": "Jul 01 2021 08:48:02",
                "task-version": "1.0.0",
                "task-development-date": "2021/03",
                "task-name": "morphosyntax",
            },
            {
                "os": [
                    "Linux",
                    "ce6ecd80a5ef",
                    "5.8.0-55-generic",
                    "#62~20.04.1-Ubuntu SMP Wed Jun 2 08:55:04 UTC 2021",
                    "x86_64",
                ],
                "hostname": "ce6ecd80a5ef",
                "host": "172.18.0.3",
                "execution-date": "Jul 01 2021 08:48:02",
                "task-version": "1.0.0",
                "task-development-date": "2021/03",
                "task-name": "ner",
            },
            {
                "os": [
                    "Linux",
                    "ce6ecd80a5ef",
                    "5.8.0-55-generic",
                    "#62~20.04.1-Ubuntu SMP Wed Jun 2 08:55:04 UTC 2021",
                    "x86_64",
                ],
                "hostname": "ce6ecd80a5ef",
                "host": "172.18.0.3",
                "execution-date": "Jul 01 2021 08:48:02",
                "task-version": "1.0.0",
                "task-development-date": "2021/03",
                "task-name": "syntax",
            },
        ],
        "title_morphosyntax": [],
        "content_morphosyntax": [
            {"pos": "PUNCT", "lemma": "(", "text": "(", "is_oov": False},
            {"pos": "PROPN", "lemma": "CN111004497", "text": "CN111004497", "is_oov": True},
            {"pos": "PUNCT", "lemma": ")", "text": ")", "is_oov": False},
            {"pos": "NOUN", "lemma": "|1", "text": "|1", "is_oov": True},
            {"pos": "PUNCT", "lemma": ".", "text": ".", "is_oov": False},
            {"pos": "DET", "lemma": "the", "text": "The", "is_oov": False},
            {"pos": "VERB", "lemma": "electroplate", "text": "electroplating", "is_oov": False},
            {"pos": "NOUN", "lemma": "nylon", "text": "nylon", "is_oov": False},
            {"pos": "NOUN", "lemma": "material", "text": "material", "is_oov": False},
            {"pos": "VERB", "lemma": "be", "text": "is", "is_oov": False},
            {"pos": "VERB", "lemma": "characterize", "text": "characterized", "is_oov": False},
            {"pos": "ADP", "lemma": "by", "text": "by", "is_oov": False},
            {"pos": "VERB", "lemma": "comprise", "text": "comprising", "is_oov": False},
            {"pos": "DET", "lemma": "the", "text": "the", "is_oov": False},
            {"pos": "VERB", "lemma": "follow", "text": "following", "is_oov": False},
            {"pos": "NOUN", "lemma": "component", "text": "components", "is_oov": False},
            {"pos": "ADP", "lemma": "in", "text": "in", "is_oov": False},
            {"pos": "NOUN", "lemma": "part", "text": "parts", "is_oov": False},
            {"pos": "ADP", "lemma": "by", "text": "by", "is_oov": False},
            {"pos": "NOUN", "lemma": "weight", "text": "weight", "is_oov": False},
            {"pos": "PUNCT", "lemma": ":", "text": ":", "is_oov": False},
            {"pos": "NUM", "lemma": "50-80", "text": "50-80", "is_oov": False},
            {"pos": "NOUN", "lemma": "part", "text": "parts", "is_oov": False},
            {"pos": "ADP", "lemma": "of", "text": "of", "is_oov": False},
            {"pos": "NOUN", "lemma": "polyamide", "text": "polyamide", "is_oov": False},
            {"pos": "NUM", "lemma": "20-50", "text": "20-50", "is_oov": False},
            {"pos": "NOUN", "lemma": "part", "text": "parts", "is_oov": False},
            {"pos": "ADP", "lemma": "of", "text": "of", "is_oov": False},
            {"pos": "VERB", "lemma": "modify", "text": "modified", "is_oov": False},
            {"pos": "NOUN", "lemma": "mineral", "text": "mineral", "is_oov": False},
            {"pos": "NUM", "lemma": "2-8", "text": "2-8", "is_oov": False},
            {"pos": "NOUN", "lemma": "part", "text": "parts", "is_oov": False},
            {"pos": "ADP", "lemma": "of", "text": "of", "is_oov": False},
            {"pos": "DET", "lemma": "a", "text": "a", "is_oov": False},
            {"pos": "NOUN", "lemma": "compatilizer", "text": "compatilizer", "is_oov": True},
            {"pos": "PUNCT", "lemma": ".", "text": ".", "is_oov": False},
        ],
        "title_ner": [],
        "content_ner": [],
        "content_deps": [
            {"text": "(", "lemma": "(", "pos": "PUNCT", "head": 1, "dep": "punct", "lefts": [], "rights": []},
            {
                "text": "CN111004497",
                "lemma": "CN111004497",
                "pos": "PROPN",
                "head": 3,
                "dep": "nmod",
                "lefts": [0],
                "rights": [2],
            },
            {"text": ")", "lemma": ")", "pos": "PUNCT", "head": 1, "dep": "punct", "lefts": [], "rights": []},
            {"text": "|1", "lemma": "|1", "pos": "NOUN", "head": 3, "dep": "ROOT", "lefts": [1], "rights": [4]},
            {"text": ".", "lemma": ".", "pos": "PUNCT", "head": 3, "dep": "punct", "lefts": [], "rights": []},
            {"text": "The", "lemma": "the", "pos": "DET", "head": 8, "dep": "det", "lefts": [], "rights": []},
            {
                "text": "electroplating",
                "lemma": "electroplate",
                "pos": "VERB",
                "head": 8,
                "dep": "amod",
                "lefts": [],
                "rights": [],
            },
            {"text": "nylon", "lemma": "nylon", "pos": "NOUN", "head": 8, "dep": "compound", "lefts": [], "rights": []},
            {
                "text": "material",
                "lemma": "material",
                "pos": "NOUN",
                "head": 10,
                "dep": "nsubjpass",
                "lefts": [5, 6, 7],
                "rights": [],
            },
            {"text": "is", "lemma": "be", "pos": "VERB", "head": 10, "dep": "auxpass", "lefts": [], "rights": []},
            {
                "text": "characterized",
                "lemma": "characterize",
                "pos": "VERB",
                "head": 10,
                "dep": "ROOT",
                "lefts": [8, 9],
                "rights": [11, 35],
            },
            {"text": "by", "lemma": "by", "pos": "ADP", "head": 10, "dep": "prep", "lefts": [], "rights": [12]},
            {
                "text": "comprising",
                "lemma": "comprise",
                "pos": "VERB",
                "head": 11,
                "dep": "pcomp",
                "lefts": [],
                "rights": [15, 18, 20, 22],
            },
            {"text": "the", "lemma": "the", "pos": "DET", "head": 15, "dep": "det", "lefts": [], "rights": []},
            {"text": "following", "lemma": "follow", "pos": "VERB", "head": 15, "dep": "amod", "lefts": [], "rights": []},
            {
                "text": "components",
                "lemma": "component",
                "pos": "NOUN",
                "head": 12,
                "dep": "dobj",
                "lefts": [13, 14],
                "rights": [16],
            },
            {"text": "in", "lemma": "in", "pos": "ADP", "head": 15, "dep": "prep", "lefts": [], "rights": [17]},
            {"text": "parts", "lemma": "part", "pos": "NOUN", "head": 16, "dep": "pobj", "lefts": [], "rights": []},
            {"text": "by", "lemma": "by", "pos": "ADP", "head": 12, "dep": "prep", "lefts": [], "rights": [19]},
            {"text": "weight", "lemma": "weight", "pos": "NOUN", "head": 18, "dep": "pobj", "lefts": [], "rights": []},
            {"text": ":", "lemma": ":", "pos": "PUNCT", "head": 12, "dep": "punct", "lefts": [], "rights": []},
            {"text": "50-80", "lemma": "50-80", "pos": "NUM", "head": 22, "dep": "nummod", "lefts": [], "rights": []},
            {"text": "parts", "lemma": "part", "pos": "NOUN", "head": 12, "dep": "dobj", "lefts": [21], "rights": [23]},
            {"text": "of", "lemma": "of", "pos": "ADP", "head": 22, "dep": "prep", "lefts": [], "rights": [26]},
            {"text": "polyamide", "lemma": "polyamide", "pos": "NOUN", "head": 26, "dep": "nmod", "lefts": [], "rights": [25]},
            {"text": "20-50", "lemma": "20-50", "pos": "NUM", "head": 24, "dep": "nummod", "lefts": [], "rights": []},
            {"text": "parts", "lemma": "part", "pos": "NOUN", "head": 23, "dep": "pobj", "lefts": [24], "rights": [27]},
            {"text": "of", "lemma": "of", "pos": "ADP", "head": 26, "dep": "prep", "lefts": [], "rights": [31]},
            {"text": "modified", "lemma": "modify", "pos": "VERB", "head": 29, "dep": "amod", "lefts": [], "rights": []},
            {"text": "mineral", "lemma": "mineral", "pos": "NOUN", "head": 31, "dep": "nmod", "lefts": [28], "rights": []},
            {"text": "2-8", "lemma": "2-8", "pos": "NUM", "head": 31, "dep": "nummod", "lefts": [], "rights": []},
            {"text": "parts", "lemma": "part", "pos": "NOUN", "head": 27, "dep": "pobj", "lefts": [29, 30], "rights": [32]},
            {"text": "of", "lemma": "of", "pos": "ADP", "head": 31, "dep": "prep", "lefts": [], "rights": [34]},
            {"text": "a", "lemma": "a", "pos": "DET", "head": 34, "dep": "det", "lefts": [], "rights": []},
            {
                "text": "compatilizer",
                "lemma": "compatilizer",
                "pos": "NOUN",
                "head": 32,
                "dep": "pobj",
                "lefts": [33],
                "rights": [],
            },
            {"text": ".", "lemma": ".", "pos": "PUNCT", "head": 10, "dep": "punct", "lefts": [], "rights": []},
        ],
        "keywords": [{"text": "part", "span": {"start": 17, "end": 18}, "count": 4, "score": 100}],
    }

    def test_uniqword_reformulator(self):
        """Test reformulator"""

        (doc, lemma_q, content_q) = TextQueryReformulator.reformulate(query=TestTextQueryReformatulator.tkeir_doc)
        self.assertTrue(
            lemma_q
            == "part CN111004497 |1 electroplate nylon material be characterize comprise follow component weight polyamide modify mineral compatilizer"
        )
        self.assertTrue(
            content_q
            == "parts CN111004497 |1 electroplating nylon material is characterized comprising following components weight polyamide modified mineral compatilizer"
        )

    def test_uniqword_reformulator(self):
        """Test reformulator"""

        (doc, lemma_q, content_q) = TextQueryReformulator.reformulate(
            query=TestTextQueryReformatulator.tkeir_doc, boost_uniqword=True
        )
        self.assertTrue(
            lemma_q
            == "part part part part CN111004497 |1 electroplate nylon material be characterize comprise follow component weight polyamide modify mineral compatilizer"
        )
        self.assertTrue(
            content_q
            == "parts parts parts parts CN111004497 |1 electroplating nylon material is characterized comprising following components weight polyamide modified mineral compatilizer"
        )

    def test_reformulator(self):
        """Test reformulator"""
        (doc, lemma_q, content_q) = TextQueryReformulator.reformulate(
            query=TestTextQueryReformatulator.tkeir_doc, boost_uniqword=False, uniqword=False
        )
        self.assertTrue(
            lemma_q
            == "CN111004497 |1 electroplate nylon material be characterize comprise follow component part weight part polyamide part modify mineral part compatilizer"
        )
        self.assertTrue(
            content_q
            == "CN111004497 |1 electroplating nylon material is characterized comprising following components parts weight parts polyamide parts modified mineral parts compatilizer"
        )
