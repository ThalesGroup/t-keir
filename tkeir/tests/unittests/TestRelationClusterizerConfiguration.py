# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.relations.RelationClusterizerConfiguration import RelationClusterizerConfiguration
import unittest
import json


class TestRelationClusterizerConfiguration(unittest.TestCase):

    test_dict = {
        "logger": {"logging-level": "debug"},
        "relations": {
            "cluster": {
                "number-of-classes": 100,
                "number-of-iterations": 100,
                "batch-size": 1024,
                "seed": 123456,
                "embeddings": {
                    "server": {
                        "host": "0.0.0.0",
                        "port": 10006,
                        "associate-environment": {"host": "SENT_EMBEDDING_HOST", "port": "SENT_EMBEDDING_PORT"},
                        "use-ssl": True,
                        "no-verify-ssl": True,
                    }
                },
            },
            "network": {
                "host": "0.0.0.0",
                "port": 10013,
                "associate-environment": {"host": "CLUSTER_INFERENCE_HOST", "port": "CLUSTER_INFERENCE_PORT"},
                "ssl": {
                    "cert": "/home/tkeir_svc/tkeir/app/ssl/certificate.crt",
                    "key": "/home/tkeir_svc/tkeir/app/ssl/privateKey.key",
                },
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
                json.dump(TestRelationClusterizerConfiguration.test_dict, f)
                f.close()
        except Exception as e:
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        relationsConfig = RelationClusterizerConfiguration()
        relationsConfig.load(fh)
        fh.close()

        self.assertEqual(
            relationsConfig.logger_config.configuration["logger"], TestRelationClusterizerConfiguration.test_dict["logger"]
        )
        TestRelationClusterizerConfiguration.test_dict["relations"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            relationsConfig.configuration["cluster"], TestRelationClusterizerConfiguration.test_dict["relations"]["cluster"]
        )

    def test_loads(self):
        relationsConfig = RelationClusterizerConfiguration()
        relationsConfig.loads(TestRelationClusterizerConfiguration.test_dict)
        self.assertEqual(
            relationsConfig.logger_config.configuration["logger"], TestRelationClusterizerConfiguration.test_dict["logger"]
        )
        TestRelationClusterizerConfiguration.test_dict["relations"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            relationsConfig.configuration["cluster"], TestRelationClusterizerConfiguration.test_dict["relations"]["cluster"]
        )

    def test_clear(self):
        relationsConfig = RelationClusterizerConfiguration()
        relationsConfig.loads(TestRelationClusterizerConfiguration.test_dict)
        relationsConfig.clear()
        self.assertEqual(relationsConfig.logger_config.logger_name, "default")
        self.assertEqual(relationsConfig.logger_config.configuration, None)
        self.assertEqual(relationsConfig.configuration, dict())
