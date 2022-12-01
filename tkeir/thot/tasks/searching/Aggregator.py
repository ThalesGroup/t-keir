# -*- coding: utf-8 -*-
"""Aggregator
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""


import requests
import base64
import json
import threading
from copy import deepcopy
import traceback
import urllib.parse
from urllib.parse import urlparse
from thot.core.Utils import is_numeric
import thot.core.Constants as Constants
from thot.core.ThotLogger import ThotLogger
from thot.core.Utils import generate_id
from thot.tasks.searching.SearchingConfiguration import SearchingConfiguration
from thot.core.Utils import get_elastic_url


def run_search_request(searchid, agg, query, pageno, call_context=None):
    searx_url = agg.searx_url
    try:
        encoded_url = searx_url + "&pageno=" + str(int(pageno)) + "&q=" + urllib.parse.quote(query)
        r = requests.get(encoded_url)
        if r.status_code == 200:
            searx_return = r.json()
            if "results" in searx_return:
                ThotLogger.info("Index " + str(len(searx_return)) + " results from searx", context=call_context)
                agg.index_results(deepcopy(searx_return["results"]), call_context=call_context)
            else:
                ThotLogger.info("No results from searx : " + encoded_url, context=call_context)
    except Exception as e:
        ThotLogger.warning(
            "Cannot open url '" + searx_url + "' ",
            trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
            context=call_context,
        )


class Aggregator:
    def __init__(self, config: SearchingConfiguration, call_context=None):
        """Initialize Aggregator

        Args:
            config (SearchingConfiguration): configuration of search engine
        """
        self.config = config
        if "aggregator" not in config.configuration:
            raise ValueError("aggregator field is mandatory.")
        self.pipeline_scheme = "http"
        self.pipeline_ssl_verify = True
        if config.configuration["aggregator"]["index-pipeline"]["use-ssl"]:
            self.pipeline_scheme = "https"
        if config.configuration["aggregator"]["index-pipeline"]["no-ssl-verify"]:
            self.pipeline_ssl_verify = False
        self.pipeline_host = config.configuration["aggregator"]["index-pipeline"]["host"]
        self.pipeline_port = config.configuration["aggregator"]["index-pipeline"]["port"]

        self.searx_url = (
            "http://"
            + self.config.configuration["aggregator"]["host"]
            + ":"
            + str(self.config.configuration["aggregator"]["port"])
            + "/search?format=json"
            + "&engines="
            + ",".join(self.config.configuration["aggregator"]["engines"])
        )
        ThotLogger.info("Searx URL:" + self.searx_url, context=call_context)
        self.thread_results = dict()
        self.result_lock = threading.Lock()

        self.index_name = "text-index"
        if "document-index-name" in config.configuration:
            self.index_name = config.configuration["document-index-name"]
        (self.es_url, self.es_verify_certs) = get_elastic_url(config.configuration["elasticsearch"])

    def third_party_search(self, query, pageno=1, call_context=None):
        searchid = generate_id("search")
        self.thread_results[searchid] = {"thread": None, "results": {}}
        self.thread_results[searchid]["thread"] = threading.Thread(
            target=run_search_request,
            args=(
                searchid,
                self,
                query,
                pageno,
                call_context,
            ),
        )
        self.thread_results[searchid]["thread"].start()
        return searchid

    def aggregate_results(self, searchid, tkeir_resuls):
        if searchid in self.thread_results:
            self.result_lock.acquire()
            results = deepcopy(self.thread_results[searchid])
            self.result_lock.release()
        return tkeir_resuls

    def index_results(self, results, call_context=None):
        if results:
            try:
                upload_req = {"action": "start"}
                r = requests.post(
                    self.pipeline_scheme + "://" + self.pipeline_host + ":" + str(self.pipeline_port) + "/api/pipeline/run",
                    json=upload_req,
                    verify=self.pipeline_ssl_verify,
                )
                for result in results:
                    perform_indexing = True
                    try:
                        r = requests.get(
                            self.es_url + "/" + self.index_name + '/_search?q=source_doc_id:"' + result["url"] + '"',
                            headers={"Content-Type": "application/json"},
                            verify=False,
                        )
                        es_search = json.loads(r.text)
                        if ("hits" in es_search) and ("hits" in es_search["hits"]):
                            perform_indexing = len(es_search["hits"]["hits"]) == 0
                    except Exception as e:
                        ThotLogger.warning(
                            "Cannot connect to Opendistro : " + self.es_url + "/" + self.index_name,
                            trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
                            context=call_context,
                        )
                    if perform_indexing:
                        content = base64.b64encode(bytes(result["url"], "utf-8")).decode()
                        json_request = {"datatype": "uri", "source": result["url"], "data": content}
                        try:
                            ThotLogger.info("Index source:" + result["url"])
                            r = requests.post(
                                self.pipeline_scheme
                                + "://"
                                + self.pipeline_host
                                + ":"
                                + str(self.pipeline_port)
                                + "/api/pipeline/run",
                                json=json_request,
                                verify=self.pipeline_ssl_verify,
                            )
                            if r.status_code != 200:
                                ThotLogger.warning(
                                    "Request return bad status:"
                                    + self.pipeline_scheme
                                    + "://"
                                    + self.pipeline_host
                                    + ":"
                                    + str(self.pipeline_port)
                                )
                                ThotLogger.warning(r.text)
                        except Exception as e:
                            ThotLogger.warning(
                                "Cannot connect to Pipeline:"
                                + self.pipeline_scheme
                                + "://"
                                + self.pipeline_host
                                + ":"
                                + str(self.pipeline_port)
                            )
                    else:
                        ThotLogger.info("'" + result["url"] + "' already indexed", context=call_context)
            except Exception as e:
                ThotLogger.warning(
                    "Exception occured during run to pipeline.",
                    trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
                    context=call_context,
                )
            upload_req = {"action": "finish"}
            r = requests.post(
                self.pipeline_scheme + "://" + self.pipeline_host + ":" + str(self.pipeline_port) + "/api/pipeline/run",
                json=upload_req,
                verify=self.pipeline_ssl_verify,
            )

    def wait_results(self, searchid):
        if (searchid in self.thread_results) and (self.thread_results[searchid]["thread"]):
            self.thread_results[searchid]["thread"].join()
        else:
            ThotLogger.warning("######################## Something wrong appears " + str(searchid in self.thread_results))

    def remove_results(self, searchid):
        if searchid in self.thread_results:
            self.result_lock.acquire()
            del self.thread_results[searchid]
            self.result_lock.release()
