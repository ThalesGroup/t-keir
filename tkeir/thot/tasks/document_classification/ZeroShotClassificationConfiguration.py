# -*- coding: utf-8 -*-
"""Zero shot classifier configuration

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import json

from thot.core.LoggerConfiguration import LoggerConfiguration
from thot.core.NetworkConfiguration import NetworkConfiguration
from thot.core.RuntimeConfiguration import RuntimeConfiguration


class ZeroShotClassificationConfiguration:
    """load zerochot classification configuration
    A ner configuration is represented by JSON entry:

    Example
    logger": {
            "logging-level": "debug"
             },
    "zeroshot-classification": {
        "classes":[
            {"label":"machine learning","content":{"machine learning","learning algorithm","modeling"},
            {"label":"neural network","content":{"neural network","hidden layers","loss function"},
            {"label":"image processing","content":{"convolutional neural network","fourier","cosine transform","image","picture","draw"},
            {"label":"natural language processing","content":{"natural language processing","named entities"}


        ]
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
            "keep-alive":True,
            "keep-alive-timeout":5,
            "graceful-shutown-timeout":15.0,
            "request-timeout":60,
            "response-timeout":60,
            "workers":1
        }
    }


    """

    def __init__(self):
        self.logger_config = LoggerConfiguration()
        self.net_config = NetworkConfiguration()
        self.runtime_config = RuntimeConfiguration()
        self.configuration = dict()

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
        self.logger_config.loads(configuration, logger_name="zeroshot-classification")
        self.net_config.loads(configuration["zeroshot-classification"])
        self.runtime_config.loads(configuration["zeroshot-classification"])
        if "classes" in configuration["zeroshot-classification"]:
            self.configuration["classes"] = configuration["zeroshot-classification"]["classes"]
        else:
            raise ValueError("classes are mandatory in zeroshot-classification configuration")
        if "settings" not in configuration["zeroshot-classification"]:
            self.configuration["settings"] = {"language": "en", "use-cuda": False, "cuda-device": 0}
        else:
            self.configuration["settings"] = configuration["zeroshot-classification"]["settings"]
        if "re-labelling-strategy" in configuration["zeroshot-classification"]:
            if configuration["zeroshot-classification"]["re-labelling-strategy"] not in ["mean", "max", "sum"]:
                raise ValueError("Classification re-labelling-strategy should be mean, max or sum")
            self.configuration["re-labelling-strategy"] = configuration["zeroshot-classification"]["re-labelling-strategy"]
        else:
            self.configuration["re-labelling-strategy"] = "sum"

    def clear(self):
        """clear logger configuration"""
        self.logger_config.clear()
        self.net_config.clear()
        self.runtime_config.clear()
        self.configuration = dict()
