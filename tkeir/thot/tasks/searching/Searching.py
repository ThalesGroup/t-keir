# -*- coding: utf-8 -*-
"""Searching
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

from collections import namedtuple
from faulthandler import is_enabled
import json
from os import SCHED_OTHER
import re
from sys import maxsize
import traceback
import numpy as np
import requests
from tkeir.thot.core.Utils import ThotTokenizerToSpacy, type_to_bool
from tkeir.thot.tasks.searching.Aggregator import Aggregator


from thot.tasks.searching.SearchingConfiguration import SearchingConfiguration
from thot.tasks.searching.TextQueryFormulator import TextQueryFormulator
from thot.tasks.searching.QueryExpansion import QueryExpansion
from thot.tasks.searching.Scorer import Scorer
from thot.tasks.searching.TermVectors import TermVectors
from thot.tasks.searching.Aggregator import Aggregator
from thot.tasks.searching.SearchingWithDocument import SearchingWithDocument
from thot.tasks.searching.SearchingWithSentence import SearchingWithSentence
from thot.tasks.searching.SearchingWithStructure import SearchingWithStructure
from thot.tasks.tokenizer.Tokenizer import Tokenizer
from thot.tasks.morphosyntax.MorphoSyntacticTagger import MorphoSyntacticTagger
from thot.tasks.ner.NERTagger import NERTagger
from thot.tasks.syntax.SyntacticTagger import SyntacticTagger
from thot.tasks.embeddings.Embeddings import Embeddings
from thot.tasks.relations.RelationsClusterizer import RelationsClusterizer
from thot.tasks.keywords.KeywordsExtractor import KeywordsExtractor
from thot.core.ThotLogger import ThotLogger
from thot.core.Constants import exception_error_and_trace
from thot.core.Utils import get_elastic_url

from elasticsearch import Elasticsearch, RequestsHttpConnection


class Searching:
    def initQA(self, config: SearchingConfiguration):
        if not self.qa_host:
            self.qa_host = None
            self.qa_ssl_verify = False
            self.aggregator = None
            self.qamaxdoc = 1
            is_enable = True
            if "qa" in config.configuration:
                if "enable" in config.configuration["qa"]:
                    is_enable = config.configuration["qa"]["enable"]
                if is_enable:
                    ThotLogger.info("Try to initialize QA sub system")
                    scheme = "http"
                    if ("use-ssl" in config.configuration["qa"]) and config.configuration["qa"]["use-ssl"]:
                        scheme = "https"
                    if "no-ssl-verify" in config.configuration["qa"]:
                        self.qa_ssl_verify = not config.configuration["qa"]["no-ssl-verify"]
                    self.qa_host = (
                        scheme + "://" + config.configuration["qa"]["host"] + ":" + str(config.configuration["qa"]["port"])
                    )
                    ThotLogger.info("Try to run on:" + self.qa_host)
                    try:
                        r = requests.get(self.qa_host + "/api/qa/health", verify=self.qa_ssl_verify)
                        if r.status_code != 200:
                            ThotLogger.warning("QA not available")
                            self.qa_host = None
                    except Exception as e_req:
                        ThotLogger.warning("QA not yet available." + str(e_req))
                    if "max-ranked-doc" in config.configuration["qa"]:
                        self.qamaxdoc = config.configuration["qa"]["max-ranked-doc"]
                        if self.qamaxdoc == -1:
                            self.qamaxdoc = 10

    def __init__(self, config: SearchingConfiguration = None, call_context=None):
        if not config:
            raise ValueError("label configuration is mandatory")

        self.config = config
        self._tokenizer = None
        self._mstagger = None
        self._nertagger = None
        self._syntactictagger = None
        self._kwExtractor = None
        self._quantizerModel = None
        self._embeddings = None
        self.qa_host = None
        self.qamaxdoc = 1

        if "disable-document-analysis" not in self.config.configuration:
            self.config.configuration["disable-document-analysis"] = False

        ThotLogger.info(
            "Disable document Analysis:" + str(self.config.configuration["disable-document-analysis"]), context=call_context
        )

        if not config.configuration["disable-document-analysis"]:
            self._tokenizer = Tokenizer(config=config.tokenizerConfig)
            self._mstagger = MorphoSyntacticTagger(config=config.msConfig)
            self._nertagger = NERTagger(config=config.nerConfig)
            self._syntactictagger = SyntacticTagger(config=config.syntaxConfig)
            self._kwExtractor = KeywordsExtractor(config=config.kwConfig)
            self._quantizerModel = None
            with open(config.configuration["search-policy"]["semantic-cluster"]["semantic-quantizer-model"], "rb") as q_model_f:
                self._quantizerModel = RelationsClusterizer(model_file_handler=q_model_f)
                q_model_f.close()
            self._embeddings = Embeddings(config=config.embeddingsConfig)

        self._last_query = dict()
        self._index_name = "text-index"

        if "document-index-name" in self.config.configuration:
            self._index_name = config.configuration["document-index-name"]
        if "suggester" in self.config.configuration:
            self._suggest = self.config.configuration["suggester"]
        else:
            self._suggest = {"number-of-suggestions": 10, "spell-check": True}

        if self._tokenizer:
            ThotLogger.info("* [Search Models] Tokenizer loaded", context=call_context)
        if self._mstagger:
            ThotLogger.info("* [Search Models] MS Tagger loaded", context=call_context)
        if self._nertagger:
            ThotLogger.info("* [Search Models] NER Tagger loaded", context=call_context)
        if self._syntactictagger:
            ThotLogger.info("* [Search Models] Syntactic Tagger loaded", context=call_context)
        if self._kwExtractor:
            ThotLogger.info("* [Search Models] Keyword model loaded", context=call_context)
        if self._quantizerModel:
            ThotLogger.info("* [Search Models] Semantic clusters loaded", context=call_context)
        if self._embeddings:
            ThotLogger.info("* [Search Models] Embeddings loaded", context=call_context)
        if self._quantizerModel:
            ThotLogger.info("* [Search Models] Semantic quantizer loaded", context=call_context)

        (self.es_url, self.es_verify_certs) = get_elastic_url(config.configuration["elasticsearch"])
        ThotLogger.info("Use url:" + self.es_url + " verify certificates:" + str(self.es_verify_certs), context=call_context)

        self.initQA(config)

        if "aggregator" in config.configuration:
            agg_is_enable = True
            if "enable" in config.configuration["aggregator"]:
                agg_is_enable = config.configuration["aggregator"]["enable"]
            if agg_is_enable:
                try:
                    self.aggregator = Aggregator(config=config, call_context=call_context)
                    ThotLogger.info("Aggregator Initialized")
                except Exception as agg_e:
                    ThotLogger.warning("Cannot load aggregator")

        self.pos_filter = set(
            ["ADP", "ADV", "AUX", "CONJ", "CCONJ", "DET", "INTJ", "PART", "SCONJ", "SYM", "SPACE", "PRON", "PUNCT"]
        )

    def _analyzeDocument(self, doc, call_context=None):
        tkeir_doc = {
            "data_source": "user-query",
            "source_doc_id": "user",
            "title": "",
            "content": [doc],
            "kg": [],
            "error": False,
        }
        if self.config.configuration["disable-document-analysis"]:
            return tkeir_doc

        tkeir_doc = self._tokenizer.tokenize(tkeir_doc, call_context=call_context)
        if self._mstagger:
            tkeir_doc = self._mstagger.tag(tkeir_doc)
        if self._nertagger:
            tkeir_doc = self._nertagger.tag(tkeir_doc)
        if self._syntactictagger:
            tkeir_doc = self._syntactictagger.tag(tkeir_doc)
        if self._kwExtractor:
            tkeir_doc = self._kwExtractor.getKeywords(tkeir_doc)
        if self._quantizerModel:
            nameClusterMapping = {"subject": "subject", "property": "relation", "value": "object"}
            semantic_need = {"subject": set(), "relation": set(), "object": set(), "keyword": set()}
            for kg_item in tkeir_doc["kg"]:
                no_position = False
                triple_items = dict()
                for triple_item in ["subject", "property", "value"]:
                    if kg_item[triple_item]["positions"] == [-1] and (kg_item["field_type"] != "keywords"):
                        no_position = True
                    if kg_item[triple_item]["lemma_content"]:
                        triple_items[triple_item] = " ".join(kg_item[triple_item]["lemma_content"])
                    else:
                        triple_items[triple_item] = " ".join(kg_item[triple_item]["content"])
                if not no_position:
                    for triple_item in ["subject", "property", "value"]:
                        semantic_need[nameClusterMapping[triple_item]].add(triple_items[triple_item])
            for kw_item in tkeir_doc["keywords"]:
                semantic_need["keyword"].add(kw_item["text"])
            embpred = {"subject": dict(), "relation": dict(), "object": dict(), "keyword": dict()}
            for triple_item in ["subject", "relation", "object", "keyword"]:
                emb = self._embeddings.computeFromTable(list(semantic_need[triple_item]))
                for e_i in emb:
                    pred = self._quantizerModel.predict([e_i["embedding"]], index=RelationsClusterizer.name2index[triple_item])
                    embpred[triple_item][e_i["content"]] = pred[0]
                    if triple_item == "keyword":
                        tkeir_doc["kg"].append(
                            {
                                "subject": {
                                    "content": e_i["content"].split(" "),
                                    "lemma_content": e_i["content"].split(" "),
                                    "label": "",
                                    "class": pred[0],
                                    "positions": [0, 0],
                                },
                                "property": {
                                    "content": ["rel:is_a"],
                                    "lemma_content": ["rel:is_a"],
                                    "label": "",
                                    "class": -1,
                                    "positions": [-1],
                                },
                                "value": {
                                    "content": ["keyword"],
                                    "lemma_content": ["keyword"],
                                    "label": "",
                                    "class": -1,
                                    "positions": [-1],
                                },
                                "automatically_fill": True,
                                "confidence": 0.0,
                                "weight": 0.0,
                                "field_type": "keywords",
                            }
                        )

            for kg_item in tkeir_doc["kg"]:
                if " ".join(kg_item["subject"]["lemma_content"]) in embpred["subject"]:
                    kg_item["subject"]["class"] = embpred["subject"][" ".join(kg_item["subject"]["lemma_content"])]
                elif " ".join(kg_item["subject"]["content"]) in embpred["subject"]:
                    kg_item["subject"]["class"] = embpred["subject"][" ".join(kg_item["subject"]["content"])]

                if " ".join(kg_item["property"]["lemma_content"]) in embpred["relation"]:
                    kg_item["property"]["class"] = embpred["relation"][" ".join(kg_item["property"]["lemma_content"])]
                elif " ".join(kg_item["property"]["content"]) in embpred["relation"]:
                    kg_item["property"]["class"] = embpred["relation"][" ".join(kg_item["property"]["content"])]

                if " ".join(kg_item["value"]["lemma_content"]) in embpred["object"]:
                    kg_item["value"]["class"] = embpred["object"][" ".join(kg_item["value"]["lemma_content"])]
                elif " ".join(kg_item["value"]["content"]) in embpred["object"]:
                    kg_item["value"]["class"] = embpred["object"][" ".join(kg_item["value"]["content"])]

                for triple in ["subject", "property", "value"]:
                    for t_i in ["lemma_content", "content"]:
                        if isinstance(kg_item[triple][t_i], list):
                            kg_item[triple][t_i] = " ".join(kg_item[triple][t_i])
        return tkeir_doc

    def custom_structured_query(self, doc, call_context=None):
        """Querying with document

        Args:
            doc ([type]): json structure[doc==query, from, size]

        Returns:
            [list]: ranked list
        """
        o = False
        if "observe" in doc:
            o = doc["observe"]
        return SearchingWithStructure(self).custom_structured_query(doc, observmode=o, call_context=call_context)

    def querying_with_doc(self, doc, call_context=None):
        """Querying with structured entry (specific AxelerIA)

        Args:
            doc ([type]): json structure[doc==query, from, size]

        Returns:
            [list]: ranked list
        """
        return SearchingWithDocument(self).querying_with_doc(doc, call_context=call_context)

    def querying_with_sentence(self, doc, call_context=None):
        """Querying with sentence

        Args:
            doc ([type]): json structure[doc==query, from, size]

        Returns:
            [list]: ranked list
        """
        return SearchingWithSentence(self).querying_with_sentence(doc, call_context=call_context)

    def suggest(self, word, call_context=None):
        query_toks = word.split(" ")
        query = {
            "_source": {"includes": ["title"]},
            "suggest": {
                "full_text-suggest": {
                    "prefix": word,
                    "completion": {
                        "field": "text_suggester",
                        "skip_duplicates": True,
                        "size": self.config.configuration["suggester"]["number-of-suggestions"],
                    },
                }
            },
        }
        es_search = None
        if self.es_url:
            try:
                r = requests.post(
                    self.es_url + "/" + self._index_name + "/_search",
                    headers={"Content-Type": "application/json"},
                    data=json.dumps(query),
                    timeout=(600, 600),
                    verify=self.es_verify_certs,
                )
                es_search = json.loads(r.text)
            except Exception as e:
                ThotLogger.error(
                    "Requests error:",
                    trace=exception_error_and_trace(str(e), str(traceback.format_exc())),
                    context=call_context,
                )

        else:
            ThotLogger.error(
                "NO E.S. host defined:", trace=exception_error_and_trace("", str(traceback.format_exc())), context=call_context
            )
        return es_search
