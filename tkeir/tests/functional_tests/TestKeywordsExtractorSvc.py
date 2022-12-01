# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.keywordextractor_svc import main
import os, signal
import unittest
import time
import requests
import json

service_pid = 0
ssl_verify = False


class TestKeywordsExtractorSvc(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        global service_pid
        if service_pid == 0:
            service_pid = os.fork()
            if service_pid == 0:

                class args:
                    config = os.path.abspath(
                        os.path.join(
                            os.path.dirname(os.path.realpath(__file__)), "../../../app/projects/default/configs/keywords.json"
                        )
                    )

                print(args.config)
                main(args)
            else:
                load_finish = False
                count = 0
                while not load_finish:
                    try:
                        r = requests.get("https://localhost:10007/api/keywordsextractor/health", verify=ssl_verify)
                        load_finish = r.status_code == 200
                    except:
                        count = count + 1
                        if count > 10:
                            load_finish = True
                            break
                        time.sleep(1)

    @classmethod
    def tearDownClass(self):
        if service_pid:
            os.kill(service_pid, signal.SIGINT)

    def test_health(self):
        if service_pid:
            r = requests.get("https://localhost:10007/api/keywordsextractor/health", verify=ssl_verify)
            self.assertTrue(r.status_code == 200)

    def test_run(self):
        if service_pid:
            dir_path = os.path.dirname(os.path.realpath(__file__))
            test_file_path = os.path.abspath(os.path.join(dir_path, "../data/test-outputs-syntax"))
            with open(os.path.join(test_file_path, "mail3.txt.converted.tokenized.ms.ner.syntax.json")) as f:
                json_request = json.load(f)
                r = requests.post("https://localhost:10007/api/keywordsextractor/run", json=json_request, verify=ssl_verify)
                tkeir_doc = r.json()["results"]
                self.assertTrue(
                    tkeir_doc["keywords"]
                    == [
                        {"score": 4, "text": "lackawanna letter", "span": {"start": 0, "end": 2}},
                        {"score": 1, "text": "credit", "span": {"start": 3, "end": 4}},
                        {"score": 15, "text": "state amount be increase", "span": {"start": 25, "end": 29}},
                        {"score": 15, "text": "see approach regard completion", "span": {"start": 134, "end": 138}},
                        {"score": 12, "text": "completion date be define", "span": {"start": 44, "end": 48}},
                        {"score": 9, "text": "discussion last week", "span": {"start": 3, "end": 6}},
                        {"score": 8, "text": "certain quality specification", "span": {"start": 109, "end": 112}},
                        {"score": 7, "text": "subordinated loan agreement", "span": {"start": 68, "end": 71}},
                        {"score": 5, "text": "completion date", "span": {"start": 82, "end": 84}},
                        {"score": 5, "text": "definition be", "span": {"start": 59, "end": 61}},
                        {"score": 5, "text": "completion require", "span": {"start": 89, "end": 91}},
                        {"score": 4, "text": "loan agreement", "span": {"start": 179, "end": 181}},
                        {"score": 4, "text": "other thing", "span": {"start": 93, "end": 95}},
                        {"score": 4, "text": "independent engineer", "span": {"start": 122, "end": 124}},
                        {"score": 4, "text": "strategy go", "span": {"start": 147, "end": 149}},
                        {"score": 4, "text": "pertinent document", "span": {"start": 200, "end": 202}},
                        {"score": 3, "text": "lackawanna letter", "span": {"start": 13, "end": 15}},
                        {"score": 3, "text": "lc expire", "span": {"start": 166, "end": 168}},
                        {"score": 2, "text": "date", "span": {"start": 126, "end": 127}},
                        {"score": 2, "text": "specification", "span": {"start": 116, "end": 117}},
                        {"score": 2, "text": "agreement", "span": {"start": 163, "end": 164}},
                        {"score": 1, "text": "letter", "span": {"start": 192, "end": 193}},
                        {"score": 1, "text": "lc", "span": {"start": 50, "end": 51}},
                        {"score": 1, "text": "information", "span": {"start": 10, "end": 11}},
                        {"score": 1, "text": "credit", "span": {"start": 194, "end": 195}},
                        {"score": 1, "text": "receipt", "span": {"start": 33, "end": 34}},
                        {"score": 1, "text": "trustee", "span": {"start": 36, "end": 37}},
                        {"score": 1, "text": "notification", "span": {"start": 38, "end": 39}},
                        {"score": 1, "text": "indenture", "span": {"start": 54, "end": 55}},
                        {"score": 1, "text": "same", "span": {"start": 63, "end": 64}},
                        {"score": 1, "text": "analysis", "span": {"start": 76, "end": 77}},
                        {"score": 1, "text": "requirement", "span": {"start": 79, "end": 80}},
                        {"score": 1, "text": "production", "span": {"start": 97, "end": 98}},
                        {"score": 1, "text": "approval", "span": {"start": 113, "end": 114}},
                        {"score": 1, "text": "wait", "span": {"start": 132, "end": 133}},
                        {"score": 1, "text": "thought", "span": {"start": 145, "end": 146}},
                        {"score": 1, "text": "expiration", "span": {"start": 189, "end": 190}},
                        {"score": 1, "text": "office", "span": {"start": 208, "end": 209}},
                    ]
                )

            # test 500
            json_request = {"xxx": "email", "src": "file://" + os.path.join(test_file_path, "mail1.txt"), "data": "bad entry"}
            r = requests.post("https://localhost:10007/api/keywordsextractor/run", json=json_request, verify=ssl_verify)
            self.assertEqual(r.status_code, 500)
