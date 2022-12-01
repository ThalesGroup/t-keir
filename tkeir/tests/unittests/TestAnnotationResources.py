# -*- coding: utf-8 -*-
"""Test Annotation Resources
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.core.ThotLogger import ThotLogger
from thot.tasks.tokenizer.AnnotationConfiguration import AnnotationConfiguration
from thot.tasks.tokenizer.AnnotationResources import AnnotationResources
import json
import os
import unittest


class TestAnnotationResources(unittest.TestCase):

    test_dict = {
        "logger": {"logging-level": "debug"},
        "resources-base-path": "/home/tkeir_svc/tkeir/thot/tests/data",
        "data": [
            {
                "lists": [
                    {
                        "format": {"type": "csv", "header": False, "sep": "\t", "columns": [{"id": 4}]},
                        "name": "geoname-country",
                        "path": "countryInfo.txt",
                        "exceptions": ["stopwords.txt"],
                        "pos": "PROPN",
                        "add-ascii-folding": True,
                        "label": "location.country",
                        "weight": 10,
                    },
                    {
                        "format": {
                            "type": "csv",
                            "header": False,
                            "sep": "\t",
                            "columns": [{"id": 1}, {"id": 3, "split-on": ","}],
                        },
                        "download": {"url": "http://download.geonames.org/export/dump/cities5000.zip", "format": "zip"},
                        "name": "geoname-city",
                        "path": "cities5000.txt",
                        "exceptions": ["stopwords.txt"],
                        "pos": "PROPN",
                        "label": "location.city",
                        "add-ascii-folding": True,
                        "weight": 10,
                    },
                    {
                        "format": {"type": "csv", "header": True, "sep": ",", "columns": [{"id": 2}]},
                        "name": "fortune500-company",
                        "path": "fortune500.csv",
                        "exceptions": ["stopwords.txt"],
                        "pos": "PROPN",
                        "add-ascii-folding": True,
                        "label": "organization",
                        "weight": 10,
                    },
                    {
                        "format": {"type": "csv", "header": True, "sep": ",", "columns": [{"id": 4}]},
                        "name": "fortune500-industry",
                        "path": "fortune500.csv",
                        "exceptions": ["stopwords.txt"],
                        "pos": "NOUN",
                        "add-ascii-folding": True,
                        "label": "industry",
                        "weight": 10,
                    },
                    {
                        "format": {"type": "list"},
                        "name": "job-title",
                        "path": "job_titles.txt",
                        "exceptions": ["stopwords.txt"],
                        "pos": "NOUN",
                        "add-ascii-folding": True,
                        "label": "jobtitle",
                        "weight": 10,
                    },
                ]
            }
        ],
    }

    def test_createModel(self):
        """Test create model function"""
        annot_config = AnnotationConfiguration()
        ThotLogger.loads(TestAnnotationResources.test_dict, logger_name="test-annotation")
        annot_config.loads(TestAnnotationResources.test_dict)

        annotte_modeling = AnnotationResources()
        annotte_modeling.createModel(annot_config.configuration, "/tmp/outmodel.pkl")
        self.assertTrue(True)
