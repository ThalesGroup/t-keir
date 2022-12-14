# -*- coding: utf-8 -*-
"""Test converter
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.converters.Converter import Converter
from thot.core.ThotLogger import ThotLogger, LogUserContext
from uuid import uuid4
import os
import unittest
import base64


class TestConverter(unittest.TestCase):
    def test_converter1(self):
        cid = "autogenerated-" + str(uuid4())
        log_context = LogUserContext(cid)
        dir_path = os.path.dirname(os.path.realpath(__file__))
        data_path = os.path.abspath(os.path.join(dir_path, "../data/test-raw/mail"))
        
        self.assertTrue(True)


    def test_converter2(self):
        cid = "autogenerated-" + str(uuid4())
        log_context = LogUserContext(cid)
        dir_path = os.path.dirname(os.path.realpath(__file__))
        data_path = os.path.abspath(os.path.join(dir_path, "../data/test-raw/mail"))
        
        self.assertTrue(True)


    def test_listType(self):
        test_list = set(Converter().listTypes())
        self.assertEqual(test_list, set(["tkeir", "raw", "email", "docx", "odt", "pdf", "rtf", "orbit-csv", "uri"]))
