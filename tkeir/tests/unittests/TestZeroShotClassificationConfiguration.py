# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.document_classification.ZeroShotClassificationConfiguration import ZeroShotClassificationConfiguration
import unittest
import json
import traceback


class TestZeroShotClassificationConfiguration(unittest.TestCase):

    test_dict = {
        "logger": {"logging-level": "debug"},
        "zeroshot-classification": {
            "classes": [
                {"label": "machine learning", "content": ["machine learning", "learning algorithm", "modeling"]},
                {"label": "neural network", "content": ["neural network", "hidden layers", "loss function"]},
                {
                    "label": "image processing",
                    "content": ["convolutional neural network", "fourier", "cosine transform", "image", "picture", "draw"],
                },
                {"label": "natural language processing", "content": ["natural language processing", "named entities"]},
            ],
            "re-labelling-strategy": "mean",
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
                json.dump(TestZeroShotClassificationConfiguration.test_dict, f)
                f.close()
        except Exception as e:
            print(str(e) + " trace:" + str(traceback.format_exc()))
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        zscConfig = ZeroShotClassificationConfiguration()
        zscConfig.load(fh)
        fh.close()

        self.assertEqual(
            zscConfig.logger_config.configuration["logger"], TestZeroShotClassificationConfiguration.test_dict["logger"]
        )
        self.assertEqual(
            zscConfig.net_config.configuration["network"],
            TestZeroShotClassificationConfiguration.test_dict["zeroshot-classification"]["network"],
        )
        TestZeroShotClassificationConfiguration.test_dict["zeroshot-classification"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            zscConfig.runtime_config.configuration["runtime"],
            TestZeroShotClassificationConfiguration.test_dict["zeroshot-classification"]["runtime"],
        )
        self.assertEqual(
            zscConfig.configuration["classes"],
            TestZeroShotClassificationConfiguration.test_dict["zeroshot-classification"]["classes"],
        )
        self.assertEqual(
            zscConfig.configuration["re-labelling-strategy"],
            TestZeroShotClassificationConfiguration.test_dict["zeroshot-classification"]["re-labelling-strategy"],
        )

    def test_loads(self):
        zscConfig = ZeroShotClassificationConfiguration()
        zscConfig.loads(TestZeroShotClassificationConfiguration.test_dict)
        self.assertEqual(
            zscConfig.logger_config.configuration["logger"], TestZeroShotClassificationConfiguration.test_dict["logger"]
        )
        self.assertEqual(
            zscConfig.net_config.configuration["network"],
            TestZeroShotClassificationConfiguration.test_dict["zeroshot-classification"]["network"],
        )
        TestZeroShotClassificationConfiguration.test_dict["zeroshot-classification"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            zscConfig.runtime_config.configuration["runtime"],
            TestZeroShotClassificationConfiguration.test_dict["zeroshot-classification"]["runtime"],
        )
        self.assertEqual(
            zscConfig.configuration["classes"],
            TestZeroShotClassificationConfiguration.test_dict["zeroshot-classification"]["classes"],
        )
        self.assertEqual(
            zscConfig.configuration["re-labelling-strategy"],
            TestZeroShotClassificationConfiguration.test_dict["zeroshot-classification"]["re-labelling-strategy"],
        )

    def test_clear(self):
        zscConfig = ZeroShotClassificationConfiguration()
        zscConfig.loads(TestZeroShotClassificationConfiguration.test_dict)
        zscConfig.clear()
        self.assertEqual(zscConfig.logger_config.logger_name, "default")
        self.assertEqual(zscConfig.logger_config.configuration, None)
        self.assertEqual(zscConfig.net_config.configuration, None)
        self.assertEqual(zscConfig.runtime_config.configuration, None)
        self.assertEqual(zscConfig.configuration, dict())
