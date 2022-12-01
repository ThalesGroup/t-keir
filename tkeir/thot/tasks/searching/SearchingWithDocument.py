# -*- coding: utf-8 -*-
"""Searching
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

from collections import namedtuple
import json
from os import SCHED_OTHER
import re
from sys import maxsize
import traceback
import numpy as np
import requests


from thot.core.ThotLogger import ThotLogger
from thot.core.Constants import exception_error_and_trace
from thot.tasks.searching.TermVectors import TermVectors
from thot.tasks.searching.Scorer import Scorer
from thot.tasks.searching.TextQueryFormulator import TextQueryFormulator
from thot.tasks.searching.QueryExpansion import QueryExpansion

from elasticsearch import Elasticsearch, RequestsHttpConnection


class SearchingWithDocument:
    def __init__(self, searching):
        self._searching = searching

    def querying_with_doc(self, doc, call_context=None):
        tkeir_doc = self._searching._analyzeDocument(doc["content"])
        q_from = int(doc["from"])
        q_size = int(doc["size"])
        qe_size = q_size

        if "scoring" not in self._searching.config.configuration["search-policy"]["settings"]:
            self._searching.config.configuration["search-policy"]["settings"]["scoring"] = {
                "normalize-score": False,
                "document-query-intersection-penalty": "no-normalization",
                "run-clause-separately": False,
                "expand-results": 0,
            }

        scoring_strategy = self._searching.config.configuration["search-policy"]["settings"]["scoring"]
        if "document-query-intersection-penalty" in scoring_strategy:
            if scoring_strategy["document-query-intersection-penalty"] in Scorer.SCORE_MAPPING:
                int_penalty = Scorer.SCORE_MAPPING[scoring_strategy["document-query-intersection-penalty"]]
                scoring_strategy["document-query-intersection-penalty"] = int_penalty
            else:
                scoring_strategy["document-query-intersection-penalty"] = -1
        else:
            scoring_strategy["document-query-intersection-penalty"] = -1
        if scoring_strategy["expand-results"] > 0:
            qe_size = qe_size + scoring_strategy["expand-results"]

        tqf = TextQueryFormulator()
        query_type = []

        eval_basic_clause = []
        eval_advanced_clause = []

        if "basic-querying" in self._searching.config.configuration["search-policy"]["settings"]:
            eval_basic_clause.append(0)
            query_type.append(
                tqf.dummyContent(
                    tkeir_doc,
                    maxsize=self._searching.config.configuration["search-policy"]["settings"]["basic-querying"]["cut-query"],
                    uniqword=self._searching.config.configuration["search-policy"]["settings"]["basic-querying"][
                        "uniq-word-query"
                    ],
                    boost_uniqword=self._searching.config.configuration["search-policy"]["settings"]["basic-querying"][
                        "boosted-uniq-word-query"
                    ],
                )
            )
        if not self._searching.config.configuration["disable-document-analysis"]:
            if "advanced-querying" in self._searching.config.configuration["search-policy"]["settings"]:
                aq_config = self._searching.config.configuration["search-policy"]["settings"]["advanced-querying"]
                if ("use-keywords" in aq_config) and aq_config["use-keywords"]:
                    query_type.append(tqf.keywordsByScore(tkeir_doc))
                    eval_advanced_clause.append(len(query_type) - 1)
                if ("use-knowledge-graph" in aq_config) and aq_config["use-knowledge-graph"]:
                    query_type.append(tqf.svoByScore(tkeir_doc))
                    eval_advanced_clause.append(len(query_type) - 1)
                if ("use-semantic-keywords" in aq_config) and aq_config["use-semantic-keywords"]:
                    query_type.append(tqf.semanticKeywords(tkeir_doc, aq_config))
                    eval_advanced_clause.append(len(query_type) - 1)
                if ("use-semantic-knowledge-graph" in aq_config) and aq_config["use-semantic-knowledge-graph"]:
                    query_type.append(tqf.semanticSVO(tkeir_doc, aq_config))
                    eval_advanced_clause.append(len(query_type) - 1)
                if ("use-concepts" in aq_config) and aq_config["use-concepts"]:
                    query_type.append(tqf.concepts(tkeir_doc, aq_config))
                    eval_advanced_clause.append(len(query_type) - 1)
                if ("use-sentences" in aq_config) and aq_config["use-sentences"]:
                    query_type.append(tqf.sentencesByScore(tkeir_doc))
                    eval_advanced_clause.append(len(query_type) - 1)

        (clauses, big_query_texts) = tqf.generateQuery(
            query_type, self._searching.config.configuration["search-policy"]["settings"]["advanced-querying"]
        )

        queries = []
        text_query = []
        excludes = []
        if (
            "results" in self._searching.config.configuration["search-policy"]["settings"]
        ) and "excludes" in self._searching.config.configuration["search-policy"]["settings"]["results"]:
            excludes = self._searching.config.configuration["search-policy"]["settings"]["results"]["excludes"]

        if scoring_strategy["run-clause-separately"] and (len(eval_advanced_clause) > 0):
            ThotLogger.info("Add clause query")
            qclauses = eval_basic_clause + eval_advanced_clause
            for qti in qclauses:
                ThotLogger.info("\tAdd query type:" + str(qti))
                (partial_q, partial_text) = tqf.generateQuery(
                    [query_type[qti]], self._searching.config.configuration["search-policy"]["settings"]["advanced-querying"]
                )
                query = {
                    "_source": {"excludes": excludes},
                    "from": int(q_from),
                    "size": int(qe_size),
                    "query": {"bool": {"should": partial_q}},
                }
                queries.append(query)
                text_query.append(partial_text)
        else:
            query = {
                "_source": {"excludes": excludes},
                "from": int(q_from),
                "size": int(qe_size),
                "query": {"bool": {"should": clauses}},
            }
            queries.append(query)
        text_query.append(big_query_texts)
        es_search = None
        query_id_score = dict()
        partial_query_id = 0
        for query in queries:
            self._searching._last_query = query
            if self._searching.es_url:
                try:
                    r = requests.post(
                        self._searching.es_url + "/" + self._searching._index_name + "/_search",
                        headers={"Content-Type": "application/json"},
                        data=json.dumps(query),
                        timeout=(600, 600),
                        verify=self._searching.es_verify_certs,
                    )
                    es_search = json.loads(r.text)
                except Exception as e:
                    ThotLogger.error(
                        "Exception occured.",
                        trace=exception_error_and_trace(str(e), str(traceback.format_exc())),
                        context=call_context,
                    )

            else:
                ThotLogger.error("Cannot get ES URL.", context=call_context)

            es_answer = dict()
            es_answer["items"] = []
            es_answer["max_score"] = 1
            es_answer["total_docs"] = 0
            if ("hits" in es_search) and ("hits" in es_search["hits"]):
                hits = es_search["hits"]["hits"]
                max_score = es_search["hits"]["max_score"]
                qtv = None
                if scoring_strategy["document-query-intersection-penalty"] >= 0:
                    tv = TermVectors(
                        {
                            "index": self._searching._index_name,
                            "es-url": self._searching.es_url,
                            "es-verify": self._searching.es_verify_certs,
                        }
                    )
                    qtv = tv.query2TermVector({"content": " ".join(list(text_query[partial_query_id]))})
                items = []
                hit_idx = 0
                for hi in hits:
                    tkeir_item = hi["_source"]
                    if "highlight" not in hi:
                        hi["highlight"] = []
                    search_score = hi["_score"]
                    norm_score = 1.0
                    if scoring_strategy["normalize-score"]:
                        search_score = search_score / max_score
                    if scoring_strategy["document-query-intersection-penalty"] >= 0:
                        tv = TermVectors(
                            {
                                "index": self._searching._index_name,
                                "es-url": self._searching.es_url,
                                "es-verify": self._searching.es_verify_certs,
                            }
                        )
                        doctv = tv.docId2TermVector(hi["_id"], ["title", "content"])
                        norm_score = Scorer.documentQueryIntersectionScore(
                            query=qtv, document=doctv, normalize=scoring_strategy["document-query-intersection-penalty"]
                        )
                    if hi["_id"] not in query_id_score:
                        # ThotLogger.info("Normalize score:"+str(norm_score)+"["+str(search_score)+"], query length:"+str(len(text_query[partial_query_id])))
                        query_id_score[hi["_id"]] = {
                            "_source": tkeir_item,
                            "_score": search_score * norm_score,
                            "_index": hi["_index"],
                            "_id": hi["_id"],
                            "_type": hi["_type"],
                            "highlight": hi["highlight"],
                        }
                    else:
                        ThotLogger.info(
                            "Query ["
                            + str(partial_query_id)
                            + "] Hit ["
                            + str(hit_idx)
                            + "] Update score, boost '"
                            + str(hi["_id"])
                            + "' with "
                            + str(search_score * norm_score),
                            context=call_context,
                        )
                        query_id_score[hi["_id"]]["_score"] = query_id_score[hi["_id"]]["_score"] + search_score * norm_score
                    hit_idx = hit_idx + 1
            else:
                es_answer["es_error"] = es_search
            partial_query_id = partial_query_id + 1
        es_answer["query"] = query

        items = list(map(lambda x: x[1], sorted(query_id_score.items(), key=lambda k: k[1]["_score"], reverse=True)))
        es_answer["total_docs"] = min([q_size, len(items)])
        es_answer["items"] = items[0:q_size]
        if len(items) > 0:
            es_answer["max_score"] = items[0]["_score"]
        return es_answer
