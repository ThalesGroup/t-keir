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
from copy import deepcopy


from thot.core.ThotLogger import ThotLogger
from thot.core.Constants import exception_error_and_trace
from thot.tasks.searching.TermVectors import TermVectors
from thot.tasks.searching.Scorer import Scorer
from thot.tasks.searching.TextQueryFormulator import TextQueryFormulator
from thot.tasks.searching.QueryExpansion import QueryExpansion

from elasticsearch import Elasticsearch, RequestsHttpConnection


class SearchingWithSentence:
    def __init__(self, searching):
        self._searching = searching
        self.query_expansion = None
        self.query_expansion_size = 0
        self.named_entity_explain = False
        self.named_entity_min_score = 0.5
        self.named_entity_max_query = 5
        if "see-also" in self._searching.config.configuration["search-policy"]["settings"]["results"]:
            self.query_expansion = QueryExpansion(
                {
                    "index": self._searching._index_name,
                    "es-url": self._searching.es_url,
                    "es-verify": self._searching.es_verify_certs,
                    "keep_word_collection_thresold_under": 0.4,
                    "word_boost_thresold_above": 0.25,
                }
            )
            self.query_expansion_size = self._searching.config.configuration["search-policy"]["settings"]["results"][
                "see-also"
            ]["number-of-cross-links"]
        self.scoring_strategy = deepcopy(self._searching.config.configuration["search-policy"]["settings"]["scoring"])
        if "named-entity-explain" in self._searching.config.configuration["search-policy"]["settings"]["results"]:
            self.named_entity_explain = True
            if (
                "min-score"
                in self._searching.config.configuration["search-policy"]["settings"]["results"]["named-entity-explain"]
            ):
                self.named_entity_min_score = self._searching.config.configuration["search-policy"]["settings"]["results"][
                    "named-entity-explain"
                ]["min-score"]
            if (
                "max-query"
                in self._searching.config.configuration["search-policy"]["settings"]["results"]["named-entity-explain"]
            ):
                self.named_entity_max_query = self._searching.config.configuration["search-policy"]["settings"]["results"][
                    "named-entity-explain"
                ]["max-query"]
        if "document-query-intersection-penalty" in self.scoring_strategy:
            if self.scoring_strategy["document-query-intersection-penalty"] in Scorer.SCORE_MAPPING:
                int_penalty = Scorer.SCORE_MAPPING[self.scoring_strategy["document-query-intersection-penalty"]]
                self.scoring_strategy["document-query-intersection-penalty"] = int_penalty
            else:
                self.scoring_strategy["document-query-intersection-penalty"] = -1
        else:
            self.scoring_strategy["document-query-intersection-penalty"] = -1

    def queryAnalysis(self, doc):
        pass

    def append_clause(self, query, clause_type, added_clause):
        query["query"] = {"bool": {clause_type: [added_clause, query["query"]]}}
        return query

    def queryOptions(self, doc):
        excludes = []
        enable_feature = {"qa": True, "aggregator": True}
        if "options" in doc:
            if "disable" in doc["options"]:
                for feature in doc["options"]["disable"]:
                    if feature in enable_feature:
                        enable_feature[feature] = False
                    else:
                        ThotLogger.warning("Feature '" + str(feature) + "' does not exists.")
            if "exclude" in doc["options"]:
                excludes = doc["options"]["exclude"]
        if (
            "results" in self._searching.config.configuration["search-policy"]["settings"]
        ) and "excludes" in self._searching.config.configuration["search-policy"]["settings"]["results"]:
            excludes = excludes + self._searching.config.configuration["search-policy"]["settings"]["results"]["excludes"]
            excludes = list(set(excludes))
        return (excludes, enable_feature)

    def configureQuery(self, doc, excludes, q_from, qe_size):
        eval_basic_clause = []
        eval_advanced_clause = []
        queries = []
        text_query = []
        tqf = TextQueryFormulator()
        query_type = []
        try:
            tkeir_doc = self._searching._analyzeDocument(doc["content"])
        except Exception as analyze_exc:
            ThotLogger.warning("Query Analysis error" + str(analyze_exc))
            tkeir_doc = None

        clause_type = None
        added_clause = None
        if "add-clause" in doc:
            clause_type = "must"
            if "type" in doc["add-clause"]:
                clause_type = doc["add-clause"]["type"]
            if "clause" in doc["add-clause"]:
                added_clause = doc["add-clause"]["clause"]

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

        if (not self._searching.config.configuration["disable-document-analysis"]) and tkeir_doc:
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

        if self.scoring_strategy["run-clause-separately"] and (len(eval_advanced_clause) > 0):
            qclauses = eval_basic_clause + eval_advanced_clause
            for qti in qclauses:
                (partial_q, partial_text) = tqf.generateQuery(
                    [query_type[qti]], self._searching.config.configuration["search-policy"]["settings"]["advanced-querying"]
                )
                query = {
                    "_source": {"excludes": excludes},
                    "from": int(q_from),
                    "size": int(qe_size),
                    "query": {"bool": {"should": partial_q}},
                }
                if clause_type and added_clause:
                    query = self.append_clause(query, clause_type, added_clause)
                queries.append(query)
                text_query.append(partial_text)
        else:
            query = {
                "_source": {"excludes": excludes},
                "from": int(q_from),
                "size": int(qe_size),
                "query": {"bool": {"should": clauses}},
            }
            if clause_type and added_clause:
                query = self.append_clause(query, clause_type, added_clause)
            queries.append(query)
        text_query.append(big_query_texts)
        return (tkeir_doc, text_query, queries)

    def intersectGraph(self, kg1, kg2):
        kg1_hash = set()
        kg2_hash = set()
        kg_map = dict()
        for ki in kg1:
            k = str(ki["subject"]["content"]) + "#" + str(ki["property"]["content"]) + "#" + str(ki["value"]["content"])
            kg1_hash.add(k)
            kg_map[k] = {
                "subject": ki["subject"]["content"],
                "property": ki["property"]["content"],
                "value": ki["value"]["content"],
            }
        for ki in kg2:
            k = str(ki["subject"]["content"]) + "#" + str(ki["property"]["content"]) + "#" + str(ki["value"]["content"])
            kg2_hash.add(k)
        kgi = kg1_hash.intersection(kg2_hash)
        kg = []
        for k in kgi:
            kg.append(kg_map[k])
        return kg

    def querying_with_sentence(self, doc, call_context=None):
        """Querying with sentence

        Args:
            doc ([type]): json structure[doc==content, from, size,add-clause={"type":"must|should","clause":"es-query"}, options:{disable:["qa","aggregator"], "exclude":["summary","sentiment","categories","text_suggester","lemma_title","lemma_content"]}]

        Returns:
            [list]: ranked list
        """

        # Run third party as quick as possible

        if "from" not in doc:
            doc["from"] = 0
        if "size" not in doc:
            doc["size"] = 10
        q_from = int(doc["from"])
        q_size = int(doc["size"])
        qe_size = q_size
        ThotLogger.info(
            "Search from :" + str(q_from) + ", size " + str(q_size) + " query:" + doc["content"][0:200], context=call_context
        )

        (excludes, enable_feature) = self.queryOptions(doc)
        (tkeir_doc, text_query, queries) = self.configureQuery(doc, excludes, q_from, qe_size)

        if self._searching.aggregator:
            ThotLogger.info("Run aggregator", context=call_context)
            self._searching.aggregator.third_party_search(doc["content"], pageno=1 + q_from / q_size, call_context=call_context)
            ThotLogger.info("Aggregator in bg.", context=call_context)

        if self.scoring_strategy["expand-results"] > 0:
            qe_size = qe_size + self.scoring_strategy["expand-results"]

        self._searching.initQA(self._searching.config)

        es_search = None
        query_id_score = dict()
        partial_query_id = 0
        see_also_graph = {}
        for query in queries:
            self._searching._last_query = query
            if self._searching.es_url:
                try:
                    r = requests.post(
                        self._searching.es_url + "/" + self._searching._index_name + "/_search",
                        verify=self._searching.es_verify_certs,
                        headers={"Content-Type": "application/json"},
                        data=json.dumps(query),
                        timeout=(600, 600),
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

            if es_search and ("hits" in es_search) and ("hits" in es_search["hits"]):
                tv = TermVectors(
                    {
                        "index": self._searching._index_name,
                        "es-url": self._searching.es_url,
                        "es-verify": self._searching.es_verify_certs,
                    }
                )
                hits = es_search["hits"]["hits"]
                max_score = es_search["hits"]["max_score"]
                qtv = None
                if self.scoring_strategy["document-query-intersection-penalty"] >= 0:
                    qtv = tv.query2TermVector({"content": " ".join(list(text_query[partial_query_id]))})
                items = []
                hit_idx = 0
                min_sa_score = 10000000
                max_sa_score = 0
                for hi in hits:
                    tkeir_item = hi["_source"]
                    if "highlight" not in hi:
                        hi["highlight"] = []
                    search_score = hi["_score"]
                    norm_score = 1.0
                    if self.scoring_strategy["normalize-score"]:
                        search_score = search_score / max_score
                    if self.scoring_strategy["document-query-intersection-penalty"] >= 0:
                        doctv = tv.docId2TermVector(hi["_id"], ["title", "content"])
                        norm_score = Scorer.documentQueryIntersectionScore(
                            query=qtv, document=doctv, normalize=self.scoring_strategy["document-query-intersection-penalty"]
                        )
                    if hi["_id"] not in query_id_score:
                        short_answers = []
                        if self._searching.qa_host and (hit_idx < self._searching.qamaxdoc) and enable_feature["qa"]:
                            texts = tkeir_item["title"] + tkeir_item["content"]
                            try:
                                r = requests.post(
                                    self._searching.qa_host + "/api/qa/run_by_sentences",
                                    headers={"Content-Type": "application/json"},
                                    data=json.dumps({"query": doc["content"], "texts": texts}),
                                    verify=self._searching.qa_ssl_verify,
                                )
                                if r.status_code == 200:
                                    short_answers = r.json()["results"]
                            except Exception as qa_ex:
                                ThotLogger.warning("Error :" + str(qa_ex) + ", trace" + str(traceback.format_exc()))
                            if self.named_entity_explain:
                                qlist = []
                                queries_set = set()

                                for ki in hi["_source"]["kg"]:
                                    current_query = None
                                    if ("instanceof" in ki["property"]["content"]) and ("person" in ki["value"]["content"]):
                                        current_query = {
                                            "e": ki["subject"]["content"],
                                            "q": "Who is " + ki["subject"]["content"] + " ?",
                                            "type": "rel:person-explain-as",
                                        }
                                    if ("instanceof" in ki["property"]["content"]) and (
                                        "organisation" in ki["value"]["content"]
                                    ):
                                        current_query = {
                                            "e": ki["subject"]["content"],
                                            "q": "What is " + ki["subject"]["content"] + " ?",
                                            "type": "rel:organisation-explain-as",
                                        }
                                    if ("instanceof" in ki["property"]["content"]) and (
                                        ("date" in ki["value"]["content"]) or ("time" in ki["value"]["content"])
                                    ):
                                        current_query = {
                                            "e": ki["subject"]["content"],
                                            "q": "What does happen the " + ki["subject"]["content"] + " ?",
                                            "type": "rel:event-explain-as",
                                        }
                                    if ("instanceof" in ki["property"]["content"]) and ("location" in ki["value"]["content"]):
                                        current_query = {
                                            "e": ki["subject"]["content"],
                                            "q": "What is located at " + ki["subject"]["content"] + " ?",
                                            "type": "rel:location-explain-as",
                                        }
                                    if current_query and (current_query["q"] not in queries_set):
                                        qlist.append(current_query)
                                        queries_set.add(current_query["q"])
                                if qlist and (self.named_entity_max_query > 0):
                                    qlist = qlist[0 : self.named_entity_max_query]
                                for q_ent_i in qlist:
                                    r = requests.post(
                                        self._searching.qa_host + "/api/qa/run_by_sentences",
                                        headers={"Content-Type": "application/json"},
                                        data=json.dumps({"query": q_ent_i["q"], "texts": texts}),
                                        verify=self._searching.qa_ssl_verify,
                                    )
                                    if r.status_code == 200:
                                        if r.json()["results"]["doc"]["score"] > self.named_entity_min_score:
                                            hi["_source"]["kg"].append(
                                                {
                                                    "subject": {
                                                        "content": q_ent_i["e"],
                                                        "lemma_content": "",
                                                        "label": "explain",
                                                        "class": -1,
                                                        "positions": [-1],
                                                    },
                                                    "property": {
                                                        "content": q_ent_i["type"],
                                                        "lemma_content": "",
                                                        "label": "explain",
                                                        "class": -1,
                                                        "positions": [-1],
                                                    },
                                                    "value": {
                                                        "content": r.json()["results"]["doc"]["answer"],
                                                        "lemma_content": "",
                                                        "label": "explain",
                                                        "class": -1,
                                                        "positions": [-1],
                                                    },
                                                }
                                            )

                        if self.query_expansion:
                            expand_values = self.query_expansion.expandWithDocId(
                                {"content": doc["content"], "title": doc["content"]}, [hi["_id"]]
                            )
                            e_clauses = []
                            for field in expand_values:
                                for word in expand_values[field]:
                                    e_clauses.append(
                                        {"match_phrase": {field: {"query": word[0], "boost": word[1], "analyzer": "std_stop"}}}
                                    )
                            e_clauses.append(query["query"])
                            e_query = {
                                "_source": {"excludes": ["lemma_content", "lemma_title"]},
                                "from": 0,
                                "size": self.query_expansion_size,
                                "query": {"bool": {"should": e_clauses}},
                            }
                            try:
                                if hi["_id"] not in see_also_graph:
                                    see_also_graph[hi["_id"]] = {
                                        "title": hi["_source"]["title"],
                                        "url": hi["_source"]["source_doc_id"],
                                        "count": 0,
                                        "close": {},
                                    }
                                see_also_graph[hi["_id"]]["count"] = see_also_graph[hi["_id"]]["count"] + 1
                                r_e = requests.post(
                                    self._searching.es_url + "/" + self._searching._index_name + "/_search",
                                    verify=self._searching.es_verify_certs,
                                    headers={"Content-Type": "application/json"},
                                    data=json.dumps(e_query),
                                    timeout=(600, 600),
                                )
                                e_es_search = json.loads(r_e.text)
                                if ("hits" in e_es_search) and ("hits" in e_es_search["hits"]):
                                    ehits = e_es_search["hits"]["hits"]
                                    for ehit in ehits:
                                        if ehit["_id"] != hi["_id"]:
                                            if ehit["_id"] not in see_also_graph:
                                                see_also_graph[ehit["_id"]] = {
                                                    "title": ehit["_source"]["title"],
                                                    "url": ehit["_source"]["source_doc_id"],
                                                    "count": 0,
                                                    "close": {},
                                                }
                                            see_also_graph[ehit["_id"]]["count"] = see_also_graph[ehit["_id"]]["count"] + 1
                                            if ehit["_id"] not in see_also_graph[hi["_id"]]["close"]:
                                                close_item = {"score": 0, "kg": [], "title": ehit["_id"], "summary": []}
                                                if ehit["_source"]["title"]:
                                                    close_item["title"] = ehit["_source"]["title"]
                                                    close_item["url"] = ehit["_source"]["source_doc_id"]
                                                    if ehit["_source"]["summary"]:
                                                        close_item["summary"] = ehit["_source"]["summary"]
                                                    else:
                                                        close_item["summary"] = ehit["_source"]["content"]
                                                see_also_graph[hi["_id"]]["close"][ehit["_id"]] = close_item
                                                if (
                                                    ("kg" in see_also_graph[hi["_id"]]["close"][ehit["_id"]])
                                                    and ("kg" in hi["_source"])
                                                    and ("kg" in ehit["_source"])
                                                ):
                                                    see_also_graph[hi["_id"]]["close"][ehit["_id"]]["kg"] = self.intersectGraph(
                                                        hi["_source"]["kg"], ehit["_source"]["kg"]
                                                    )
                                            see_also_graph[hi["_id"]]["close"][ehit["_id"]]["score"] = (
                                                see_also_graph[hi["_id"]]["close"][ehit["_id"]]["score"] + ehit["_score"]
                                            )
                                            if min_sa_score > see_also_graph[hi["_id"]]["close"][ehit["_id"]]["score"]:
                                                min_sa_score = see_also_graph[hi["_id"]]["close"][ehit["_id"]]["score"]
                                            if max_sa_score < see_also_graph[hi["_id"]]["close"][ehit["_id"]]["score"]:
                                                max_sa_score = see_also_graph[hi["_id"]]["close"][ehit["_id"]]["score"]

                            except Exception as e:
                                ThotLogger.error(
                                    "Exception occured.",
                                    trace=exception_error_and_trace(str(e), str(traceback.format_exc())),
                                    context=call_context,
                                )

                        human_readable_score = search_score * norm_score
                        query_id_score[hi["_id"]] = {
                            "_source": tkeir_item,
                            "index-name": self._searching._index_name,
                            "short-answers": short_answers,
                            "_score": human_readable_score,
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
        es_answer["query"] = []
        es_answer["see-also"] = []
        if "query" not in excludes:
            es_answer["query"] = query
        if "see-also" not in excludes:
            for k in see_also_graph:
                for dk in see_also_graph[k]["close"]:
                    if min_sa_score and max_sa_score and (min_sa_score != max_sa_score):
                        see_also_graph[k]["close"][dk]["score"] = (see_also_graph[k]["close"][dk]["score"] - min_sa_score) / (
                            max_sa_score - min_sa_score
                        )
            es_answer["see-also"] = see_also_graph

        items = list(map(lambda x: x[1], sorted(query_id_score.items(), key=lambda k: k[1]["_score"], reverse=True)))

        es_answer["total_docs"] = min([q_size, len(items)])
        es_answer["items"] = items[0:q_size]
        if len(items) > 0:
            es_answer["max_score"] = items[0]["_score"]
        return es_answer
