# -*- coding: utf-8 -*-
"""Test Query Exapansion
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2021 by THALES
"""

import unittest
from unittest import mock
import os
import json
import py7zr
from thot.tasks.searching.QueryExpansion import QueryExpansion
from thot.core.ThotLogger import ThotLogger, LogUserContext


def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code
            self.text = json.dumps(json_data)

        def json(self):
            return self.json_data

    if TestQueryExpansion.TEST_CASE == "docIdToTermVector":
        return MockResponse(TestQueryExpansion.DOCID2TERMVECTOR, 200)
    if TestQueryExpansion.TEST_CASE == "query2TermVector":
        return MockResponse(TestQueryExpansion.QUERY2TERMVECTOR, 200)
    if TestQueryExpansion.TEST_CASE == "expandWithDocId":
        for doc in TestQueryExpansion.EXPANDWITHDOCIDS_DOCS:
            if (
                doc["_id"]
                in [
                    "cacheid_919dd45493022ad85f8cda857b9b41ad",
                    "cacheid_50c4c5ed0104a1beb2f57f94e70c7759",
                    "cacheid_1543ceb2a634405c5a8cbfebb283855c",
                ]
            ) and (doc["_id"] in args[0]):
                return MockResponse(doc, 200)
        return MockResponse(TestQueryExpansion.EXPANDWITHDOCIDS, 200)
    if TestQueryExpansion.TEST_CASE == "getDocIdsWithRequest":
        return MockResponse(TestQueryExpansion.GETDOCIDWITHREQUEST, 200)

    return MockResponse("{}", 200)


