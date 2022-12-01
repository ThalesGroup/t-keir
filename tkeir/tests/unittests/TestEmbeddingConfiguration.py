# -*- coding: utf-8 -*-
"""Test embedding configuration
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.embeddings.EmbeddingsConfiguration import EmbeddingsConfiguration
import os
import unittest
import json


class TestEmbeddingConfiguration(unittest.TestCase):

    test_dict = {
        "logger": {"logging-level": "debug"},
        "embeddings": {
            "models": [{"language": "multi"}],
            "network": {
                "host": "0.0.0.0",
                "port": 8080,
                "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"},
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

    def test_load(self):
        try:
            with open("/tmp/cfg.json", "w") as f:
                json.dump(TestEmbeddingConfiguration.test_dict, f)
                f.close()
        except Exception as e:
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        if "HOST_ENVNAME" in os.environ:
            del os.environ["HOST_ENVNAME"]
        if "PORT_ENVNAME" in os.environ:
            del os.environ["PORT_ENVNAME"]
        embeddingConfig = EmbeddingsConfiguration()
        embeddingConfig.load(fh)
        fh.close()

        self.assertEqual(embeddingConfig.logger_config.configuration["logger"], TestEmbeddingConfiguration.test_dict["logger"])
        self.assertEqual(
            embeddingConfig.net_config.configuration["network"], TestEmbeddingConfiguration.test_dict["embeddings"]["network"]
        )
        TestEmbeddingConfiguration.test_dict["embeddings"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            embeddingConfig.runtime_config.configuration["runtime"],
            TestEmbeddingConfiguration.test_dict["embeddings"]["runtime"],
        )
        self.assertEqual(embeddingConfig.configuration["models"], TestEmbeddingConfiguration.test_dict["embeddings"]["models"])

    def test_loads(self):
        if "HOST_ENVNAME" in os.environ:
            del os.environ["HOST_ENVNAME"]
        if "PORT_ENVNAME" in os.environ:
            del os.environ["PORT_ENVNAME"]
        embeddingConfig = EmbeddingsConfiguration()
        embeddingConfig.loads(TestEmbeddingConfiguration.test_dict)
        self.assertEqual(embeddingConfig.logger_config.configuration["logger"], TestEmbeddingConfiguration.test_dict["logger"])
        self.assertEqual(
            embeddingConfig.net_config.configuration["network"], TestEmbeddingConfiguration.test_dict["embeddings"]["network"]
        )
        TestEmbeddingConfiguration.test_dict["embeddings"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            embeddingConfig.runtime_config.configuration["runtime"],
            TestEmbeddingConfiguration.test_dict["embeddings"]["runtime"],
        )
        self.assertEqual(embeddingConfig.configuration["models"], TestEmbeddingConfiguration.test_dict["embeddings"]["models"])

    def test_clear(self):
        embeddingConfig = EmbeddingsConfiguration()
        embeddingConfig.loads(TestEmbeddingConfiguration.test_dict)
        embeddingConfig.clear()
        self.assertEqual(embeddingConfig.logger_config.logger_name, "default")
        self.assertEqual(embeddingConfig.logger_config.configuration, None)
        self.assertEqual(embeddingConfig.net_config.configuration, None)
        self.assertEqual(embeddingConfig.runtime_config.configuration, None)
        self.assertEqual(embeddingConfig.configuration, dict())
