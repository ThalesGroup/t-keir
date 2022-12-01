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
from thot.tasks.searching.TermVectors import TermVectors
from thot.tasks.searching.Scorer import Scorer
from thot.tasks.searching.TextQueryFormulator import TextQueryFormulator
from thot.tasks.searching.QueryExpansion import QueryExpansion

from elasticsearch import Elasticsearch, RequestsHttpConnection


class SearchingWithStructure:
    def __init__(self, searching):
        self._searching = searching

    def custom_structured_query(self, doc, observmode=False, call_context=None):
        scoring_strategy = {
            "normalize-score": True,
            "document-query-intersection-penalty": Scorer.SCORE_MAPPING["by-query-size"],
            "run-clause-separately": False,
            "expand-results": 50,
        }
        q_from = 0
        q_size = 10
        if "from" in doc:
            q_from = doc["from"]
        if "size" in doc:
            q_size = doc["size"]

        if "request" not in doc:
            raise ValueError("Request is mandatory")

        if "output" not in doc:
            raise ValueError("Output is mandatory")

        excludes = []
        if (
            "results" in self._searching.config.configuration["search-policy"]["settings"]
        ) and "excludes" in self._searching.config.configuration["search-policy"]["settings"]["results"]:
            excludes = self._searching.config.configuration["search-policy"]["settings"]["results"]["excludes"]

        qe_size = q_size

        if "scoring" not in self._searching.config.configuration["search-policy"]["settings"]:
            self._searching.config.configuration["search-policy"]["settings"]["scoring"] = {
                "normalize-score": True,
                "document-query-intersection-penalty": "by-query-size",
                "run-clause-separately": False,
                "expand-results": 50,
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

        clauses = []
        request_value = ""
        kg_request = ""
        expand_values = []
        # request & request expansion
        for clause in doc["request"]:
            if clause["key"] == "content":
                request_value = request_value + " " + clause["value"]

        for clause in doc["request"]:
            if clause["key"] == "content":
                clauses.append({"match": {"content": request_value}})
            if clause["key"] == "request_expansion_by_document":
                qe = QueryExpansion(
                    {
                        "index": self._searching._index_name,
                        "es-url": self._searching.es_url,
                        "es-verify": self._searching.es_verify_certs,
                        "keep_word_collection_thresold_under": 0.4,
                        "word_boost_thresold_above": 0.25,
                    }
                )
                es_ids = []
                if isinstance(clause["value"], str):
                    if "," in clause["value"]:
                        clause["value"] = clause["value"].split(",")
                    if "|" in clause["value"]:
                        clause["value"] = clause["value"].split("|")
                for c_i in range(len(clause["value"])):
                    clause["value"][c_i] = clause["value"][c_i].strip()
                for lid in clause["value"]:
                    docids = qe.getDocIdsWithRequest(
                        {"query": {"nested": {"path": "kg.subject", "query": {"match": {"kg.subject.content": lid}}}}},
                        call_context=call_context,
                    )
                    es_ids = es_ids + docids
                    if es_ids:
                        expand_values = qe.expandWithDocId({"content": request_value, "title": request_value}, es_ids)
                        for field in expand_values:
                            for word in expand_values[field]:
                                clauses.append(
                                    {"match_phrase": {field: {"query": word[0], "boost": word[1], "analyzer": "std_stop"}}}
                                )
            if clause["key"] == "kg":
                nested_clauses = []
                for triple in ["subject", "property", "value"]:
                    if triple in clause["value"]:
                        nested_clauses.append(
                            {
                                "nested": {
                                    "path": "kg." + triple,
                                    "query": {"match": {"kg." + triple + ".content": clause["value"][triple]}},
                                }
                            }
                        )
                        if triple == "subject":
                            kg_request = kg_request + " " + clause["value"][triple]
                if nested_clauses:
                    clauses.append({"nested": {"path": "kg", "query": {"bool": {"must": nested_clauses}}}})

        tkeir_doc = self._searching._analyzeDocument(request_value)

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

        (generated_clauses, big_query_texts) = tqf.generateQuery(
            query_type, self._searching.config.configuration["search-policy"]["settings"]["advanced-querying"]
        )
        ThotLogger.info("Additional clauses:" + str(len(generated_clauses)), context=call_context)

        query = {
            "from": int(q_from),
            "size": int(q_size),
            "_source": {"excludes": excludes},
            "query": {"bool": {"should": clauses + generated_clauses}},
        }
        es_search = None
        if not request_value:
            request_value = kg_request
        self._searching._last_query = query
        if self._searching.es_url:
            r = requests.post(
                self._searching.es_url + "/" + self._searching._index_name + "/_search",
                headers={"Content-Type": "application/json"},
                data=json.dumps(query),
                timeout=(600, 600),
                verify=self._searching.es_verify_certs,
            )
            es_search = json.loads(r.text)
        else:
            ThotLogger.error("Cannot get ES URL.")

        results_items = []
        if es_search and ("hits" in es_search) and ("hits" in es_search["hits"]):
            hits = es_search["hits"]["hits"]
            max_score = es_search["hits"]["max_score"]
            if max_score == 0:
                max_score = 1
            qtv = None
            if (scoring_strategy["document-query-intersection-penalty"] >= 0) or observmode:
                tv = TermVectors(
                    {
                        "index": self._searching._index_name,
                        "es-url": self._searching.es_url,
                        "es-verify": self._searching.es_verify_certs,
                    }
                )
                qtv = tv.query2TermVector({"title": request_value, "content": request_value})
            for hi in hits:
                tkeir_item = hi["_source"]
                result_item = {
                    "title": "",
                    "content": "",
                    "keywords": "",
                    "author": "",
                    "abstract": "",
                    "id": "",
                    "publicationDate": "",
                    "priorityDate": "",
                    "organization": "",
                    "rank": 0.0,
                    "cluster": -1,
                    "ipc": "",
                    "cpc": "",
                    "concepts": [],
                }
                hash_concepts = set()
                search_score = hi["_score"]
                norm_score = 1.0
                if scoring_strategy["normalize-score"]:
                    search_score = search_score / max_score
                if (scoring_strategy["document-query-intersection-penalty"] >= 0) or observmode:
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
                result_item["rank"] = int(100 * search_score * norm_score)
                if "title" in tkeir_item:
                    result_item["title"] = tkeir_item["title"]
                if "content" in tkeir_item:
                    result_item["content"] = tkeir_item["content"]
                if "kg" in tkeir_item:
                    for kg_item in tkeir_item["kg"]:
                        if kg_item["value"]["content"] == "keyword":
                            result_item["keywords"] = result_item["keywords"] + "|" + kg_item["subject"]["content"]
                        if kg_item["value"]["content"] == "inventors":
                            result_item["author"] = result_item["author"] + "|" + kg_item["subject"]["content"]
                        if kg_item["value"]["content"] == "current-assignee":
                            result_item["organization"] = result_item["organization"] + "|" + kg_item["subject"]["content"]
                        if kg_item["value"]["content"] == "abstract":
                            result_item["abstract"] = result_item["abstract"] + kg_item["subject"]["content"]
                        if kg_item["value"]["content"] == "independent-claims":
                            result_item["abstract"] = result_item["abstract"] + kg_item["subject"]["content"]
                        if kg_item["value"]["content"] == "claims":
                            result_item["abstract"] = result_item["abstract"] + kg_item["subject"]["content"]
                        if kg_item["value"]["content"] == "publication-number":
                            result_item["id"] = result_item["id"] + kg_item["subject"]["content"]
                        if kg_item["value"]["content"] == "publication-date":
                            result_item["publicationDate"] = result_item["publicationDate"] + kg_item["subject"]["content"]
                        if kg_item["value"]["content"] == "priority-date":
                            result_item["priorityDate"] = result_item["priorityDate"] + kg_item["subject"]["content"]
                        if kg_item["value"]["content"] == "cpc":
                            if kg_item["subject"]["content"]:
                                result_item["cpc"] = kg_item["subject"]["content"]
                        if kg_item["value"]["content"] == "ipc":
                            if kg_item["subject"]["content"]:
                                result_item["ipc"] = kg_item["subject"]["content"]
                        if kg_item["value"]["content"] == "original-document":
                            if kg_item["subject"]["content"]:
                                result_item["url"] = kg_item["subject"]["content"]
                        """ TODO : restore when HMI OK
                        if kg_item["property"]["content"]=="rel:has-concept":
                            if kg_item["subject"]["content"] and kg_item["value"]["content"]:
                                hash_key = kg_item["subject"]["content"] + "#" + kg_item["value"]["content"]
                                if hash_key not in hash_concepts:
                                    result_item["concepts"].append({
                                        "name":kg_item["subject"]["content"],
                                        "parent":kg_item["value"]["content"]
                                    })
                                    hash_concepts.add(hash_key)
                        """

                result_item["keywords"].replace("|", "", 1)
                result_item["author"].replace("|", "", 1)
                if observmode:
                    result_item["doc_tv"] = doctv
                results_items.append(result_item)
        results_items = sorted(results_items, key=lambda x: x["rank"], reverse=True)
        if observmode:
            return {"items": results_items, "query": qtv}
        return results_items
