# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2021 by THALES
"""

import unittest
import os
import py7zr
import json
from thot.tasks.searching.TextQueryFormulator import TextQueryFormulator


class TestTextQueryFormulator(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.data_path = os.path.abspath(os.path.join(dir_path, "../data/test-query"))
        print("Extract data:", os.path.join(self.data_path, "big_query_document.json.7z"))

        try:
            """
            with py7zr.SevenZipFile(os.path.join(self.data_path,'big_query_document.json.7z'), mode='r') as z:
                z.extractall(path=self.data_path)
            """
            with open(os.path.join(self.data_path, "big_query_document.json"), encoding="utf-8") as doc_f:
                self.tkeir_doc = json.load(doc_f)
                doc_f.close()
            self.tqf = TextQueryFormulator()
            self.config = {
                "use-basic-querying": True,
                "use-lemma": True,
                "use-keywords": True,
                "use-knowledge-graph": True,
                "use-semantic-keywords": False,
                "use-semantic-knowledge-graph": False,
                "use-concepts": False,
                "querying": {
                    "match-phrase-slop": 3,
                    "match-phrase-boosting": 2,
                    "match-sentence": {"number-and-symbol-filtering": False},
                    "match-keyword": {
                        "number-and-symbol-filtering": False,
                        "semantic-skip-highest-ranked-classes": 3,
                        "semantic-max-boosting": 4000,
                    },
                    "match-svo": {
                        "semantic-use-class-triple": True,
                        "semantic-use-lemma-property-object": True,
                        "semantic-use-subject-lemma-object": True,
                        "semantic-use-subject-property-lemma": True,
                        "semantic-use-lemma-lemma-object": True,
                        "semantic-use-lemma-property-lemma": True,
                        "semantic-use-subject-lemma-lemma": True,
                        "semanic-max-boosting": 5,
                    },
                },
            }
        except Exception as e:
            print(str(e))

    @classmethod
    def tearDownClass(self):
        pass

    def test_generateQuery(self):
        queryType = []
        basic_query = True
        sentence_query = True
        keyword_query = True
        svo_query = True
        semantic_keyword_query = True
        semantic_svo_query = True
        if basic_query:
            queryType.append(self.tqf.dummyContent(self.tkeir_doc, maxsize=1024))
        if sentence_query:
            queryType.append(self.tqf.sentencesByScore(self.tkeir_doc))
        if keyword_query:
            queryType.append(self.tqf.keywordsByScore(self.tkeir_doc))
        if svo_query:
            queryType.append(self.tqf.svoByScore(self.tkeir_doc))
        if semantic_keyword_query:
            queryType.append(self.tqf.semanticKeywords(self.tkeir_doc, self.config))
        if semantic_svo_query:
            queryType.append(self.tqf.semanticSVO(self.tkeir_doc, self.config))
        self.tqf.generateQuery(queryType, self.config)
