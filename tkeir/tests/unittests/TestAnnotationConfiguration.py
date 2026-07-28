# -*- coding: utf-8 -*-
"""Test Annotation Configuration
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.tokenizer.AnnotationConfiguration import AnnotationConfiguration
import json
import os
import unittest


class TestAnnotationConfiguration(unittest.TestCase):

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

    def test_load(self):
        """Test load with file function"""

        try:
            with open("/tmp/cfg.json", "w") as f:
                json.dump(TestAnnotationConfiguration.test_dict, f)
                f.close()
        except Exception as e:
            self.assertFalse(True)

        fh = open("/tmp/cfg.json")
        annotation_config = AnnotationConfiguration()
        annotation_config.load(fh)
        fh.close()
        self.assertEqual(annotation_config.configuration, TestAnnotationConfiguration.test_dict)

    def test_loads(self):
        """Test load with dict function"""
        annotation_config = AnnotationConfiguration()
        annotation_config.loads(TestAnnotationConfiguration.test_dict)
        self.assertEqual(annotation_config.configuration, TestAnnotationConfiguration.test_dict)

    def test_clear(self):
        annotation_config = AnnotationConfiguration()
        annotation_config.loads(TestAnnotationConfiguration.test_dict)
        annotation_config.clear()
        self.assertEqual(annotation_config.configuration, None)
