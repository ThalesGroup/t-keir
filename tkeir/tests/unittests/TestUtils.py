# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.core.Utils import (
    check_pid,
    timelimit,
    mkdir_p,
    type_to_bool,
    generate_id,
    is_numeric,
    is_email,
    get_elastic_url,
    save_json,
    load_json,
)
import time
import os
import unittest

def myrunfun(timewait):
    t=time.time()
    time.sleep(timewait)    
    return 3

class TestUtils(unittest.TestCase):
    def test_check_pid(self):
        self.assertFalse(check_pid(123))
        self.assertTrue(check_pid(os.getpid()))

    def test_timelimit(self):
        try:
            x = timelimit(50,myrunfun,args=(2,))
            self.assertTrue(True)
        except:
            self.assertTrue(False)
        try:
            timelimit(1,myrunfun,args=(5,))
            self.assertTrue(False)
        except Exception as ex:
            self.assertTrue(True)


    def test_mkdir_p(self):
        self.assertTrue(True)

    def test_type_to_bool(self):
        self.assertTrue(type_to_bool("1"))
        self.assertTrue(type_to_bool(1))
        self.assertTrue(type_to_bool("TrUe"))
        self.assertFalse(type_to_bool("0"))
        self.assertFalse(type_to_bool(0))
        self.assertFalse(type_to_bool("fAlSe"))

    def test_generate_id(self):
        self.assertTrue(True)

    def test_is_numeric(self):
        self.assertTrue(is_numeric(1))
        self.assertTrue(is_numeric(1.0))
        self.assertFalse(is_numeric("aaa&ze"))

    def test_getElasticURL(self):
        (es_url, es_verify) = get_elastic_url(
            {
                "network": {
                    "host": "opendistro",
                    "port": 9200,
                    "use_ssl": False,
                    "verify_certs": False,
                    "auth": {
                        "user": "admin",
                        "password": "admin",
                    },
                }
            }
        )
        self.assertEqual(es_url, "http://admin:admin@opendistro:9200")
        self.assertFalse(es_verify)

        (es_url, es_verify) = get_elastic_url(
            {
                "network": {
                    "host": "opendistro",
                    "port": 9200,
                    "use_ssl": True,
                    "verify_certs": True,
                    "auth": {
                        "user": "admin",
                        "password": "admin",
                    },
                }
            }
        )
        self.assertEqual(es_url, "https://admin:admin@opendistro:9200")
        self.assertTrue(es_verify)

        (es_url, es_verify) = get_elastic_url(
            {"network": {"host": "opendistro", "port": 9200, "use_ssl": False, "verify_certs": False}}
        )
        self.assertEqual(es_url, "http://opendistro:9200")
        self.assertFalse(es_verify)

    def test_json_save_and_load(self):
        data = {"test-me": "test", "is-json": True}
        save_json(data, "/tmp/file.json")
        loaded_data = load_json("/tmp/file.json")
        self.assertEqual(data, loaded_data)

    def test_json_save_and_load_zip(self):
        data = {"test-me": "test", "is-json": True}
        save_json(data, "/tmp/file.json.gz", zip_file=True)
        loaded_data = load_json("/tmp/file.json.gz", zip_file=True)
        self.assertEqual(data, loaded_data)
