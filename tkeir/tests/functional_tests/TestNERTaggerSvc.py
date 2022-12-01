# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.nertagger_svc import main
import os, signal
import unittest
import time
import requests


service_pid = 0
ssl_verify = False


class TestNERTaggerSvc(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        global service_pid
        if service_pid == 0:
            service_pid = os.fork()
            if service_pid == 0:

                class args:
                    config = os.path.abspath(
                        os.path.join(
                            os.path.dirname(os.path.realpath(__file__)), "../../../app/projects/default/configs/nertagger.json"
                        )
                    )

                print(args.config)
                main(args)
            else:
                load_finish = False
                count = 0
                while not load_finish:
                    try:
                        r = requests.get("https://localhost:10003/api/nertagger/health", verify=ssl_verify)
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
            r = requests.get("https://localhost:10003/api/nertagger/health", verify=ssl_verify)
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
                "title_tokens": [
                    {"token": "Access", "start_sentence": True},
                    {"token": "to", "start_sentence": False},
                    {"token": "UBSWenergy", "start_sentence": False},
                    {"token": "Production", "start_sentence": False},
                    {"token": "Environment", "start_sentence": False},
                    {"token": "by", "start_sentence": False},
                    {"token": "John", "start_sentence": False},
                    {"token": "Doe", "start_sentence": False},
                ],
                "content_tokens": [
                    {"token": "He", "start_sentence": True},
                    {"token": "lives", "start_sentence": False},
                    {"token": "at", "start_sentence": False},
                    {"token": "Paris", "start_sentence": False},
                    {"token": ",", "start_sentence": False},
                    {"token": "and", "start_sentence": False},
                    {"token": "works", "start_sentence": False},
                    {"token": "at", "start_sentence": False},
                    {"token": "Valero Energy", "start_sentence": False},
                    {"token": ".", "start_sentence": False},
                    {"token": "His", "start_sentence": False},
                    {"token": "email", "start_sentence": False},
                    {"token": "is", "start_sentence": False},
                    {"token": "jd@paris.fr", "start_sentence": False},
                    {"token": ".", "start_sentence": False},
                    {"token": "He", "start_sentence": True},
                    {"token": "works", "start_sentence": False},
                    {"token": "on", "start_sentence": False},
                    {"token": "the", "start_sentence": False},
                    {"token": "document", "start_sentence": False},
                    {"token": "published", "start_sentence": False},
                    {"token": "by", "start_sentence": False},
                    {"token": "john", "start_sentence": False},
                    {"token": "et", "start_sentence": False},
                    {"token": "al", "start_sentence": False},
                    {"token": ".", "start_sentence": False},
                ],
                "title_morphosyntax": [
                    {"pos": "NOUN", "lemma": "access", "text": "Access"},
                    {"pos": "ADP", "lemma": "to", "text": "to"},
                    {"pos": "PROPN", "lemma": "UBSWenergy", "text": "UBSWenergy"},
                    {"pos": "PROPN", "lemma": "Production", "text": "Production"},
                    {"pos": "PROPN", "lemma": "Environment", "text": "Environment"},
                    {"pos": "ADP", "lemma": "by", "text": "by"},
                    {"pos": "PROPN", "lemma": "John", "text": "John"},
                    {"pos": "PROPN", "lemma": "Doe", "text": "Doe"},
                ],
                "content_morphosyntax": [
                    {"pos": "PRON", "lemma": "he", "text": "He"},
                    {"pos": "VERB", "lemma": "live", "text": "lives"},
                    {"pos": "ADP", "lemma": "at", "text": "at"},
                    {"pos": "PROPN", "lemma": "Paris", "text": "Paris"},
                    {"pos": "PUNCT", "lemma": ",", "text": ","},
                    {"pos": "CCONJ", "lemma": "and", "text": "and"},
                    {"pos": "VERB", "lemma": "work", "text": "works"},
                    {"pos": "ADP", "lemma": "at", "text": "at"},
                    {"pos": "PROPN", "lemma": "Valero Energy", "text": "Valero Energy"},
                    {"pos": "PUNCT", "lemma": ".", "text": "."},
                    {"pos": "PRON", "lemma": "his", "text": "His"},
                    {"pos": "NOUN", "lemma": "email", "text": "email"},
                    {"pos": "VERB", "lemma": "be", "text": "is"},
                    {"pos": "ADJ", "lemma": "jd@paris.fr", "text": "jd@paris.fr"},
                    {"pos": "PUNCT", "lemma": ".", "text": "."},
                    {"pos": "PRON", "lemma": "he", "text": "He"},
                    {"pos": "VERB", "lemma": "work", "text": "works"},
                    {"pos": "ADP", "lemma": "on", "text": "on"},
                    {"pos": "DET", "lemma": "the", "text": "the"},
                    {"pos": "NOUN", "lemma": "document", "text": "document"},
                    {"pos": "VERB", "lemma": "publish", "text": "published"},
                    {"pos": "ADP", "lemma": "by", "text": "by"},
                    {"pos": "PROPN", "lemma": "john", "text": "john"},
                    {"pos": "NOUN", "lemma": "et", "text": "et"},
                    {"pos": "PROPN", "lemma": "al", "text": "al"},
                    {"pos": "PUNCT", "lemma": ".", "text": "."},
                ],
            }

            r = requests.post("https://localhost:10003/api/nertagger/run", json=json_request, verify=ssl_verify)

            tkeir_doc = r.json()["results"]

            title_ner = [{"start": 6, "end": 8, "label": "person", "text": "John Doe"}]
            content_ner = [
                {"start": 3, "end": 4, "label": "location", "text": "Paris"},
                {"start": 8, "end": 9, "label": "organization", "text": "Valero Energy"},
                {"start": 13, "end": 14, "label": "email", "text": "jd@paris.fr"},
                {"start": 22, "end": 25, "label": "cite_person", "text": "john et al"},
            ]

            self.assertEqual(tkeir_doc["title_ner"], title_ner)
            self.assertEqual(tkeir_doc["content_ner"], content_ner)

            # test 500
            json_request = {"xxx": "email", "src": "file://" + os.path.join(data_path, "mail1.txt"), "data": "bad entry"}
            r = requests.post("https://localhost:10003/api/nertagger/run", json=json_request, verify=ssl_verify)
            self.assertEqual(r.status_code, 500)
