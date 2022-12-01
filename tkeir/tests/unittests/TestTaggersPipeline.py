# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.core.ThotLogger import ThotLogger, LogUserContext
from thot.tasks.taggers_pipeline.TaggersPipelineConfiguration import TaggersPipelineConfiguration
from thot.tasks.taggers_pipeline.TaggersPipeline import TaggersPipeline, pipelineLoop
import unittest
import os
import base64
import json
import threading
import time


class TestTaggersPipeline(unittest.TestCase):

    test_dict = {
        "logger": {"logging-level": "debug"},
        "pipeline": {
            "settings": {"max-time-loop": -1, "max-time-per-task": 1, "zip-results": True},
            "tasks": [
                {
                    "task": "converter",
                    "previous-task": "input",
                    "save-output": False,
                    "clean-input-folder-after-analysis": True,
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/test/configs/",
                    "configuration": "converter.json",
                    "input-dir": "/home/tkeir_svc/tkeir/var/datasets/raw-inputs",
                    "output-dir": "/home/tkeir_svc/tkeir/var/datasets/test-inputs",
                },
                {
                    "task": "tokenizer",
                    "previous-task": "converter",
                    "save-output": False,
                    "clean-input-folder-after-analysis": True,
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/test/configs/",
                    "configuration": "tokenizer.json",
                    "input-dir": "/home/tkeir_svc/tkeir/var/datasets/raw-inputs",
                    "output-dir": "/home/tkeir_svc/tkeir/var/datasets/test-outputs-tokenizer",
                },
                {
                    "previous-task": "tokenizer",
                    "save-output": False,
                    "task": "morphosyntax",
                    "clean-input-folder-after-analysis": True,
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/test/configs/",
                    "configuration": "mstagger.json",
                    "input-dir": "/home/tkeir_svc/tkeir/var/datasets/raw-inputs",
                    "output-dir": "/home/tkeir_svc/tkeir/var/datasets/test-outputs-ms",
                },
                {
                    "task": "ner",
                    "previous-task": "morphosyntax",
                    "save-output": False,
                    "clean-input-folder-after-analysis": True,
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/test/configs/",
                    "configuration": "nertagger.json",
                    "input-dir": "/home/tkeir_svc/tkeir/var/datasets/raw-inputs",
                    "output-dir": "/home/tkeir_svc/tkeir/var/datasets/test-outputs-ner",
                },
                {
                    "task": "syntax",
                    "previous-task": "ner",
                    "save-output": False,
                    "clean-input-folder-after-analysis": True,
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/test/configs/",
                    "input-dir": "/home/tkeir_svc/tkeir/var/datasets/raw-inputs",
                    "output-dir": "/home/tkeir_svc/tkeir/var/datasets/test-outputs-syntax",
                    "configuration": "syntactic-tagger.json",
                },
                {
                    "task": "keywords",
                    "previous-task": "syntax",
                    "save-output": True,
                    "clean-input-folder-after-analysis": True,
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/test/configs/",
                    "input-dir": "/home/tkeir_svc/tkeir/var/datasets/raw-inputs",
                    "output-dir": "/home/tkeir_svc/tkeir/var/datasets/test-outputs-kw",
                    "configuration": "keywords.json",
                },
            ],
            "network": {
                "host": "0.0.0.0",
                "port": 10006,
                "associate-environment": {"host": "PIPELINE_HOST", "port": "PIPELINE_PORT"},
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

    def test_init(self):
        try:
            with open("/tmp/cfg.json", "w") as f:
                json.dump(TestTaggersPipeline.test_dict, f)
                f.close()
        except Exception as e:
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        pipelineConfig = TaggersPipelineConfiguration()
        pipelineConfig.load(fh)
        fh.close()
        pipeline = TaggersPipeline(config=pipelineConfig)
        self.assertEqual(len(pipeline.tasks), 6)
        pipeline.stopPipeline = True
        pipelineLoop(pipeline)

    def test_run(self):
        cid = "autogenerated-" + str("xxx")
        log_context = LogUserContext(cid)
        try:
            with open("/tmp/cfg.json", "w") as f:
                TestTaggersPipeline.test_dict["pipeline"]["settings"]["max-time-loop"] = 30
                json.dump(TestTaggersPipeline.test_dict, f)
                f.close()
        except Exception as e:
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        pipelineConfig = TaggersPipelineConfiguration()
        pipelineConfig.load(fh)
        fh.close()
        dir_path = os.path.dirname(os.path.realpath(__file__))
        data_path = os.path.abspath(os.path.join(dir_path, "../data/test-raw/mail"))
        pipeline = TaggersPipeline(config=pipelineConfig)
        processThread = threading.Thread(target=pipelineLoop, args=(pipeline, log_context))  # <- note extra ','
        processThread.start()
        tokenids = []
        pipeline.start_upload()
        files = [os.path.join(data_path, filename) for filename in os.listdir(data_path)]
        for mail in files:
            with open(mail, "rb") as f:
                data = base64.b64encode(f.read())
                tokenids.append(
                    pipeline.upload(data_type="email", data=data.decode(), source="file://" + mail, call_context=log_context)
                )
                f.close()
        pipeline.finish_upload()
        st_time = time.time()
        et_time = time.time() - st_time
        tkeir_doc = None
        while et_time < 60:
            for tokenid in tokenids:
                s = pipeline.status(tokenid=tokenid)
                if "is-last-task" in s:
                    tkeir_doc = pipeline.get(tokenid=tokenid)
            et_time = time.time() - st_time
            time.sleep(1)
        processThread.join()
        self.assertTrue(tkeir_doc != None)
