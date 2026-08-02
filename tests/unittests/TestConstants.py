"""Title: Test Annotation Configuration

Automated tests for T-KEIR (unit / functional).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import unittest

import thot.core.Constants as Constants


class TestConstants(unittest.TestCase):
    def test_exception_error_and_trace(self):
        self.assertEqual(
            Constants.exception_error_and_trace("a", "b"),
            "Exception:a - Trace:b",
        )