class TestQueryExpansion(unittest.TestCase):

    TEST_CASE = ""

    @classmethod
    def setUpClass(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.data_path = os.path.abspath(os.path.join(dir_path, "../data/test-index"))
        self.opendistro_host = "opendistro"
        if "OPENDISTRO_DNS_HOST" in os.environ:
            self.opendistro_host = os.environ["OPENDISTRO_DNS_HOST"]

        with open(os.path.join(self.data_path, "qe_docid2termvector.json")) as doc_f:
            TestQueryExpansion.DOCID2TERMVECTOR = json.load(doc_f)
            doc_f.close()
        with open(os.path.join(self.data_path, "qe_expandwithdocids.json")) as doc_f:
            TestQueryExpansion.EXPANDWITHDOCIDS = json.load(doc_f)
            doc_f.close()
        with open(os.path.join(self.data_path, "qe_getdocidwithrequest.json")) as doc_f:
            TestQueryExpansion.GETDOCIDWITHREQUEST = json.load(doc_f)
            doc_f.close()
        with open(os.path.join(self.data_path, "qe_query2termvector.json")) as doc_f:
            TestQueryExpansion.QUERY2TERMVECTOR = json.load(doc_f)
            doc_f.close()
        with open(os.path.join(self.data_path, "qe_expandwithdocid_docs.json")) as doc_f:
            TestQueryExpansion.EXPANDWITHDOCIDS_DOCS = json.load(doc_f)
            doc_f.close()

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_docIdToTermVector(self, get_mock):
        TestQueryExpansion.TEST_CASE = "docIdToTermVector"
        qe = QueryExpansion(
            {
                "index": "text-index-test",
                "es-url": "https://admin:admin@" + self.opendistro_host + ":9200",
                "es-verify": False,
                "keep_word_collection_thresold_under": 0.25,
                "word_boost_thresold_above": 0.25,
            }
        )
        r = qe._docId2TermVector(
            "cacheid_8d4fb22cfcca57beb041971f53904a2d",
            [
                "title",
                "lemma_title",
            ],
        )
        self.assertEqual(
            r["term_vectors"],
            {
                "title": {
                    "field_statistics": {"sum_doc_freq": 1822, "doc_count": 196, "sum_ttf": 2036},
                    "terms": {
                        "composit": {
                            "doc_freq": 70,
                            "ttf": 72,
                            "term_freq": 1,
                            "tokens": [{"position": 2, "start_offset": 20, "end_offset": 31}],
                        },
                        "gloss": {
                            "doc_freq": 2,
                            "ttf": 2,
                            "term_freq": 1,
                            "tokens": [{"position": 5, "start_offset": 41, "end_offset": 46}],
                        },
                        "low": {
                            "doc_freq": 8,
                            "ttf": 8,
                            "term_freq": 1,
                            "tokens": [{"position": 4, "start_offset": 37, "end_offset": 40}],
                        },
                        "resin": {
                            "doc_freq": 52,
                            "ttf": 58,
                            "term_freq": 1,
                            "tokens": [{"position": 1, "start_offset": 14, "end_offset": 19}],
                        },
                        "thermoplast": {
                            "doc_freq": 10,
                            "ttf": 10,
                            "term_freq": 1,
                            "tokens": [{"position": 0, "start_offset": 0, "end_offset": 13}],
                        },
                    },
                },
                "lemma_title": {
                    "field_statistics": {"sum_doc_freq": 1768, "doc_count": 196, "sum_ttf": 1954},
                    "terms": {
                        "composition": {
                            "doc_freq": 52,
                            "ttf": 54,
                            "term_freq": 1,
                            "tokens": [{"position": 2, "start_offset": 21, "end_offset": 32}],
                        },
                        "gloss": {
                            "doc_freq": 2,
                            "ttf": 2,
                            "term_freq": 1,
                            "tokens": [{"position": 4, "start_offset": 37, "end_offset": 42}],
                        },
                        "low": {
                            "doc_freq": 8,
                            "ttf": 8,
                            "term_freq": 1,
                            "tokens": [{"position": 3, "start_offset": 33, "end_offset": 36}],
                        },
                        "resin": {
                            "doc_freq": 34,
                            "ttf": 34,
                            "term_freq": 1,
                            "tokens": [{"position": 1, "start_offset": 15, "end_offset": 20}],
                        },
                        "thermoplastic": {
                            "doc_freq": 10,
                            "ttf": 10,
                            "term_freq": 1,
                            "tokens": [{"position": 0, "start_offset": 1, "end_offset": 14}],
                        },
                    },
                },
            },
        )

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_query2TermVector(self, get_mock):
        TestQueryExpansion.TEST_CASE = "query2TermVector"
        qe = QueryExpansion(
            {
                "index": "text-index-test",
                "es-url": "https://admin:admin@" + self.opendistro_host + ":9200",
                "es-verify": False,
                "keep_word_collection_thresold_under": 0.25,
                "word_boost_thresold_above": 0.25,
            }
        )
        r = qe._query2TermVector(
            {"title": ["Back doorknob durability test device"], "lemma_title": "doorknob durability test device"}
        )
        self.assertEqual(
            r["term_vectors"],
            {
                "lemma_title": {
                    "field_statistics": {"sum_doc_freq": 1768, "doc_count": 196, "sum_ttf": 1954},
                    "terms": {
                        "device": {
                            "doc_freq": 8,
                            "ttf": 12,
                            "term_freq": 1,
                            "tokens": [{"position": 3, "start_offset": 25, "end_offset": 31}],
                        },
                        "doorknob": {
                            "doc_freq": 2,
                            "ttf": 2,
                            "term_freq": 1,
                            "tokens": [{"position": 0, "start_offset": 0, "end_offset": 8}],
                        },
                        "durability": {
                            "doc_freq": 2,
                            "ttf": 2,
                            "term_freq": 1,
                            "tokens": [{"position": 1, "start_offset": 9, "end_offset": 19}],
                        },
                        "test": {
                            "doc_freq": 2,
                            "ttf": 2,
                            "term_freq": 1,
                            "tokens": [{"position": 2, "start_offset": 20, "end_offset": 24}],
                        },
                    },
                },
                "title": {
                    "field_statistics": {"sum_doc_freq": 1822, "doc_count": 196, "sum_ttf": 2036},
                    "terms": {
                        "back": {
                            "doc_freq": 2,
                            "ttf": 2,
                            "term_freq": 1,
                            "tokens": [{"position": 0, "start_offset": 0, "end_offset": 4}],
                        },
                        "devic": {
                            "doc_freq": 8,
                            "ttf": 12,
                            "term_freq": 1,
                            "tokens": [{"position": 4, "start_offset": 30, "end_offset": 36}],
                        },
                        "doorknob": {
                            "doc_freq": 2,
                            "ttf": 2,
                            "term_freq": 1,
                            "tokens": [{"position": 1, "start_offset": 5, "end_offset": 13}],
                        },
                        "durabl": {
                            "doc_freq": 2,
                            "ttf": 2,
                            "term_freq": 1,
                            "tokens": [{"position": 2, "start_offset": 14, "end_offset": 24}],
                        },
                        "test": {
                            "doc_freq": 2,
                            "ttf": 2,
                            "term_freq": 1,
                            "tokens": [{"position": 3, "start_offset": 25, "end_offset": 29}],
                        },
                    },
                },
            },
        )

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_expandWithDocId(self, get_mock):
        TestQueryExpansion.TEST_CASE = "expandWithDocId"
        qe = QueryExpansion(
            {
                "index": "text-index-test",
                "es-url": "https://admin:admin@" + self.opendistro_host + ":9200",
                "es-verify": False,
                "keep_word_collection_thresold_under": 0.4,
                "word_boost_thresold_above": 0.25,
            }
        )
        q = qe.expandWithDocId(
            {"content": ["invention halogen-free"]},
            [
                "cacheid_919dd45493022ad85f8cda857b9b41ad",
                "cacheid_50c4c5ed0104a1beb2f57f94e70c7759",
                "cacheid_1543ceb2a634405c5a8cbfebb283855c",
            ],
        )
        self.assertEqual(
            q,
            {
                "title": [("guitar", 1.0), ("oxid", 1.0), ("spun", 1.0), ("summer", 1.0), ("sweater", 1.0), ("yarn", 1.0)],
                "content": [
                    ("free", 5.608695652173914),
                    ("halogen", 5.608695652173914),
                    ("099863", 1.8695652173913044),
                    ("201710683310.1", 1.8695652173913044),
                    ("2018", 1.8695652173913044),
                    ("301", 1.8695652173913044),
                    ("303", 1.8695652173913044),
                    ("acacia", 1.8695652173913044),
                    ("accessori", 1.8695652173913044),
                    ("accru", 1.8695652173913044),
                    ("adaptor", 1.8695652173913044),
                    ("administr", 1.8695652173913044),
                    ("affectedbi", 1.8695652173913044),
                    ("andhumid", 1.8695652173913044),
                    ("anempti", 1.8695652173913044),
                    ("audienc", 1.8695652173913044),
                    ("cn2018", 1.8695652173913044),
                    ("cumbersom", 1.8695652173913044),
                    ("dimensional0.1", 1.8695652173913044),
                    ("dovetail", 1.8695652173913044),
                    ("explod", 1.8695652173913044),
                    ("fretboard", 1.8695652173913044),
                    ("guitar", 1.8695652173913044),
                    ("guitar'", 1.8695652173913044),
                    ("headstock", 1.8695652173913044),
                    ("loudness55db49db43db52db", 1.8695652173913044),
                    ("m24.9kj", 1.8695652173913044),
                    ("m27.9kj", 1.8695652173913044),
                    ("m28.8kj", 1.8695652173913044),
                    ("m2materialguitar", 1.8695652173913044),
                    ("mahogani", 1.8695652173913044),
                    ("materialbend", 1.8695652173913044),
                    ("membership", 1.8695652173913044),
                    ("month", 1.8695652173913044),
                    ("obscur", 1.8695652173913044),
                    ("of120mpa45mpa60mpa66mpamaterialimpact", 1.8695652173913044),
                    ("of16kj", 1.8695652173913044),
                    ("of19gpa7gpa7gpa8gpaelast", 1.8695652173913044),
                    ("pillow", 1.8695652173913044),
                    ("pleas", 1.8695652173913044),
                    ("pluck", 1.8695652173913044),
                    ("plung", 1.8695652173913044),
                    ("procur", 1.8695652173913044),
                    ("sameveloc", 1.8695652173913044),
                    ("sandblast", 1.8695652173913044),
                    ("sander", 1.8695652173913044),
                    ("seamless", 1.8695652173913044),
                    ("soundboard", 1.8695652173913044),
                    ("spruce", 1.8695652173913044),
                    ("subroutin", 1.8695652173913044),
                    ("sustain7.8s7.1s6.6s7.2", 1.8695652173913044),
                    ("thesam", 1.8695652173913044),
                    ("thissprucemahoganyacaciaitemapplicationguitarguitarguitar", 1.8695652173913044),
                    ("tuner", 1.8695652173913044),
                    ("u.s.c", 1.8695652173913044),
                    ("us10984764", 1.8695652173913044),
                    ("24c", 1.8695652173913044),
                    ("amt", 1.8695652173913044),
                    ("compsn", 1.8695652173913044),
                    ("cpd", 1.8695652173913044),
                    ("epoxycyclohexancarboxyl", 1.8695652173913044),
                    ("substd", 1.8695652173913044),
                    ("w.r.t", 1.8695652173913044),
                    ("0.5wt", 1.8695652173913044),
                    ("dimethylsufoxid", 1.8695652173913044),
                    ("japio", 1.8695652173913044),
                    ("modacryl", 1.8695652173913044),
                    ("sweater", 1.8695652173913044),
                    ("bucket", 1.713768115942029),
                    ("string", 1.7069943289224954),
                    ("bridg", 1.5100334448160537),
                    ("player", 1.4956521739130437),
                    ("acoust", 1.4021739130434785),
                    ("glu", 1.4021739130434785),
                    ("labor", 1.4021739130434785),
                    ("spun", 1.2463768115942029),
                    ("music", 1.1217391304347826),
                    ("reson", 1.1217391304347826),
                    ("deck", 1.0683229813664596),
                    ("bodi", 1.0584311019093628),
                    ("instal", 1.0546265328874025),
                    ("board", 1.0386473429951693),
                    ("barrel", 1.0),
                ],
            },
        )

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_getDocIdsWithRequest(self, get_mock):
        TestQueryExpansion.TEST_CASE = "getDocIdsWithRequest"
        qe = QueryExpansion(
            {
                "index": "text-index-test",
                "es-url": "https://admin:admin@" + self.opendistro_host + ":9200",
                "es-verify": False,
                "keep_word_collection_thresold_under": 0.4,
                "word_boost_thresold_above": 0.25,
            }
        )
        log_context = LogUserContext("generated-xxx")
        docids = qe.getDocIdsWithRequest(
            {
                "query": {
                    "nested": {
                        "path": "kg.subject",
                        "query": {"match": {"kg.subject.content": "us10984764|us20200184936|wo2019/029669|cn107369432"}},
                    }
                }
            },
            call_context=log_context,
        )
        self.assertEqual(docids, ["cacheid_919dd45493022ad85f8cda857b9b41ad"])
