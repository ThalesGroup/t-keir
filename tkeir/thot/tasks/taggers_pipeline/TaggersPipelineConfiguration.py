# -*- coding: utf-8 -*-
"""Tagger pipeline configuration
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import json
import os
from tkeir.thot.core.ThotLogger import ThotLogger

from thot.core.Utils import mkdir_p
from thot.core.LoggerConfiguration import LoggerConfiguration
from thot.core.NetworkConfiguration import NetworkConfiguration
from thot.core.RuntimeConfiguration import RuntimeConfiguration


class TaggersPipelineConfiguration:
    """load morphosyntactic tagger configuration
    A tagger configuration is represented by JSON entry:

    Example
    {
         "logger": {
                            "logging-level": 'debug'
                        },
        "pipeline": {
            "settings":{
                "max-time-loop":-1,
                "max-time-per-task":6,
                "zip-results":true
            }
            "tasks":[{
                        "use-as-a-service":false,
                        "task":"converter",
                        "resources-base-path":"/home/tkeir_svc/tkeir/configs/tests/configs/",
                        "configuration": "converter.json",
                        "output-dir":"/home/tkeir_svc/tkeir/thot/tests/data/test-inputs"
                    },
                    {
                        "use-as-a-service":false,
                        "task":"tokenizer",
                        "resources-base-path":"/home/tkeir_svc/tkeir/configs/tests/configs/",
                        "configuration": "tokenizer.json",
                        "input-dir":"/home/tkeir_svc/tkeir/thot/tests/data/test-inputs",
                        "output-dir":"/home/tkeir_svc/tkeir/thot/tests/data/test-outputs-tokenizer"
                    },
                    {
                        "use-as-a-service":false,
                        "task":"morphosyntax",
                        "resources-base-path":"/home/tkeir_svc/tkeir/configs/tests/configs/",
                        "configuration": "mstagger.json",
                        "input-dir":"/home/tkeir_svc/tkeir/thot/tests/data/test-outputs-tokenizer",
                        "output-dir":"/home/tkeir_svc/tkeir/thot/tests/data/test-outputs-ms"
                    },
                    {
                        "use-as-a-service":false,
                        "task":"ner",
                        "resources-base-path":"/home/tkeir_svc/tkeir/configs/tests/configs/",
                        "configuration": "ner.json",
                        "input-dir":"/home/tkeir_svc/tkeir/thot/tests/data/test-outputs-ms",
                        "output-dir":"/home/tkeir_svc/tkeir/thot/tests/data/test-outputs-ner"
                    },
                    {
                        "use-as-a-service":false,
                        "task":"syntax",
                        "resources-base-path":"/home/tkeir_svc/tkeir/configs/tests/configs/",
                        "input-dir":"/home/tkeir_svc/tkeir/thot/tests/data/test-outputs-ner",
                        "output-dir":"/home/tkeir_svc/tkeir/thot/tests/data/test-outputs-syntax",
                        "configuration": "syntax.json"
                    }
                    ],
            "network": {
                "host":"0.0.0.0",
                "port":8080,
                "associate-environment": {
                    "host":"HOST_ENVNAME",
                    "port":"PORT_ENVNAME"
                }
            },
            "runtime":{
                "request-max-size":100000000,
                "request-buffer-queue-size":100,
                "keep-alive":true,
                "keep-alive-timeout":5,
                "graceful-shutown-timeout":15.0,
                "request-timeout":60,
                "response-timeout":60,
                "workers":1
            },
            "serialize":{
                "input":{
                    "path":"/tmp",
                    "keep-service-info":true
                },
                "output":{
                    "path":"/tmp",
                    "keep-service-info":true
                }
            }

        }
    }
    """

    def __init__(self):
        self.logger_config = LoggerConfiguration()
        self.net_config = NetworkConfiguration()
        self.runtime_config = RuntimeConfiguration()
        # Fill on tokenizer empty
        self.configuration = dict()

    def _check_tasks_configuration(self):
        for task in self.configuration["tasks"]:
            if "task" not in task:
                ThotLogger.error("task field is mandatory.")
                raise ValueError("task field is mandatory.")
            if "resources-base-path" not in task:
                ThotLogger.error("resources-base-path field is mandatory.")
                raise ValueError("resources-base-path field is mandatory.")
            if "input-dir" not in task:
                ThotLogger.error("input-dir field is mandatory.")
                raise ValueError("input-dir field is mandatory.")
            if "previous-task" not in task:
                ThotLogger.error("previous-task field is mandatory.")
                raise ValueError("previous-task field is mandatory.")
            if "output-dir" not in task:
                ThotLogger.error("output-dir field is mandatory.")
                raise ValueError("output-dir field is mandatory.")
            if "configuration" not in task:
                ThotLogger.error("configuration field is mandatory.")
                raise ValueError("configuration field is mandatory.")
            if task["task"] not in [
                "converter",
                "tokenizer",
                "morphosyntax",
                "ner",
                "syntax",
                "keywords",
                "zeroshotclassifier",
                "clusterinfer",
                "sentiment",
                "summarizer",
                "relation-clustering",
                "index",
            ]:
                ThotLogger.error(str(task["task"]) + " is not a valid task")
                raise ValueError(str(task["task"]) + " is not a valid task")
            if not os.path.isfile(os.path.join(task["resources-base-path"], task["configuration"])):
                ThotLogger.error("configuration file '" + str(task["configuration"]) + "' does not exists")
                raise ValueError("configuration file '" + str(task["configuration"]) + "' does not exists.")
            if "clean-input-folder-after-analysis" not in task:
                task["clean-input-folder-after-analysis"] = False
            if "save-output" not in task:
                task["save-output"] = False
            mkdir_p(task["input-dir"])
            mkdir_p(task["output-dir"])

    def load(self, config_f=None, path: list = []):
        """Load logger configuration from file

        Args:
            config_f (str, optional): load configruation with file handler. Defaults to None.
            path (list,option): access to a part of the configuration
        """
        json_config = json.load(config_f)
        self.loads(json_config)

    def loads(self, configuration: dict = None):
        """Load logger configuration from dict (json)

        Args:
            configuration (dict, optional): load logger configruation with dict. Defaults to None.
        """
        self.logger_config.loads(configuration, logger_name="tagger-pipeline")
        self.net_config.loads(configuration["pipeline"])
        self.runtime_config.loads(configuration["pipeline"])
        if "tasks" in configuration["pipeline"]:
            self.configuration["tasks"] = configuration["pipeline"]["tasks"]
        else:
            raise ValueError("Tasks should be defines")
        if "settings" in configuration["pipeline"]:
            self.configuration["settings"] = configuration["pipeline"]["settings"]
            if "max-time-loop" not in self.configuration["settings"]:
                self.configuration["settings"]["max-time-loop"] = -1
            if "max-time-per-task" not in self.configuration["settings"]:
                self.configuration["settings"]["max-time-per-task"] = -1
            if "zip-results" not in self.configuration["settings"]:
                self.configuration["settings"]["zip-results"] = False
        else:
            self.configuration["settings"] = {"max-time-loop": -1, "max-time-per-task": -1, "zip-results": False}
        self._check_tasks_configuration()

    def clear(self):
        """clear logger configuration"""
        self.logger_config.clear()
        self.net_config.clear()
        self.runtime_config.clear()
        self.configuration = dict()
