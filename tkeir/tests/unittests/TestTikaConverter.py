# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.converters.TikaConverter import TikaConverter
from thot.tasks.converters.ConverterConfiguration import ConverterConfiguration
from thot.core.ThotLogger import ThotLogger, LogUserContext
import json
import os
import unittest


class TestTikaConverter(unittest.TestCase):
    def test_converter(self):
        test_dict = {
            "logger": {"logging-level": "debug"},
            "converter": {
                "network": {
                    "host": "0.0.0.0",
                    "port": 8080,
                    "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"},
                },
                "settings": {
                    "tika": {
                        "host": "localhost",
                        "port": 9998,
                        "associate-environment": {"host": "TIKA_HOST", "port": "TIKA_PORT"},
                    },
                    "output": {"zip": True},
                },
                "serialize": {
                    "input": {"path": "/tmp", "keep-service-info": True},
                    "output": {"path": "/tmp", "keep-service-info": True},
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
                    "associate-environment": {
                        "request-max-size": "ENV1",
                        "request-buffer-queue-size": "ENV2",
                        "keep-alive": "ENV3",
                        "keep-alive-timeout": "ENV4",
                        "graceful-shutown-timeout": "ENV5",
                        "request-timout": "ENV6",
                        "response-timeout": "ENV7",
                        "workers": "ENV8",
                    },
                },
            },
        }
        dir_path = os.path.dirname(os.path.realpath(__file__))
        data_path = os.path.abspath(os.path.join(dir_path, "../data/"))
        converterConfig = ConverterConfiguration()
        converterConfig.loads(test_dict)
        for doc in ["converter_test.docx", "converter_test.odt", "converter_test.pdf", "converter_test.rtf"]:
            with open(os.path.join(data_path, doc), "rb") as f:
                data = f.read()
                f.close()
                log_context = LogUserContext("my-cor-id:" + doc)
                ThotLogger.loads({"logging-level": "info"}, logger_name="** My test Logger **")
                document = TikaConverter.convert(data, "file://" + doc, converterConfig, call_context=log_context)
                self.assertTrue(len(document["content"]) and ("This is a raw test" in document["content"][0]))
