# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.summarizer.SummarizerConfiguration import SummarizerConfiguration
from thot.tasks.summarizer.Summarizer import Summarizer
from thot.core.ThotLogger import ThotLogger, LogUserContext
import unittest
import json
import traceback
import os

dir_path = os.path.dirname(os.path.realpath(__file__))
test_file_path = os.path.abspath(os.path.join(dir_path, "../data/test-outputs-syntax"))


class TestSummarizer(unittest.TestCase):

    test_dict = {
        "logger": {"logging-level": "debug"},
        "summarizer": {
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

    def test_summarizer(self):
        try:
            with open("/tmp/cfg.json", "w") as f:
                json.dump(TestSummarizer.test_dict, f)
                f.close()
        except Exception as e:
            print(str(e) + " trace:" + str(traceback.format_exc()))
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        sumConfig = SummarizerConfiguration()
        sumConfig.load(fh)
        fh.close()
        with open(os.path.join(test_file_path, "mail3.txt.converted.tokenized.ms.ner.syntax.json")) as f:
            tkeir_doc = json.load(f)
            f.close()
            sum_res = Summarizer(config=sumConfig)
            cid = "autogenerated-" + str("xxx")
            log_context = LogUserContext(cid)
            tkeir_doc = sum_res.summarizationByTextBlocks(
                {"doc": tkeir_doc, "min-length": 5, "max-length": 20}, call_context=log_context
            )
            self.assertEqual(
                tkeir_doc["summaries"][0]["summary"],
                "Lackawanna Letter of Credit increased $ 4.5 million upon receipt of notification of",
            )
