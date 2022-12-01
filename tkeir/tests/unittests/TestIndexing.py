# -*- coding: utf-8 -*-
"""Test Indexing
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.indexing.IndexingConfiguration import IndexingConfiguration
from thot.tasks.indexing.Indexing import Indexing
from thot.tasks.indexing.IndicesManager import IndicesManager
from thot.core.ThotLogger import ThotLogger, LogUserContext
import unittest
import json
import traceback
import os
from uuid import uuid4

dir_path = os.path.dirname(os.path.realpath(__file__))
test_file_path = os.path.abspath(os.path.join(dir_path, "../data/test-outputs-syntax"))


class TestIndexing(unittest.TestCase):

    test_dict = {
        "logger": {"logging-level": "debug"},
        "indexing": {
            "document": {"remove-knowledge-graph-duplicates": True},
            "elasticsearch": {
                "network": {
                    "host": "opendistro",
                    "port": 9200,
                    "use_ssl": False,
                    "verify_certs": False,
                    "auth": {
                        "user": "admin",
                        "password": "admin",
                        "associate-environment": {"user": "OPENDISTRO_USER", "password": "OPENDISTRO_PASSWORD"},
                    },
                    "associate-environment": {
                        "host": "OPENDISTRO_DNS_HOST",
                        "port": "OPENDISTRO_PORT",
                        "use_ssl": "OPENDISTRO_USE_SSL",
                        "verify_certs": "OPENDISTRO_VERIFY_CERTS",
                    },
                },
                "nms-index": {
                    "name": "default-nms-index",
                    "mapping-file": "/home/tkeir_svc/tkeir/resources/indices/indices_mapping/nms_cache_index.json",
                },
                "text-index": {
                    "name": "default-text-index",
                    "mapping-file": "/home/tkeir_svc/tkeir/resources/indices/indices_mapping/cache_index.json",
                },
                "relation-index": {
                    "name": "default-relation-index",
                    "mapping-file": "/home/tkeir_svc/tkeir/resources/indices/indices_mapping/relation_index.json",
                },
            },
            "network": {
                "host": "0.0.0.0",
                "port": 10012,
                "associate-environment": {"host": "INDEX_HOST", "port": "INDEX_PORT"},
            },
            "runtime": {
                "request-max-size": 100000000,
                "request-buffer-queue-size": 100,
                "keep-alive": True,
                "keep-alive-timeout": 500,
                "graceful-shutown-timeout": 15.0,
                "request-timeout": 600,
                "response-timeout": 600,
                "workers": 1,
            },
            "serialize": {
                "input": {"path": "/tmp", "keep-service-info": True},
                "output": {"path": "/tmp", "keep-service-info": True},
            },
        },
    }

    @classmethod
    def setUpClass(self):
        with open("/tmp/cfg.json", "w") as f:
            json.dump(TestIndexing.test_dict, f)
            f.close()
            fh = open("/tmp/cfg.json")
            indexConfig = IndexingConfiguration()
            indexConfig.load(fh)
            fh.close()
            IndicesManager.createIndices(config=indexConfig.configuration)

    @classmethod
    def tearDownClass(self):
        with open("/tmp/cfg.json", "w") as f:
            json.dump(TestIndexing.test_dict, f)
            f.close()
            fh = open("/tmp/cfg.json")
            indexConfig = IndexingConfiguration()
            indexConfig.load(fh)
            es_host = indexConfig.configuration["elasticsearch"]["network"]["host"]
            fh.close()
            os.system("curl -XDELETE http://" + es_host + ":9200/test-text-index")
            os.system("curl -XDELETE http://" + es_host + ":9200/test-relation-index")
            os.system("curl -XDELETE http://" + es_host + ":9200/test-nms-index")

    def test_doc2index(self):
        try:
            with open("/tmp/cfg.json", "w") as f:
                json.dump(TestIndexing.test_dict, f)
                f.close()
        except Exception as e:
            print(str(e) + " trace:" + str(traceback.format_exc()))
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        indexConfig = IndexingConfiguration()
        indexConfig.load(fh)
        fh.close()
        dir_path = os.path.dirname(os.path.realpath(__file__))
        test_file_path = os.path.abspath(os.path.join(dir_path, "../data/test-index/"))
        with open(os.path.join(test_file_path, "fulldoc.json")) as f:
            tkeir_doc = json.load(f)
            f.close()
            indexing = Indexing(config=indexConfig)
            index_doc = indexing.doc2index(tkeir_doc)
            self.assertEqual(index_doc[0], "tkeir-id-8c68f454691fc898dd72a47781347ae4")

    def test_index(self):
        try:
            with open("/tmp/cfg.json", "w") as f:
                json.dump(TestIndexing.test_dict, f)
                f.close()
        except Exception as e:
            print(str(e) + " trace:" + str(traceback.format_exc()))
        fh = open("/tmp/cfg.json")
        indexConfig = IndexingConfiguration()
        indexConfig.load(fh)
        fh.close()
        indexing = Indexing(config=indexConfig)
        dir_path = os.path.dirname(os.path.realpath(__file__))
        test_file_path = os.path.abspath(os.path.join(dir_path, "../data/test-index/"))
        with open(os.path.join(test_file_path, "fulldoc.json")) as f:
            tkeir_doc = json.load(f)
            f.close()
            cid = "autogenerated-" + str(uuid4())
            log_context = LogUserContext(cid)
            index_doc = indexing.index(tkeir_doc, call_context=log_context)
            self.assertTrue(True)
