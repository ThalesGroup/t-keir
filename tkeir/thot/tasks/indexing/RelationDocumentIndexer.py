# -*- coding: utf-8 -*-
"""Relation document indexer
Elastic search Document index wrapper.

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.


"""

import os
import traceback
import time

from elasticsearch import Elasticsearch, RequestsHttpConnection, helpers
from thot.core.ThotLogger import ThotLogger
import thot.core.Constants as Constants
import hashlib


class RelationDocumentIndexer:
    """
    Index document with json format
    """

    # elastic search object
    es = None
    config = None

    @staticmethod
    def es_wrapper(config):
        try:
            es_hosts = [
                {"host": config["elasticsearch"]["network"]["host"], "port": config["elasticsearch"]["network"]["port"]}
            ]
            es = Elasticsearch(
                hosts=es_hosts,
                use_ssl=config["elasticsearch"]["network"]["use_ssl"],
                verify_certs=config["elasticsearch"]["network"]["verify_certs"],
                connection_class=RequestsHttpConnection,
                timeout=600,
                max_retries=100,
                retry_on_timeout=True,
                maxsize=25,
            )
            return es
        except Exception as e:
            raise ValueError(
                "Es configuration exception:" + Constants.exception_error_and_trace(str(e), str(traceback.format_exc()))
            )

    @staticmethod
    def configure(config):
        """
        Configure Document indexer
        :param config_network : network configuration for elastic search
        """
        RelationDocumentIndexer.es = RelationDocumentIndexer.es_wrapper(config)
        RelationDocumentIndexer.config = config

    @staticmethod
    def index(json_doc, doc_id=None):
        """
        Index a document
        :param json_doc: the json document in the good format (see schema)
        :return: nothing
        """
        ThotLogger.debug("[Enter]")
        if not RelationDocumentIndexer.config:
            raise ValueError("Configuration should be set.")
        if not RelationDocumentIndexer.es:
            raise ValueError("Elasticsearch not set.")
        start_time = time.time()
        ThotLogger.info("Index[ES] news document")
        results = []
        index_name = RelationDocumentIndexer.config["elasticsearch"]["nms-index"]["name"]
        try:
            hash_id = None
            if doc_id:
                hash_id = doc_id
            else:
                if ("relation" in json_doc) and ("class" in json_doc):
                    m = hashlib.md5()
                    m.update(str(json_doc["relation"] + str(json_doc["class"])).encode())
                    hash_id = "relationid_" + m.hexdigest()
            if hash_id is None:
                RelationDocumentIndexer.es.index(index=index_name, body=json_doc, doc_type="_doc")
            else:
                r = RelationDocumentIndexer.es.index(index=index_name, body=json_doc, id=hash_id, doc_type="_doc")
                ThotLogger.info("Index[" + index_name + "] id:" + hash_id + " / " + str(r))

            time_call_es = time.time() - start_time
            results = {
                "status": "success",
                "service_name": "indexer",
                "start_time": start_time,
                "time_elapsed": time_call_es,
                "doc_id": hash_id,
                "size": "",
                "error": "",
            }
        except Exception as e:
            ThotLogger.error(str(e))
            tracebck = traceback.format_exc()
            ThotLogger.error(tracebck)
            time_call_es = time.time() - start_time
            results = {
                "status": "failed",
                "service_name": "indexer",
                "start_time": start_time,
                "time_elapsed": time_call_es,
                "size": "",
                "error": Constants.exception_error_and_trace(str(e), str(traceback)),
            }
        ThotLogger.debug("[Exit]")
        return results

    @staticmethod
    def bulk(data):
        for ok, response in helpers.streaming_bulk(RelationDocumentIndexer.es, actions=data, chunk_size=200):
            if not ok:
                # failure inserting
                ThotLogger.error("FAILED Index:" + str(response))

    @staticmethod
    def delete(index_name, json_doc):
        """
        Index a document
        :param json_doc: the json document in the good format (see schema)
        :return: nothing
        """
        ThotLogger.debug("[Enter]")
        if not RelationDocumentIndexer.config:
            raise ValueError("Configuration should be set.")
        if not RelationDocumentIndexer.es:
            raise ValueError("Elasticsearch not set.")
        start_time = time.time()
        results = []
        try:
            hash_id = None
            if ("sourceName" in json_doc) and ("id" in json_doc):
                m = hashlib.md5()
                m.update(str(json_doc["sourceName"] + json_doc["id"]).encode())
                hash_id = "tkeir_" + m.hexdigest()
                ThotLogger.info("Index id:" + hash_id)
                RelationDocumentIndexer.es.delete(index=index_name, id=hash_id, doc_type="_doc")
            time_call_es = time.time() - start_time
            result = {
                "status": "success",
                "service_name": "indexer",
                "start_time": start_time,
                "time_elapsed": time_call_es,
                "size": "",
                "error": "",
            }
        except Exception as e:
            ThotLogger.error(str(e))
            tracebck = traceback.format_exc()
            ThotLogger.error(Constants.exception_error_and_trace(str(e), str(traceback)))
            time_call_es = time.time() - start_time
            results = {
                "status": "failed",
                "service_name": "indexer",
                "start_time": start_time,
                "time_elapsed": time_call_es,
                "size": "",
                "error": Constants.exception_error_and_trace(str(e), str(traceback)),
            }
        ThotLogger.debug("[Exit]")
        return results
