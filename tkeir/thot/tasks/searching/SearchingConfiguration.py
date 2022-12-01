# -*- coding: utf-8 -*-
"""Searching configuration
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import json

from thot.core.CommonConfiguration import CommonConfiguration
from thot.core.LoggerConfiguration import LoggerConfiguration
from thot.core.NetworkConfiguration import NetworkConfiguration
from thot.core.RuntimeConfiguration import RuntimeConfiguration
from thot.tasks.tokenizer.TokenizerConfiguration import TokenizerConfiguration
from thot.tasks.morphosyntax.MorphoSyntacticTaggerConfiguration import MorphoSyntacticTaggerConfiguration
from thot.tasks.ner.NERTaggerConfiguration import NERTaggerConfiguration
from thot.tasks.syntax.SyntacticTaggerConfiguration import SyntacticTaggerConfiguration
from thot.tasks.embeddings.EmbeddingsConfiguration import EmbeddingsConfiguration
from thot.tasks.keywords.KeywordsConfiguration import KeywordsConfiguration


class SearchingConfiguration:
    """load searching configuration
    A searching configuration is represented by JSON entry:

    Example
    logger": {
            "logging-level": "debug"
             },
    "searching": {
        "elasticsearch":{
                "network": {
                    "host": "localhost",
                    "port": 9200,
                    "use_ssl": False,
                    "verify_certs": False,
                    "associate-environment": {
                        "host":"HOST_ENVNAME",
                        "port":"PORT_ENVNAME"
                    }
                }
        },
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
        self.tokenizerConfig = TokenizerConfiguration()
        self.msConfig = MorphoSyntacticTaggerConfiguration()
        self.nerConfig = NERTaggerConfiguration()
        self.embeddingsConfig = EmbeddingsConfiguration()
        self.syntaxConfig = SyntacticTaggerConfiguration()
        self.kwConfig = KeywordsConfiguration()

        self.net_config = NetworkConfiguration()
        self.runtime_config = RuntimeConfiguration()
        # Fill on named entity empty
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
        self.logger_config.loads(configuration, logger_name="searching")
        self.net_config.loads(configuration["searching"])
        self.runtime_config.loads(configuration["searching"])
        self.tokenizerConfig.loads(configuration)
        self.msConfig.loads(configuration)
        self.nerConfig.loads(configuration)
        self.syntaxConfig.loads(configuration)
        self.embeddingsConfig.loads(configuration)
        self.kwConfig.loads(configuration)
        if "elasticsearch" in configuration["searching"]:
            self.configuration["elasticsearch"] = configuration["searching"]["elasticsearch"]
            CommonConfiguration.affect_associated_environment(self.configuration["elasticsearch"]["network"])
            if "auth" in self.configuration["elasticsearch"]["network"]:
                CommonConfiguration.affect_associated_environment(self.configuration["elasticsearch"]["network"]["auth"])
        else:
            raise ValueError("elasticsearch is mandatory in searching configuration")

        if "aggregator" in configuration["searching"]:
            self.configuration["aggregator"] = configuration["searching"]["aggregator"]
            if "index-pipeline" in self.configuration["aggregator"]:
                CommonConfiguration.affect_associated_environment(self.configuration["aggregator"]["index-pipeline"])
        if "qa" in configuration["searching"]:
            self.configuration["qa"] = configuration["searching"]["qa"]
            CommonConfiguration.affect_associated_environment(self.configuration["qa"])

        if "suggester" in configuration["searching"]:
            self.configuration["suggester"] = configuration["searching"]["suggester"]
        else:
            self.configuration["suggester"] = {"number-of-suggestions": 10, "spell-check": True}

        if "document-index-name" in configuration["searching"]:
            self.configuration["document-index-name"] = configuration["searching"]["document-index-name"]
        if "disable-document-analysis" in configuration["searching"]:
            self.configuration["disable-document-analysis"] = configuration["searching"]["disable-document-analysis"]
        if "search-policy" in configuration["searching"]:
            self.configuration["search-policy"] = configuration["searching"]["search-policy"]

        if "scoring" not in self.configuration["search-policy"]["settings"]:
            self.configuration["search-policy"]["settings"]["scoring"] = {
                "normalize-score": False,
                "document-query-intersection-penalty": "no-normalization",
                "run-clause-separately": False,
                "expand-results": 0,
            }

    def clear(self):
        """clear logger configuration"""
        self.logger_config.clear()
        self.net_config.clear()
        self.runtime_config.clear()
        self.tokenizerConfig.clear()
        self.msConfig.clear()
        self.nerConfig.clear()
        self.syntaxConfig.clear()
        self.embeddingsConfig.clear()
        self.kwConfig.clear()
        self.configuration = dict()
