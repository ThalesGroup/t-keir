# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.converter_svc import main
import os, signal
import unittest
import base64
import time
import requests


service_pid = 0
ssl_verify = False


class TestConverterSvc(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        global service_pid
        if service_pid == 0:
            service_pid = os.fork()
            if service_pid == 0:
                os.environ["CONVERTER_HOST"] = "127.0.0.1"

                class args:
                    config = os.path.abspath(
                        os.path.join(
                            os.path.dirname(os.path.realpath(__file__)), "../../../app/projects/default/configs/converter.json"
                        )
                    )

                main(args)
            else:
                os.environ["CONVERTER_HOST"] = "127.0.0.1"
                load_finish = False
                count = 0
                while not load_finish:
                    try:
                        r = requests.get("https://127.0.0.1:10000/api/converter/health", verify=ssl_verify)
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
            r = requests.get("https://127.0.0.1:10000/api/converter/health", verify=ssl_verify)
            self.assertTrue(r.status_code == 200)

    def test_listTypes(self):
        if service_pid:
            r = requests.get("https://127.0.0.1:10000/api/converter/list-types", verify=ssl_verify)
            self.assertTrue(r.status_code == 200)
            r_json = r.json()
            self.assertTrue("raw" in r_json["results"])
            self.assertTrue("email" in r_json["results"])

    def test_run(self):
        if service_pid:
            dir_path = os.path.dirname(os.path.realpath(__file__))
            data_path = os.path.abspath(os.path.join(dir_path, "../data/test-raw/mail"))
            with open(os.path.join(data_path, "mail1.txt"), "rb") as f:
                data = base64.b64encode(f.read()).decode()
                f.close()
                # test 200
                json_request = {"datatype": "email", "source": "file://" + os.path.join(data_path, "mail1.txt"), "data": data}
                r = requests.post(
                    "https://127.0.0.1:10000/api/converter/run",
                    json=json_request,
                    verify=ssl_verify,
                    headers={"x-correlation-id": "functional-test1"},
                )
                test_dict = {
                    "data_source": "converter-service",
                    "source_doc_id": "file://mail1.txt",
                    "title": "Access to UBSWenergy Production Environment",
                    "content": [
                        "IMPORTANT- THE IDS BELOW WILL BE YOUR PERMANENT ACCESS TO PRODUCTION Your\nPRODUCTION User ID and Password has been set up on UBSWenergy. Please follow\nthe steps below to access the new environment: From Internet Explorer connect\nto the UBSWenergy Production Cluster through the following link:\nhttp://remoteservices.netco.enron.com/ica/ubswenergy.ica (use your\nUBSWenergy/Enron NT Log In & Password) From the second Start menu, select\nappropriate application: STACK MANAGER User ID: JZUFFER Password: q 9M npX\n(Please Change) Below is a special internal use only link for the simulation\npurposes only to get to the trading area of the website. DO NOT PROVIDE THIS\nLINK TO ANYONE NOT PART OF THE SIMULATION. (customers should be directed to go\nto the direct link www.ubsenergy.com).\nhttp://www.ubswenergy.com/site_index.html (FOR SIMULATION ONLY) WEBSITE - Book\n(ALBERTA LONG TERM POWER) User ID: MUS93962 Password: WELCOME! WEBSITE - Book\n(ALBERTA ORIGINATION) User ID: MUS93124 Password: WELCOME! WEBSITE - Book\n(ALBERTA TRANSFER BOOK) User ID: MUS52346 Password: WELCOME! PLEASE DO NOT\nTRANSACT BEFORE SIMULATION TOMORROW! Should you have any questions or issues,\nplease contact me at x33465 or the Call Center at 713-584-4444 Thank you,\nStephanie Sever 713-853-3465\n\n"
                    ],
                    "kg": [
                        {
                            "subject": {
                                "content": "stephanie.sever@enron.com",
                                "lemma_content": "stephanie.sever@enron.com",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "value": {"content": "email", "lemma_content": "email", "positions": [-1], "label_content": ""},
                            "property": {
                                "content": "rel:instanceof",
                                "lemma_content": "rel:instanceof",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "automatically_fill": True,
                            "confidence": 1.0,
                            "weight": 0.0,
                            "field_type": "mail-header",
                        },
                        {
                            "subject": {
                                "content": "Sever, Stephanie",
                                "lemma_content": "Sever, Stephanie",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "value": {"content": "person", "lemma_content": "person", "positions": [-1], "label_content": ""},
                            "property": {
                                "content": "rel:instanceof",
                                "lemma_content": "rel:instanceof",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "automatically_fill": True,
                            "confidence": 1.0,
                            "weight": 0.0,
                            "field_type": "mail-header",
                        },
                        {
                            "subject": {
                                "content": "stephanie.sever@enron.com",
                                "lemma_content": "stephanie.sever@enron.com",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "value": {
                                "content": "john.zufferli@enron.com",
                                "lemma_content": "john.zufferli@enron.com",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "property": {
                                "content": "rel:mailto",
                                "lemma_content": "rel:mailto",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "automatically_fill": True,
                            "confidence": 1.0,
                            "weight": 0.0,
                            "field_type": "mail-header",
                        },
                        {
                            "subject": {"content": "Sever", "lemma_content": "Sever", "positions": [-1], "label_content": ""},
                            "value": {
                                "content": "Zufferli",
                                "lemma_content": "Zufferli",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "property": {
                                "content": "rel:mailto",
                                "lemma_content": "rel:mailto",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "automatically_fill": True,
                            "confidence": 1.0,
                            "weight": 0.0,
                            "field_type": "mail-header",
                        },
                        {
                            "subject": {"content": "Sever", "lemma_content": "Sever", "positions": [-1], "label_content": ""},
                            "value": {"content": "John", "lemma_content": "John", "positions": [-1], "label_content": ""},
                            "property": {
                                "content": "rel:mailto",
                                "lemma_content": "rel:mailto",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "automatically_fill": True,
                            "confidence": 1.0,
                            "weight": 0.0,
                            "field_type": "mail-header",
                        },
                        {
                            "subject": {
                                "content": " Stephanie",
                                "lemma_content": " Stephanie",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "value": {
                                "content": "Zufferli",
                                "lemma_content": "Zufferli",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "property": {
                                "content": "rel:mailto",
                                "lemma_content": "rel:mailto",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "automatically_fill": True,
                            "confidence": 1.0,
                            "weight": 0.0,
                            "field_type": "mail-header",
                        },
                        {
                            "subject": {
                                "content": " Stephanie",
                                "lemma_content": " Stephanie",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "value": {"content": "John", "lemma_content": "John", "positions": [-1], "label_content": ""},
                            "property": {
                                "content": "rel:mailto",
                                "lemma_content": "rel:mailto",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "automatically_fill": True,
                            "confidence": 1.0,
                            "weight": 0.0,
                            "field_type": "mail-header",
                        },
                        {
                            "subject": {
                                "content": "Zufferli",
                                "lemma_content": "Zufferli",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "value": {"content": "person", "lemma_content": "person", "positions": [-1], "label_content": ""},
                            "property": {
                                "content": "rel:instanceof",
                                "lemma_content": "rel:instanceof",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "automatically_fill": True,
                            "confidence": 1.0,
                            "weight": 0.0,
                            "field_type": "mail-header",
                        },
                        {
                            "subject": {"content": "John", "lemma_content": "John", "positions": [-1], "label_content": ""},
                            "value": {"content": "person", "lemma_content": "person", "positions": [-1], "label_content": ""},
                            "property": {
                                "content": "rel:instanceof",
                                "lemma_content": "rel:instanceof",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "automatically_fill": True,
                            "confidence": 1.0,
                            "weight": 0.0,
                            "field_type": "mail-header",
                        },
                        {
                            "subject": {
                                "content": "Wed, 06 Feb 2002 14:04:29 -0800",
                                "lemma_content": "Wed, 06 Feb 2002 14:04:29 -0800",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "value": {"content": "date", "lemma_content": "date", "positions": [-1], "label_content": ""},
                            "property": {
                                "content": "rel:instanceof",
                                "lemma_content": "rel:instanceof",
                                "positions": [-1],
                                "label_content": "",
                            },
                            "automatically_fill": True,
                            "confidence": 1.0,
                            "weight": 0.0,
                            "field_type": "mail-header",
                        },
                    ],
                    "error": False,
                }
                doc = r.json()["results"]
                del doc["tasks-info"]
                self.assertEqual(test_dict["title"], doc["title"])
                self.assertEqual(test_dict["content"], doc["content"])
                self.assertEqual(test_dict["kg"], doc["kg"])
                # test 422
                json_request = {"badtype": "email", "source": "file://" + os.path.join(data_path, "mail1.txt"), "data": "none"}
                r = requests.post(
                    "https://127.0.0.1:10000/api/converter/run",
                    json=json_request,
                    verify=ssl_verify,
                    headers={"x-correlation-id": "functional-test2"},
                )
                self.assertEqual(r.status_code, 422)
                # test 500
                json_request = {
                    "datatype": "email",
                    "source": "file://" + os.path.join(data_path, "mail1.txt"),
                    "data": "bad base64 entry",
                }
                r = requests.post(
                    "https://127.0.0.1:10000/api/converter/run",
                    json=json_request,
                    verify=ssl_verify,
                    headers={"x-correlation-id": "functional-test3"},
                )
                self.assertEqual(r.status_code, 500)
