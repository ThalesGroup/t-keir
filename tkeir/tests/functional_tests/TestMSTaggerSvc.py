# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.mstagger_svc import main
import os, signal
import unittest
import time
import requests
import sys


service_pid = 0
ssl_verify = False


class TestMSTaggerSvc(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        global service_pid
        if service_pid == 0:
            service_pid = os.fork()
            if service_pid == 0:

                class args:
                    config = os.path.abspath(
                        os.path.join(
                            os.path.dirname(os.path.realpath(__file__)), "../../../app/projects/default/configs/mstagger.json"
                        )
                    )

                print(args.config)
                main(args)
            else:
                load_finish = False
                count = 0
                while not load_finish:
                    try:
                        r = requests.get("https://localhost:10002/api/mstagger/health", verify=ssl_verify)
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
            r = requests.get("https://localhost:10002/api/mstagger/health", verify=ssl_verify)
            self.assertTrue(r.status_code == 200)

    def test_run(self):
        if service_pid:
            dir_path = os.path.dirname(os.path.realpath(__file__))
            data_path = os.path.abspath(os.path.join(dir_path, "../data/"))

            text = ["He lives at Orsay, and works at Valero Energy."]
            json_request = {
                "data_source": "tokenizer-service",
                "source_doc_id": "file://test.txt",
                "title": "Access to UBSWenergy Production Environment",
                "content": text,
                "title_tokens": [
                    {"token": "Access", "start_sentence": True},
                    {"token": "to", "start_sentence": False},
                    {"token": "UBSWenergy", "start_sentence": False},
                    {"token": "Production", "start_sentence": False},
                    {"token": "Environment", "start_sentence": False},
                ],
                "content_tokens": [
                    {"token": "He", "start_sentence": True},
                    {"token": "lives", "start_sentence": False},
                    {"token": "at", "start_sentence": False},
                    {"token": "paris", "start_sentence": False},
                    {"token": ",", "start_sentence": False},
                    {"token": "and", "start_sentence": False},
                    {"token": "works", "start_sentence": False},
                    {"token": "at", "start_sentence": False},
                    {"token": "Valero Energy", "start_sentence": False},
                    {"token": ".", "start_sentence": False},
                ],
            }

            r = requests.post("https://localhost:10002/api/mstagger/run", json=json_request, verify=ssl_verify)

            tkeir_doc = r.json()["results"]

            self.assertEqual(
                tkeir_doc["title_morphosyntax"],
                [
                    {"pos": "NOUN", "lemma": "access", "text": "Access", "is_oov": False, "is_sent_start": True},
                    {"pos": "ADP", "lemma": "to", "text": "to", "is_oov": False, "is_sent_start": False},
                    {"pos": "PROPN", "lemma": "UBSWenergy", "text": "UBSWenergy", "is_oov": True, "is_sent_start": False},
                    {"pos": "PROPN", "lemma": "Production", "text": "Production", "is_oov": False, "is_sent_start": False},
                    {"pos": "PROPN", "lemma": "Environment", "text": "Environment", "is_oov": False, "is_sent_start": False},
                ],
            )

            self.assertEqual(
                tkeir_doc["content_morphosyntax"],
                [
                    {"pos": "PRON", "lemma": "he", "text": "He", "is_oov": False, "is_sent_start": True},
                    {"pos": "VERB", "lemma": "live", "text": "lives", "is_oov": False, "is_sent_start": False},
                    {"pos": "ADP", "lemma": "at", "text": "at", "is_oov": False, "is_sent_start": False},
                    {"pos": "NOUN", "lemma": "paris", "text": "paris", "is_oov": False, "is_sent_start": False},
                    {"pos": "PUNCT", "lemma": ",", "text": ",", "is_oov": False, "is_sent_start": False},
                    {"pos": "CCONJ", "lemma": "and", "text": "and", "is_oov": False, "is_sent_start": False},
                    {"pos": "VERB", "lemma": "work", "text": "works", "is_oov": False, "is_sent_start": False},
                    {"pos": "ADP", "lemma": "at", "text": "at", "is_oov": False, "is_sent_start": False},
                    {"pos": "PROPN", "lemma": "Valero Energy", "text": "Valero Energy", "is_oov": True, "is_sent_start": False},
                    {"pos": "PUNCT", "lemma": ".", "text": ".", "is_oov": False, "is_sent_start": False},
                ],
            )

            # test 500
            json_request = {"xxx": "email", "src": "file://" + os.path.join(data_path, "mail1.txt"), "data": "bad entry"}
            r = requests.post("https://localhost:10002/api/mstagger/run", json=json_request, verify=ssl_verify)
            self.assertEqual(r.status_code, 500)
