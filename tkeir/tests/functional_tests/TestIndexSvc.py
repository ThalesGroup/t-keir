# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.index_svc import main
import os, signal
import unittest
import time
import requests
import json
from uuid import uuid4


service_pid = 0
ssl_verify = False


class TestIndexSvc(unittest.TestCase):
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
                            "../../../app/projects/default/configs/indexing-ssl.json",
                        )
                    )

                main(args)
            else:
                load_finish = False
                count = 0
                while not load_finish:
                    try:
                        r = requests.get("https://localhost:10012/api/indexing/health", verify=ssl_verify)
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
            r = requests.get("https://localhost:10012/api/indexing/health", verify=ssl_verify)
            self.assertTrue(r.status_code == 200)

    def test_run(self):
        if service_pid:
            dir_path = os.path.dirname(os.path.realpath(__file__))
            test_file_path = os.path.abspath(os.path.join(dir_path, "../data/test-index/"))
            with open(os.path.join(test_file_path, "fulldoc.json")) as f:
                tkeir_doc = json.load(f)
                f.close()
                r = requests.post("https://localhost:10012/api/indexing/run", json=tkeir_doc, verify=ssl_verify)
                self.assertEqual(r.status_code, 200)

            # test 500
            json_request = {"xxx": "email", "src": "file://" + os.path.join("//", "mail1.txt"), "data": "bad entry"}
            r = requests.post("https://localhost:10012/api/indexing/run", json=json_request, verify=ssl_verify)
            self.assertEqual(r.status_code, 500)
