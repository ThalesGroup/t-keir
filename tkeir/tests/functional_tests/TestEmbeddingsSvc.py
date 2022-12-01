# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.embeddings_svc import main
import os, signal
import unittest
import time
import requests


service_pid = 0
ssl_verify = False


class TestEmbeddingsSvc(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        global service_pid
        if service_pid == 0:
            service_pid = os.fork()
            if service_pid == 0:

                class args:
                    config = os.path.abspath(
                        os.path.join(
                            os.path.dirname(os.path.realpath(__file__)), "../../../app/projects/default/configs/embeddings.json"
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
                        r = requests.get("https://localhost:10005/api/embeddings/health", verify=ssl_verify)
                        load_finish = r.status_code == 200
                    except:
                        count = count + 1
                        if count > 50:
                            load_finish = True
                            break
                        time.sleep(1)

    @classmethod
    def tearDownClass(self):
        if service_pid:
            os.kill(service_pid, signal.SIGINT)

    def test_health(self):
        if service_pid:
            r = requests.get("https://localhost:10005/api/embeddings/health", verify=ssl_verify)
            self.assertTrue(r.status_code == 200)

    def test_run(self):
        if service_pid:
            dir_path = os.path.dirname(os.path.realpath(__file__))
            data_path = os.path.abspath(os.path.join(dir_path, "../data/"))

            text = ["He lives at paris, and works at Valero Energy."]
            json_request = {
                "data_source": "tokenizer-service",
                "source_doc_id": "file://test.txt",
                "title": "Access to UBSWenergy Production Environment",
                "content": text,
                "title_tokens": ["Access", "to", "UBSWenergy", "Production", "Environment", "by", "John", "Doe"],
                "content_tokens": [
                    "He",
                    "lives",
                    "at",
                    "Paris",
                    ",",
                    "and",
                    "works",
                    "at",
                    "Valero Energy",
                    ".",
                    "His",
                    "email",
                    "is",
                    "jd@paris.fr",
                    ".",
                    "He",
                    "works",
                    "on",
                    "the",
                    "document",
                    "published",
                    "by",
                    "john",
                    "et",
                    "al",
                    ".",
                ],
            }

            r = requests.post("https://localhost:10005/api/embeddings/run", json=json_request, verify=ssl_verify)

            tkeir_doc = r.json()["results"]

            # test 500
            json_request = {"xxx": "email", "src": "file://" + os.path.join(data_path, "mail1.txt"), "data": "bad entry"}
            r = requests.post("https://localhost:10005/api/embeddings/run", json=json_request, verify=ssl_verify)
            self.assertEqual(r.status_code, 500)
