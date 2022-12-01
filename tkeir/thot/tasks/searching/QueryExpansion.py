# -*- coding: utf-8 -*-
"""Query expansion
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""


import requests
import json
import traceback
from thot.core.Utils import is_numeric
from thot.core.ThotLogger import ThotLogger
from thot.core.Constants import exception_error_and_trace
from thot.tasks.searching.TermVectors import TermVectors


class QueryExpansion:
    def __init__(self, config):
        self._es_url = config["es-url"]
        self._es_verify = config["es-verify"]
        self._index_name = config["index"]
        self._keep_word_collection_thresold_under = config["keep_word_collection_thresold_under"]
        self._word_boost_thresold_above = config["word_boost_thresold_above"]
        self._termvectors = TermVectors({"es-url": self._es_url, "es-verify": self._es_verify, "index": self._index_name})

    def _docId2TermVector(self, docid: str, fields: list):
        return self._termvectors.docId2TermVector(docid, fields)

    def _query2TermVector(self, query: dict):
        return self._termvectors.query2TermVector(query)

    def expandWithDocId(self, query: dict, docids: list, prune_term=128, clean_number=True):
        # get all term vectors
        doc_termvectors = []
        for docid in docids:
            doc_termvectors.append(self._docId2TermVector(docid, ["content", "title"]))
        q_termvector = self._query2TermVector(query)
        return self.expandWithTermVector(q_termvector, doc_termvectors, prune_term=prune_term, clean_number=clean_number)

    def expandWithTermVector(self, q_termvector: dict, doc_termvectors: list, prune_term=128, clean_number=True):
        doc_fields = dict()
        for doc in doc_termvectors:
            for field in doc["term_vectors"]:
                field_stat = doc["term_vectors"][field]["field_statistics"]
                if field not in doc_fields:
                    doc_fields[field] = dict()
                for term in doc["term_vectors"][field]["terms"]:
                    if "doc_freq" in doc["term_vectors"][field]["terms"][term]:
                        doc_stat = doc["term_vectors"][field]["terms"][term]["doc_freq"] / field_stat["doc_count"]
                        if (doc_stat < self._keep_word_collection_thresold_under) and (
                            doc["term_vectors"][field]["terms"][term]["doc_freq"] > 1
                        ):
                            if "term_freq" in doc["term_vectors"][field]["terms"][term]:
                                word_boost_stat = (
                                    doc["term_vectors"][field]["terms"][term]["term_freq"]
                                    / doc["term_vectors"][field]["terms"][term]["ttf"]
                                )
                                if word_boost_stat > self._word_boost_thresold_above:
                                    if term not in doc_fields[field]:
                                        doc_fields[field][term] = []
                                    doc_fields[field][term].append(word_boost_stat)

        for field in q_termvector["term_vectors"]:
            field_stat = q_termvector["term_vectors"][field]["field_statistics"]
            if field not in doc_fields:
                doc_fields[field] = dict()
            term_count = dict()
            sum_count = 0.0
            for term in q_termvector["term_vectors"][field]["terms"]:
                if "doc_freq" in q_termvector["term_vectors"][field]["terms"][term]:
                    doc_stat = q_termvector["term_vectors"][field]["terms"][term]["doc_freq"] / field_stat["doc_count"]
                    if doc_stat < self._keep_word_collection_thresold_under:
                        if "term_freq" in q_termvector["term_vectors"][field]["terms"][term]:
                            word_boost_stat = (
                                q_termvector["term_vectors"][field]["terms"][term]["term_freq"]
                                / q_termvector["term_vectors"][field]["terms"][term]["ttf"]
                            )
                            term_count[term] = q_termvector["term_vectors"][field]["terms"][term]["term_freq"]
                            sum_count = sum_count + q_termvector["term_vectors"][field]["terms"][term]["term_freq"]
            for term in term_count:
                if clean_number and is_numeric(term):
                    continue
                if sum_count > 0:
                    term_q_boost = term_count[term] / sum_count
                    if term_q_boost > self._word_boost_thresold_above:
                        if term not in doc_fields[field]:
                            doc_fields[field][term] = []
                        doc_fields[field][term].append(1.0 + term_q_boost)

        for field in doc_fields:
            for term in doc_fields[field]:
                l = len(doc_fields[field][term])
                doc_fields[field][term] = sum(doc_fields[field][term]) / l
            doc_fields[field] = sorted(doc_fields[field].items(), key=lambda x: x[1], reverse=True)
            if prune_term > 0:
                doc_fields[field] = doc_fields[field][0:prune_term]
            for k in range(len(doc_fields[field])):
                norm_score = doc_fields[field][k][1] / doc_fields[field][-1][1]
                doc_fields[field][k] = (doc_fields[field][k][0], norm_score)
        return doc_fields

    def getDocIdsWithRequest(self, query: dict, call_context=None):
        docids = []
        try:
            q_url = self._es_url + "/" + self._index_name + "/_search"
            r = requests.get(
                q_url,
                verify=self._es_verify,
                data=json.dumps(query),
                headers={"Content-Type": "application/json"},
                timeout=(600, 600),
            )
            es_search = json.loads(r.text)
            if es_search and ("hits" in es_search) and ("hits" in es_search["hits"]):
                hits = es_search["hits"]["hits"]
            for hi in hits:
                docids.append(hi["_id"])
        except Exception as e:
            ThotLogger.error(
                "Exception occured.", trace=exception_error_and_trace(str(e), str(traceback.format_exc())), context=call_context
            )
        return docids
