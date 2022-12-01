# -*- coding: utf-8 -*-
"""Test converter
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from tkeir.thot.tasks.relations.RelationClusterizerConfiguration import RelationClusterizerConfiguration
from thot.tasks.relations.ClusterInference import ClusteringInference
import os
import unittest
import base64
import json

dir_path = os.path.dirname(os.path.realpath(__file__))
test_file_path = os.path.abspath(os.path.join(dir_path, "../data/test-outputs-kw"))


class TestClusterInference(unittest.TestCase):

    test_config = {
        "logger": {"logging-level": "debug"},
        "relations": {
            "cluster": {
                "algorithm": "kmeans",
                "number-of-classes": 128,
                "number-of-iterations": 16,
                "seed": 123456,
                "batch-size": 4096,
                "embeddings": {
                    "server": {
                        "host": "0.0.0.0",
                        "port": 10006,
                        "associate-environment": {"host": "SENT_EMBEDDING_HOST", "port": "SENT_EMBEDDING_PORT"},
                        "use-ssl": True,
                        "no-verify-ssl": True,
                    },
                    "aggregate": {"configuration": "/home/tkeir_svc/tkeir/app/projects/default/configs/embeddings.json"},
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
            "clustering-model": {
                "semantic-quantizer-model": "/home/tkeir_svc/tkeir/app/projects/default/resources/modeling/relation_names.model.pkl"
            },
            "serialize": {
                "input": {"path": "/tmp", "keep-service-info": True},
                "output": {"path": "/tmp", "keep-service-info": True},
            },
        },
    }

    def __test_clusterinference(self):
        with open(os.path.join(test_file_path, "mail3.txt.converted.tokenized.ms.ner.syntax.kw.json")) as f:
            tkeir_doc = json.load(f)
            f.close()
            cfg = RelationClusterizerConfiguration()
            cfg.loads(TestClusterInference.test_config)
            ci = ClusteringInference(config=cfg)
            tkeir_doc = ci.infer(tkeir_doc)
            has_class = False
            for k in tkeir_doc["kg"]:
                if "class" in k["subject"]:
                    if k["subject"]["class"] != -1:
                        has_class = True
            self.assertTrue(has_class)

    def test_clusterinference_agg(self):
        with open(os.path.join(test_file_path, "mail3.txt.converted.tokenized.ms.ner.syntax.kw.json")) as f:
            tkeir_doc = json.load(f)
            f.close()
            cfg = RelationClusterizerConfiguration()
            cfg.loads(TestClusterInference.test_config)
            ci = ClusteringInference(config=cfg, embeddings_server=False)
            tkeir_doc = ci.infer(tkeir_doc)
            has_class = False
            for k in tkeir_doc["kg"]:
                if "class" in k["subject"]:
                    if k["subject"]["class"] != -1:
                        has_class = True
            self.assertTrue(has_class)
