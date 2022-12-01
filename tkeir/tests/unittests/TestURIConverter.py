# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.converters.URIConverter import URIConverter
import json
import os
import unittest


class TestURIConverter(unittest.TestCase):
    def test_converter(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        document = URIConverter.convert("http://www.example.com".encode("utf-8"), "http://www.example.com")
        self.assertEqual(document["title"], "Example Domain")
        self.assertEqual(
            document["content"],
            [
                "Example Domain\nExample Domain\nThis domain is for use in illustrative examples in documents. You may use this\n    domain in literature without prior coordination or asking for permission.\nMore information..." 
            ],
        )
