# -*- coding: utf-8 -*-
"""Test Annotation Configuration
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

import thot.core.Constants as Constants

import unittest


class TestConstants(unittest.TestCase):
    def test_exception_error_and_trace(self):
        self.assertEqual(Constants.exception_error_and_trace("a", "b"), "Exception:a - Trace:b")
