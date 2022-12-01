# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.qa_svc import main
import os, signal
import unittest
import time
import requests
import json


service_pid = 0
ssl_verify = False


class TestQASvc(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        global service_pid
        if service_pid == 0:
            service_pid = os.fork()
            if service_pid == 0:

                class args:
                    config = os.path.abspath(
                        os.path.join(
                            os.path.dirname(os.path.realpath(__file__)), "../../../app/projects/default/configs/qa.json"
                        )
                    )
                    init = False

                print(args.config)
                main(args)
            else:
                load_finish = False
                count = 0
                while not load_finish:
                    try:
                        r = requests.get("https://localhost:10011/api/qa/health", verify=ssl_verify)
                        load_finish = r.status_code == 200
                    except:
                        count = count + 1
                        if count > 30:
                            load_finish = True
                            break
                        time.sleep(1)

    @classmethod
    def tearDownClass(self):
        if service_pid:
            os.kill(service_pid, signal.SIGINT)

    def test_health(self):
        if service_pid:
            r = requests.get("https://localhost:10011/api/qa/health", verify=ssl_verify)
            self.assertTrue(r.status_code == 200)

    def test_run(self):
        if service_pid:
            dir_path = os.path.dirname(os.path.realpath(__file__))
            test_file_path = os.path.abspath(os.path.join(dir_path, "../data/test-outputs-syntax"))
            with open(os.path.join(test_file_path, "mail3.txt.converted.tokenized.ms.ner.syntax.json")) as f:
                json_request = json.load(f)

            r = requests.post(
                "https://localhost:10011/api/qa/run",
                json={"doc": json_request, "query": "When does expire the LC?"},
                verify=ssl_verify,
            )
            tkeir_doc = r.json()["results"]

            self.assertEqual(tkeir_doc["qa"][0]["doc"]["answer"], "June 30")

            # test 500
            json_request = {"xxx": "email", "src": "file://" + os.path.join(test_file_path, "mail1.txt"), "data": "bad entry"}
            r = requests.post("https://localhost:10011/api/qa/run", json=json_request, verify=ssl_verify)
            self.assertEqual(r.status_code, 500)
