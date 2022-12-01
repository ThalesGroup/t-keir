# -*- coding: utf-8 -*-
"""Test Indexing configuration
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.indexing.IndexingConfiguration import IndexingConfiguration
import unittest
import json
import os


class TestIndexingConfiguration(unittest.TestCase):

    test_dict = {
        "logger": {"logging-level": "debug"},
        "indexing": {
            "document": {"remove-knowledge-graph-duplicates": True},
            "elasticsearch": {
                "network": {
                    "host": "0.0.0.0",
                    "port": 9200,
                    "use_ssl": False,
                    "verify_certs": False,
                    "associate-environment": {"host": "O_HOST", "port": "O_PORT"},
                },
                "nms-index": {
                    "name": "nms-index",
                    "mapping-file": "/home/tkeir_svc/tkeir/resources/indices/indices_mapping/nms_cache_index.json",
                },
                "text-index": {
                    "name": "text-index",
                    "mapping-file": "/home/tkeir_svc/tkeir/resources/indices/indices_mapping/cache_index.json",
                },
                "relation-index": {
                    "name": "relation-index",
                    "mapping-file": "/home/tkeir_svc/tkeir/resources/indices/indices_mapping/relation_index.json",
                },
            },
            "network": {
                "host": "0.0.0.0",
                "port": 10012,
                "associate-environment": {"host": "INDEX_HOST", "port": "INDEX_PORT"},
            },
            "runtime": {
                "request-max-size": 100000000,
                "request-buffer-queue-size": 100,
                "keep-alive": True,
                "keep-alive-timeout": 5,
                "graceful-shutown-timeout": 15.0,
                "request-timeout": 60,
                "response-timeout": 60,
                "workers": 1,
            },
            "serialize": {
                "input": {"path": "/tmp", "keep-service-info": True},
                "output": {"path": "/tmp", "keep-service-info": True},
            },
        },
    }

    test_dict_env = {
        "logger": {"logging-level": "debug"},
        "indexing": {
            "document": {"remove-knowledge-graph-duplicates": True},
            "elasticsearch": {
                "network": {
                    "host": "http://1234",
                    "port": 2900,
                    "use_ssl": False,
                    "verify_certs": False,
                    "associate-environment": {"host": "O_HOST", "port": "O_PORT"},
                },
                "nms-index": {
                    "name": "nms-index",
                    "mapping-file": "/home/tkeir_svc/tkeir/resources/indices/indices_mapping/nms_cache_index.json",
                },
                "text-index": {
                    "name": "text-index",
                    "mapping-file": "/home/tkeir_svc/tkeir/resources/indices/indices_mapping/cache_index.json",
                },
                "relation-index": {
                    "name": "relation-index",
                    "mapping-file": "/home/tkeir_svc/tkeir/resources/indices/indices_mapping/relation_index.json",
                },
            },
            "serialize": {
                "input": {"path": "/tmp", "keep-service-info": True},
                "output": {"path": "/tmp", "keep-service-info": True},
            },
        },
    }

    def test_load(self):
        try:
            with open("/tmp/cfg.json", "w") as f:
                json.dump(TestIndexingConfiguration.test_dict, f)
                f.close()
        except Exception as e:
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        if "O_HOST" in os.environ:
            del os.environ["O_HOST"]
        if "O_PORT" in os.environ:
            del os.environ["O_PORT"]
        indexingConfig = IndexingConfiguration()
        indexingConfig.load(fh)
        fh.close()
        self.assertEqual(indexingConfig.logger_config.configuration["logger"], TestIndexingConfiguration.test_dict["logger"])
        TestIndexingConfiguration.test_dict["indexing"]["serialize"]["do-serialization"] = True

        self.assertEqual(
            indexingConfig.configuration["elasticsearch"], TestIndexingConfiguration.test_dict["indexing"]["elasticsearch"]
        )

    def test_loads(self):
        if "O_HOST" in os.environ:
            del os.environ["O_HOST"]
        if "O_PORT" in os.environ:
            del os.environ["O_PORT"]
        indexingConfig = IndexingConfiguration()
        indexingConfig.loads(TestIndexingConfiguration.test_dict)
        self.assertEqual(indexingConfig.logger_config.configuration["logger"], TestIndexingConfiguration.test_dict["logger"])
        TestIndexingConfiguration.test_dict["indexing"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            indexingConfig.configuration["elasticsearch"], TestIndexingConfiguration.test_dict["indexing"]["elasticsearch"]
        )

    def test_load_with_env(self):
        if "O_HOST" in os.environ:
            del os.environ["O_HOST"]
        if "O_PORT" in os.environ:
            del os.environ["O_PORT"]
        os.environ["O_HOST"] = "http://1234"
        os.environ["O_PORT"] = "2900"
        try:
            with open("/tmp/cfg.json", "w") as f:
                json.dump(TestIndexingConfiguration.test_dict, f)
                f.close()
        except Exception as e:
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        indexingConfig = IndexingConfiguration()
        indexingConfig.load(fh)
        fh.close()
        self.assertEqual(
            indexingConfig.logger_config.configuration["logger"], TestIndexingConfiguration.test_dict_env["logger"]
        )
        TestIndexingConfiguration.test_dict_env["indexing"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            indexingConfig.configuration["elasticsearch"], TestIndexingConfiguration.test_dict_env["indexing"]["elasticsearch"]
        )

    def test_loads_with_env(self):
        if "O_HOST" in os.environ:
            del os.environ["O_HOST"]
        if "O_HOST" in os.environ:
            del os.environ["O_PORT"]
        os.environ["O_HOST"] = "http://1234"
        os.environ["O_PORT"] = "2900"
        indexingConfig = IndexingConfiguration()
        indexingConfig.loads(TestIndexingConfiguration.test_dict)
        self.assertEqual(
            indexingConfig.logger_config.configuration["logger"], TestIndexingConfiguration.test_dict_env["logger"]
        )
        TestIndexingConfiguration.test_dict_env["indexing"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            indexingConfig.configuration["elasticsearch"], TestIndexingConfiguration.test_dict_env["indexing"]["elasticsearch"]
        )

    def test_clear(self):
        indexingConfig = IndexingConfiguration()
        indexingConfig.loads(TestIndexingConfiguration.test_dict)
        indexingConfig.clear()
        self.assertEqual(indexingConfig.logger_config.logger_name, "default")
        self.assertEqual(indexingConfig.logger_config.configuration, None)
        self.assertEqual(indexingConfig.configuration, dict())
