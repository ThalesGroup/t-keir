# -*- coding: utf-8 -*-
"""Test Annotation Configuration
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.index_client import process_file

import unittest
from unittest import mock
import requests
import os


def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return {"results": {"testing": "test"}}

    return MockResponse({}, TestIndexClient.HTTP_STATUS)


class TestIndexClient(unittest.TestCase):

    HTTP_STATUS = 200

    @mock.patch("requests.post", side_effect=mocked_requests_get)
    def test_process_file(self, get_mock):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.data_path = os.path.abspath(os.path.join(dir_path, "../data/test-outputs-kw/"))
        test_file = os.path.join(self.data_path, "enron.txt.converted.tokenized.ms.ner.syntax.kw.json")

        class args:
            output = "/tmp/"
            scheme = "http"
            no_ssl_verify = False

        self.assertEqual(process_file(args, "localhost", 8080, test_file), "ok")

    @mock.patch("requests.post", side_effect=mocked_requests_get)
    def test_process_file_exception(self, get_mock):
        TestIndexClient.HTTP_STATUS = 500
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.data_path = os.path.abspath(os.path.join(dir_path, "../data/test-outputs-kw/"))
        test_file = os.path.join(self.data_path, "enron.txt.converted.tokenized.ms.ner.syntax.kw.json")

        class args:
            output = "/tmp/"
            scheme = "http"
            no_ssl_verify = False

        self.assertNotEqual(process_file(args, "localhost", 8080, test_file), "ok")
