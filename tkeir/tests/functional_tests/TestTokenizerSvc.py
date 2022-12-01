# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tokenizer_svc import main
import os, signal
import unittest
import time
import requests


service_pid = 0
ssl_verify = False


class TestTokenizerSvc(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        global service_pid
        if service_pid == 0:
            service_pid = os.fork()
            if service_pid == 0:

                class args:
                    config = os.path.abspath(
                        os.path.join(
                            os.path.dirname(os.path.realpath(__file__)), "../../../app/projects/default/configs/tokenizer.json"
                        )
                    )
                    init = False

                main(args)
            else:
                load_finish = False
                count = 0
                while not load_finish:
                    try:
                        r = requests.get(
                            "https://localhost:10001/api/tokenizer/health",
                            verify=ssl_verify,
                            headers={"x-correlation-id": "functional-test0"},
                        )
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
            r = requests.get(
                "https://localhost:10001/api/tokenizer/health",
                verify=ssl_verify,
                headers={"x-correlation-id": "functional-test1"},
            )
            self.assertTrue(r.status_code == 200)

    def test_run(self):
        if service_pid:
            dir_path = os.path.dirname(os.path.realpath(__file__))
            data_path = os.path.abspath(os.path.join(dir_path, "../data/"))

            text = [
                [
                    "A new study is the first to identify how human brains grow much larger, with three times as many neurons, compared with chimpanzee and gorilla brains. The study, led by researchers at the Medical Research Council (MRC) Laboratory of Molecular Biology in Cambridge, UK, identified a key molecular switch that can make ape brain organoids grow more like human organoids, and vice versa."
                ],
                [
                    "The study, published in the journal Cell, compared brain organoids -- 3D tissues grown from stem cells which model early brain development -- that were grown from human, gorilla and chimpanzee stem cells.Similar to actual brains, the human brain organoids grew a lot larger than the organoids from other apes.Dr Madeline Lancaster, from the MRC Laboratory of Molecular Biology, who led the study, said: This provides some of the first insight into what is different about the developing human brain that sets us apart from our closest living relatives, the other great apes. The most striking difference between us and other apes is just how incredibly big our brains are.During the early stages of brain development, neurons are made by stem cells called neural progenitors. These progenitor cells initially have a cylindrical shape that makes it easy for them to split into identical daughter cells with the same shape."
                ],
            ]

            json_request = {
                "data_source": "tokenizer-service",
                "source_doc_id": "file://test.txt",
                "title": "Access to UBSWenergy Production Environment",
                "content": text,
            }

            r = requests.post(
                "https://localhost:10001/api/tokenizer/run",
                json=json_request,
                verify=ssl_verify,
                headers={"x-correlation-id": "functional-test2"},
            )
            tkeir_doc = r.json()["results"]
            content_tokens = [
                [
                    [
                        [
                            {"token": "A", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "new", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "study", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "is", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "first", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "to", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "identify", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "how", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "human", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "brains", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "grow", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "much", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "larger", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "with", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "three", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "times", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "as", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "many", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "neurons", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "compared", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "with", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "chimpanzee", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "and", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "gorilla", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "brains", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        ],
                        [
                            {"token": "The", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "study", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "led", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "by", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "researchers", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "at", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Medical", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Research", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Council", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "(", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "MRC", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ")", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Laboratory", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "of", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Molecular", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Biology", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "in", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Cambridge", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "UK", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "identified", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "a", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "key", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "molecular", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "switch", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "that", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "can", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "make", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "ape", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "brain", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "organoids", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "grow", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "more", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "like", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "human", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "organoids", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "and", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "vice", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "versa", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        ],
                    ]
                ],
                [
                    [
                        [
                            {"token": "The", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "study", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "published", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "in", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "journal", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Cell", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "compared", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "brain", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "organoids", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "--", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "3D", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "tissues", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "grown", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "from", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "stem", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "cells", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "which", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "model", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "early", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "brain", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "development", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "--", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "that", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "were", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "grown", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "from", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "human", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "gorilla", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "and", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "chimpanzee", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "stem", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "cells", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Similar", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "to", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "actual", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "brains", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "human", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "brain", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "organoids", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "grew", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "a", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "lot", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "larger", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "than", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "organoids", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "from", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "other", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "apes", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Dr", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Madeline", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Lancaster", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "from", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "MRC", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Laboratory", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "of", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Molecular", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Biology", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "who", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "led", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "study", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "said", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ":", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "This", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "provides", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "some", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "of", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "first", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "insight", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "into", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "what", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "is", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "different", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "about", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "developing", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "human", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "brain", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "that", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "sets", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "us", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "apart", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "from", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "our", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "closest", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "living", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "relatives", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "other", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "great", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "apes", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        ],
                        [
                            {"token": "The", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "most", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "striking", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "difference", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "between", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "us", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "and", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "other", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "apes", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "is", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "just", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "how", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "incredibly", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "big", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "our", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "brains", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "are", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "During", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "early", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "stages", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "of", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "brain", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "development", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "neurons", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "are", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "made", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "by", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "stem", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "cells", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "called", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "neural", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "progenitors", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        ],
                        [
                            {"token": "These", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "progenitor", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "cells", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "initially", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "have", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "a", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "cylindrical", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "shape", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "that", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "makes", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "it", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "easy", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "for", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "them", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "to", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "split", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "into", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "identical", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "daughter", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "cells", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "with", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "same", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "shape", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        ],
                    ]
                ],
            ]
            title_tokens = [
                [
                    {"token": "Access", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                    {"token": "to", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {"token": "UBSWenergy", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {"token": "Production", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {"token": "Environment", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                ]
            ]
            self.assertEqual(tkeir_doc["content_tokens"], content_tokens)
            self.assertEqual(tkeir_doc["title_tokens"], title_tokens)
            # test 500
            json_request = {"xxx": "email", "src": "file://" + os.path.join(data_path, "mail1.txt"), "data": "bad entry"}
            r = requests.post(
                "https://localhost:10001/api/tokenizer/run",
                json=json_request,
                verify=ssl_verify,
                headers={"x-correlation-id": "functional-test3"},
            )
            self.assertEqual(r.status_code, 500)
