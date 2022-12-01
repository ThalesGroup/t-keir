# -*- coding: utf-8 -*-
"""Test Annotation Configuration
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.clusterinfer_client import process_file

import unittest
from unittest import mock
import requests
import os


class TestEmbbeddingsClient(unittest.TestCase):
    def test_empty(self):
        self.assertTrue(True)
