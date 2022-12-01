# -*- coding: utf-8 -*-
"""Document indexer
Elastic search Document index wrapper.

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.


"""

import os
import traceback
import time
import requests

from elasticsearch import Elasticsearch, helpers
from thot.core.ThotLogger import ThotLogger
import thot.core.Constants as Constants
from thot.core.Utils import get_elastic_url
import hashlib


class ESDocumentIndexer:
    """
    Index document with json format
    """

    # elastic search object
    es = None
    config = None
    count_indexed_file = 0

    @staticmethod
    def es_wrapper(config):
        """ ElasticSearch wrapper
        Args:
            - config : host and port configuration
        Return : Elatisticsearch class
        """
        
        try:
            (es_url, es_verify_cert) = get_elastic_url(config["elasticsearch"])
            es_hosts = [
                {"host": config["elasticsearch"]["network"]["host"], "port": config["elasticsearch"]["network"]["port"]}
            ]
            es = Elasticsearch(
                hosts=[es_url],
                verify_certs=es_verify_cert,
                timeout=600,
                max_retries=100,
                retry_on_timeout=True,
                maxsize=25,
            )
            return es
        except Exception as e:
            raise ValueError("Es configuration. " + Constants.exception_error_and_trace(str(e), str(traceback.format_exc())))

    @staticmethod
    def configure(config):
        """ Configure E.S """
        ESDocumentIndexer.es = ESDocumentIndexer.es_wrapper(config)
        ESDocumentIndexer.config = config
        scheme = "http"
        (es_url, verify_ssl) = get_elastic_url(config["elasticsearch"])

        elastic_found = False
        count = 0
        while (not elastic_found) and (count < 60):
            ThotLogger.info(" ****** Try connnect to E.S[" + str(count) + "]:" + es_url)
            try:
                r = requests.get(es_url, verify=verify_ssl)
                if r.status_code == 200:
                    elastic_found = True
            except:
                ThotLogger.info(" ****** Try connnect to E.S[" + str(count) + "] Failed")

            count = count + 1
            time.sleep(1)
        if not elastic_found:
            raise ValueError("Not elastic search found")
        ThotLogger.info("Configure Document Indexer")

    @staticmethod
    def index(json_doc, doc_id=None, call_context=None):
        """
        Index a document
        :param json_doc: the json document in the good format (see schema)
        :return: nothing
        """
        if not ESDocumentIndexer.config:
            raise ValueError("Configuration should be set. Please use initialize")
        if not ESDocumentIndexer.es:
            raise ValueError("Elasticsearch not set.")
        start_time = time.time()
        ThotLogger.info("Index[ES] news document", context=call_context)
        results = []
        index_name = ESDocumentIndexer.config["elasticsearch"]["text-index"]["name"]
        try:
            hash_id = None
            if doc_id:
                hash_id = doc_id
            else:
                if ("title" in json_doc) or ("content" in json_doc):
                    m = hashlib.md5()
                    m.update(str(json_doc["title"] + json_doc["content"] + json_doc["source_doc_id"]).encode())
                    hash_id = "tkeir-id-" + m.hexdigest()

            if hash_id is None:
                ThotLogger.info("Index id:" + hash_id, context=call_context)
                r = ESDocumentIndexer.es.index(index=index_name, body=json_doc, doc_type="_doc")
                ESDocumentIndexer.count_indexed_file = ESDocumentIndexer.count_indexed_file + 1
                ThotLogger.info(
                    "Index[" + index_name + "] / " + str(r) + " **COUNT:" + str(ESDocumentIndexer.count_indexed_file)+" doc:"+str(json_doc["source_doc_id"]),
                    context=call_context
                )

            else:
                ThotLogger.info("Index id:" + hash_id, context=call_context)
                r = ESDocumentIndexer.es.index(index=index_name, body=json_doc, id=hash_id, doc_type="_doc")
                ESDocumentIndexer.count_indexed_file = ESDocumentIndexer.count_indexed_file + 1
                ThotLogger.info(
                    "Index["
                    + index_name
                    + "] id:"
                    + hash_id
                    + " / "
                    + str(r)
                    + " **COUNT:"
                    + str(ESDocumentIndexer.count_indexed_file)
                    + " doc:"+str(json_doc["source_doc_id"]),
                    context=call_context
                )

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
            tr = Constants.exception_error_and_trace(str(e), str(traceback.format_exc())) + "| On doc:"+str(json_doc["source_doc_id"])
            ThotLogger.error("Exception occured.", trace=tr, context=call_context)
            time_call_es = time.time() - start_time
            results = {
                "status": "failed",
                "service_name": "indexer",
                "start_time": start_time,
                "time_elapsed": time_call_es,
                "size": "",
                "error": str(e) + "trace:" + tr,
            }
        return results

    @staticmethod
    def bulk(data):
        for ok, response in helpers.streaming_bulk(ESDocumentIndexer.es, actions=data, chunk_size=200):
            if not ok:
                # failure inserting
                ThotLogger.error("FAILED Index[" + str(response) + "]")

    @staticmethod
    def delete(json_doc, call_context=None):
        """
        Delete a document
        :param json_doc: the json document in the good format (see schema)
        :return: nothing
        """
        if not ESDocumentIndexer.config:
            raise ValueError("Configuration should be set.")
        if not ESDocumentIndexer.es:
            raise ValueError("Elasticsearch not set.")
        index_name = ESDocumentIndexer.config["elasticsearch"]["text-index"]["name"]

        start_time = time.time()
        results = []
        try:
            hash_id = None
            if ("sourceName" in json_doc) and ("id" in json_doc):
                m = hashlib.md5()
                m.update(str(json_doc["sourceName"] + json_doc["id"]).encode())
                hash_id = "tkeir_" + m.hexdigest()
                ThotLogger.info("Index id:" + hash_id)
                ESDocumentIndexer.es.delete(index=index_name, id=hash_id, doc_type="_doc")
            time_call_es = time.time() - start_time
            results = {
                "status": "success",
                "service_name": "indexer",
                "start_time": start_time,
                "time_elapsed": time_call_es,
                "size": "",
                "error": "",
            }
        except Exception as e:
            tr = Constants.exception_error_and_trace(str(e), str(traceback.format_exc()))
            ThotLogger.error("Exception occured.", trace=tr, context=call_context)
            time_call_es = time.time() - start_time
            results = {
                "status": "failed",
                "service_name": "indexer",
                "start_time": start_time,
                "time_elapsed": time_call_es,
                "size": "",
                "error": tr,
            }
        return results

    @staticmethod
    def delete_with_id(hash_id, call_context=None):
        try:
            start_time = time.time()
            index_name = ESDocumentIndexer.config["elasticsearch"]["text-index"]["name"]
            r = ESDocumentIndexer.es.delete(index=index_name, id=hash_id, doc_type="_doc")
            time_call_es = time.time() - start_time
            results = {
                "status": "success",
                "service_name": "indexer",
                "info": r,
                "start_time": start_time,
                "time_elapsed": time_call_es,
                "size": "",
                "error": "",
            }
        except Exception as e:
            tr = Constants.exception_error_and_trace(str(e), str(traceback.format_exc()))
            ThotLogger.error("Exception occured.", trace=tr, context=call_context)
            time_call_es = time.time() - start_time
            results = {
                "status": "failed",
                "service_name": "indexer",
                "start_time": start_time,
                "time_elapsed": time_call_es,
                "size": "",
                "error": tr,
            }
        return results
