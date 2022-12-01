# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2021 by THALES
"""

import unittest
from unittest import mock
import os
import json
from thot.tasks.searching.TermVectors import TermVectors
from thot.tasks.searching.Scorer import Scorer


def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

    if "cacheid_1f3406322166594eccd0616138f0b1ab" in args[0]:
        return MockResponse(TestScorer.DOC_TEST, 200)
    return MockResponse(TestScorer.Q_TEST, 200)


class TestScorer(unittest.TestCase):

    DOC_TEST = None
    Q_TEST = None

    @classmethod
    def setUpClass(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.data_path = os.path.abspath(os.path.join(dir_path, "../data/test-index"))
        self.opendistro_host = "opendistro"
        if "OPENDISTRO_DNS_HOST" in os.environ:
            self.opendistro_host = os.environ["OPENDISTRO_DNS_HOST"]

        with open(os.path.join(self.data_path, "scorer_doc.json")) as doc_f:
            TestScorer.DOC_TEST = json.load(doc_f)
            doc_f.close()
        with open(os.path.join(self.data_path, "scorer_q.json")) as q_f:
            TestScorer.Q_TEST = json.load(q_f)
            q_f.close()

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_documentQueryIntersectionScore(self, get_mock):
        tv = TermVectors(
            {"index": "text-index-test", "es-url": "https://admin:admin@" + self.opendistro_host + ":9200", "es-verify": False}
        )
        doc = tv.docId2TermVector(
            "cacheid_1f3406322166594eccd0616138f0b1ab",
            [
                "title",
                "content",
            ],
        )
        q = tv.query2TermVector(
            {
                "title": ["FAKEWORD Back doorknob durability test device"],
                "content": "drive air cylinder  automobile back door handle",
            }
        )

        self.assertEqual(
            Scorer.documentQueryIntersectionScore(query=q, document=doc, normalize=Scorer.NORMALIZE_BY_UNION_SIZE),
            0.03426791277258567,
        )
        self.assertEqual(
            Scorer.documentQueryIntersectionScore(query=q, document=doc, normalize=Scorer.NORMALIZE_BY_DOCUMENT_SIZE), 0.034375
        )
        self.assertEqual(
            Scorer.documentQueryIntersectionScore(query=q, document=doc, normalize=Scorer.NORMALIZE_BY_INTERSECTION_SIZE), 1.0
        )
        self.assertEqual(Scorer.documentQueryIntersectionScore(query=q, document=doc), 0.9166666666666666)
