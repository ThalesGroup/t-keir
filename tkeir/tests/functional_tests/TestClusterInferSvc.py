# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.clusterinfer_svc import main
import os, signal
import unittest
import time
import requests
import json

service_pid = 0
ssl_verify = False


class TestClusterInferSvc(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        global service_pid
        if service_pid == 0:
            service_pid = os.fork()
            if service_pid == 0:

                class args:
                    config = os.path.abspath(
                        os.path.join(
                            os.path.dirname(os.path.realpath(__file__)),
                            "../../../app/projects/default/configs/relations-ssl.json",
                        )
                    )

                print(args.config)
                main(args)
            else:
                load_finish = False
                count = 0
                while not load_finish:
                    try:
                        r = requests.get("https://localhost:10013/api/clusterinfer/health", verify=ssl_verify)
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
            r = requests.get("https://localhost:10013/api/clusterinfer/health", verify=ssl_verify)
            self.assertTrue(r.status_code == 200)

    def test_run(self):
        if service_pid:
            dir_path = os.path.dirname(os.path.realpath(__file__))
            test_file_path = os.path.abspath(os.path.join(dir_path, "../data/test-outputs-kw"))
            with open(os.path.join(test_file_path, "mail3.txt.converted.tokenized.ms.ner.syntax.kw.json")) as f:
                json_request = json.load(f)
                r = requests.post("https://localhost:10013/api/clusterinfer/run", json=json_request, verify=ssl_verify)
                tkeir_doc = r.json()["results"]
                has_class = False
                for kg_item in tkeir_doc["kg"]:
                    if ("class" in kg_item["subject"]) and (kg_item["subject"]["class"] != -1):
                        has_class = True
                self.assertTrue(has_class)

            # test 500
            json_request = {"xxx": "email", "src": "file://" + os.path.join(test_file_path, "mail1.txt"), "data": "bad entry"}
            r = requests.post("https://localhost:10013/api/clusterinfer/run", json=json_request, verify=ssl_verify)
            self.assertEqual(r.status_code, 500)
