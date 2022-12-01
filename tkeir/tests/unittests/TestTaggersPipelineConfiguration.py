# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.taggers_pipeline.TaggersPipelineConfiguration import TaggersPipelineConfiguration
import unittest
import json


class TestTaggersPipelineConfiguration(unittest.TestCase):

    test_dict = {
        "logger": {"logging-level": "debug"},
        "pipeline": {
            "tasks": [
                {
                    "task": "converter",
                    "save-output": False,
                    "previous-task": "input",
                    "clean-input-folder-after-analysis": False,
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/default/configs/",
                    "configuration": "converter.json",
                    "input-dir": "/home/tkeir_svc/tkeir/var/datasets/test-raw",
                    "output-dir": "/home/tkeir_svc/tkeir/var/datasets/test-inputs",
                },
                {
                    "task": "tokenizer",
                    "save-output": False,
                    "previous-task": "converter",
                    "clean-input-folder-after-analysis": True,
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/default/configs/",
                    "configuration": "tokenizer.json",
                    "input-dir": "/home/tkeir_svc/tkeir/var/datasets/test-inputs",
                    "output-dir": "/home/tkeir_svc/tkeir/var/datasets/test-outputs-tokenizer",
                },
                {
                    "task": "morphosyntax",
                    "save-output": False,
                    "previous-task": "tokenizer",
                    "clean-input-folder-after-analysis": True,
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/default/configs/",
                    "configuration": "mstagger.json",
                    "input-dir": "/home/tkeir_svc/tkeir/var/datasets/test-outputs-tokenizer",
                    "output-dir": "/home/tkeir_svc/tkeir/var/datasets/test-outputs-ms",
                },
                {
                    "task": "ner",
                    "save-output": False,
                    "previous-task": "morphosyntax",
                    "clean-input-folder-after-analysis": True,
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/default/configs/",
                    "configuration": "nertagger.json",
                    "input-dir": "/home/tkeir_svc/tkeir/var/datasets/test-outputs-ms",
                    "output-dir": "/home/tkeir_svc/tkeir/var/datasets/test-outputs-ner",
                },
                {
                    "task": "syntax",
                    "save-output": False,
                    "previous-task": "ner",
                    "clean-input-folder-after-analysis": True,
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/default/configs/",
                    "input-dir": "/home/tkeir_svc/tkeir/var/datasets/test-outputs-ner",
                    "output-dir": "/home/tkeir_svc/tkeir/var/datasets/test-outputs-syntax",
                    "configuration": "syntactic-tagger.json",
                },
                {
                    "task": "keywords",
                    "save-output": False,
                    "previous-task": "syntax",
                    "clean-input-folder-after-analysis": True,
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/default/configs/",
                    "input-dir": "/home/tkeir_svc/tkeir/var/datasets/test-outputs-syntax",
                    "output-dir": "/home/tkeir_svc/tkeir/var/datasets/test-outputs-kw",
                    "configuration": "keywords.json",
                },
            ],
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
        },
    }

    def test_load(self):
        try:
            with open("/tmp/cfg.json", "w") as f:
                json.dump(TestTaggersPipelineConfiguration.test_dict, f)
                f.close()
        except Exception as e:
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        pipelineConfig = TaggersPipelineConfiguration()
        pipelineConfig.load(fh)
        fh.close()

        self.assertEqual(
            pipelineConfig.logger_config.configuration["logger"], TestTaggersPipelineConfiguration.test_dict["logger"]
        )
        self.assertEqual(
            pipelineConfig.net_config.configuration["network"],
            TestTaggersPipelineConfiguration.test_dict["pipeline"]["network"],
        )
        self.assertEqual(
            pipelineConfig.runtime_config.configuration["runtime"],
            TestTaggersPipelineConfiguration.test_dict["pipeline"]["runtime"],
        )
        self.assertEqual(pipelineConfig.configuration["tasks"], TestTaggersPipelineConfiguration.test_dict["pipeline"]["tasks"])

    def test_loads(self):
        pipelineConfig = TaggersPipelineConfiguration()
        pipelineConfig.loads(TestTaggersPipelineConfiguration.test_dict)
        self.assertEqual(
            pipelineConfig.logger_config.configuration["logger"], TestTaggersPipelineConfiguration.test_dict["logger"]
        )
        self.assertEqual(
            pipelineConfig.net_config.configuration["network"],
            TestTaggersPipelineConfiguration.test_dict["pipeline"]["network"],
        )
        self.assertEqual(
            pipelineConfig.runtime_config.configuration["runtime"],
            TestTaggersPipelineConfiguration.test_dict["pipeline"]["runtime"],
        )
        self.assertEqual(pipelineConfig.configuration["tasks"], TestTaggersPipelineConfiguration.test_dict["pipeline"]["tasks"])

    def test_clear(self):
        pipelineConfig = TaggersPipelineConfiguration()
        pipelineConfig.loads(TestTaggersPipelineConfiguration.test_dict)
        pipelineConfig.clear()
        self.assertEqual(pipelineConfig.logger_config.logger_name, "default")
        self.assertEqual(pipelineConfig.logger_config.configuration, None)
        self.assertEqual(pipelineConfig.net_config.configuration, None)
        self.assertEqual(pipelineConfig.runtime_config.configuration, None)
        self.assertEqual(pipelineConfig.configuration, dict())
