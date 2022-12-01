# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.core.ThotLogger import ThotLogger, LogUserContext
from thot.tasks.tokenizer.TokenizerConfiguration import TokenizerConfiguration
from thot.tasks.tokenizer.Tokenizer import Tokenizer
import json
import unittest
import time
import os


class TestTokenizer(unittest.TestCase):

    tokenizer_config = {
        "logger": {"logging-level": "debug"},
        "tokenizers": {
            "segmenters": [
                {
                    "language": "en",
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/default/resources/modeling/tokenizer/en",
                    "mwe": "tkeir_mwe.pkl",
                    "normalization-rules": "tokenizer-rules.json",
                }
            ],
            "network": {
                "host": "0.0.0.0",
                "port": 8080,
                "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"},
            },
            "runtime": {
                "request-max-size": 100000000,
                "request-buffer-queue-size": 100,
                "keep-alive": True,
                "keep-alive-timeout": 5,
                "graceful-shutown-timeout": 15.0,
                "request-timeout": 60,
                "response-timeout": 60,
                "workers": 1,
            },
            "serialize": {
                "input": {"path": "/tmp", "keep-service-info": True},
                "output": {"path": "/tmp", "keep-service-info": True},
            },
        },
    }

    def __test_trie(self):
        config = TokenizerConfiguration()
        config.loads(TestTokenizer.tokenizer_config)
        ThotLogger.loads(config.logger_config.configuration)
        tkeir_doc = {
            "data_source": "tokenizer-service",
            "source_doc_id": "file://test.txt",
            "title": "",
            "content": "the poly[2,4-(pipérazin-1,4-yl)-6-(morpholin-4-yl)-1,3,5-triazine] is a basic polymer with nothing in common with Tow Truck Operator, it was developed at Aix La Chapelle",
        }
        tokenizer = Tokenizer(config=config)
        tkeir_doc = tokenizer.tokenize(tkeir_doc)
        self.assertEqual(
            tkeir_doc["content_tokens"],
            [
                [
                    {"token": "the", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                    {
                        "token": "poly[2,4-(pipérazin-1,4-yl)-6-(morpholin-4-yl)-1,3,5-triazine]",
                        "start_sentence": False,
                        "mwe": {
                            "data": {
                                "chemistry-terminology": {
                                    "pos": "NOUN",
                                    "data": [{"type": "concept", "concept": "piperazine"}],
                                    "weight": 10,
                                }
                            },
                            "is-compound": False,
                        },
                    },
                    {"token": "is", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {"token": "a", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {"token": "basic", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {"token": "polymer", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {"token": "with", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {"token": "nothing", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {"token": "in", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {"token": "common", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {"token": "with", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {
                        "token": "Tow Truck Operator",
                        "start_sentence": False,
                        "mwe": {
                            "is-compound": True,
                            "data": {
                                "jobtitle": {"pos": "NOUN", "data": [{"type": "concept", "concept": "operator"}], "weight": 10}
                            },
                        },
                    },
                    {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {"token": "it", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {"token": "was", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {"token": "developed", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {"token": "at", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    {
                        "token": "Aix La Chapelle",
                        "start_sentence": False,
                        "mwe": {
                            "is-compound": True,
                            "data": {"location.city": {"pos": "PROPN", "data": [{"type": "named-entity"}], "weight": 10}},
                        },
                    },
                ]
            ],
        )

    def test_typos(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        res_path = os.path.abspath(os.path.join(dir_path, "../../../app/projects/default/resources/modeling/tokenizer/en/"))
        TestTokenizer.tokenizer_config["tokenizers"]["segmenters"][0]["resources-base-path"] = res_path
        config = TokenizerConfiguration()
        config.loads(TestTokenizer.tokenizer_config)
        ThotLogger.loads(config.logger_config.configuration)
        cid = "autogenerated-" + str("xxx")
        log_context = LogUserContext(cid)
        text = [["The Knowlege about the goverment are huge."]]
        tkeir_doc = {"data_source": "tokenizer-service", "source_doc_id": "file://test.txt", "title": "", "content": text}
        test_dict = {
            "data_source": "tokenizer-service",
            "source_doc_id": "file://test.txt",
            "title": "",
            "content": [["The Knowlege about the goverment are huge."]],
            "content_tokens": [
                [
                    [
                        [
                            {"token": "The", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Knowledge", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "about", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "government", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "are", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "huge", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        ]
                    ]
                ]
            ],
        }
        tokenizer = Tokenizer(config=config, call_context=log_context)
        tkeir_doc = tokenizer.tokenize(tkeir_doc, call_context=log_context)
        import json

        self.assertEqual(tkeir_doc["content_tokens"], test_dict["content_tokens"])

    def test_normalizer(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        res_path = os.path.abspath(os.path.join(dir_path, "../../../app/projects/default/resources/modeling/tokenizer/en/"))
        TestTokenizer.tokenizer_config["tokenizers"]["segmenters"][0]["resources-base-path"] = res_path
        config = TokenizerConfiguration()
        config.loads(TestTokenizer.tokenizer_config)
        ThotLogger.loads(config.logger_config.configuration)
        cid = "autogenerated-" + str("xxx")
        log_context = LogUserContext(cid)
        text = [["The fiber is not the Fibres."]]
        tkeir_doc = {"data_source": "tokenizer-service", "source_doc_id": "file://test.txt", "title": "", "content": text}
        test_dict = {
            "data_source": "tokenizer-service",
            "source_doc_id": "file://test.txt",
            "title": "",
            "content": [["The fiber is not the Fibres."]],
            "content_tokens": [
                [
                    [
                        [
                            {"token": "The", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "fiber", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "is", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "not", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": "Fibers", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                            {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        ]
                    ]
                ]
            ],
        }
        tokenizer = Tokenizer(config=config, call_context=log_context)
        tkeir_doc = tokenizer.tokenize(tkeir_doc, call_context=log_context)
        self.assertEqual(tkeir_doc["content_tokens"], test_dict["content_tokens"])

    def test_underscore_and_star(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        res_path = os.path.abspath(os.path.join(dir_path, "../../../app/projects/default/resources/modeling/tokenizer/en/"))
        TestTokenizer.tokenizer_config["tokenizers"]["segmenters"][0]["resources-base-path"] = res_path
        config = TokenizerConfiguration()
        config.loads(TestTokenizer.tokenizer_config)
        cid = "autogenerated-" + str("xxx")
        log_context = LogUserContext(cid)
        ThotLogger.loads(config.logger_config.configuration)
        text = [
            [" this is a __underscored text__ with _ and __ to use a sp_lit. stars for news * research and development * list."]
        ]
        tkeir_doc = {
            "data_source": "tokenizer-service",
            "source_doc_id": "file://test.txt",
            "title": "none",
            "content": text,
        }
        tokenizer = Tokenizer(config=config, call_context=log_context)
        tkeir_doc = tokenizer.tokenize(tkeir_doc, call_context=log_context)
        cmp_tok = [
            [
                [
                    [
                        {"token": "this", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "is", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "a", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "_", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "_", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "underscored", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "text", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "_", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "_", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "with", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "_", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "and", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "_", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "_", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "to", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "use", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "a", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "sp_lit", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    ],
                    [
                        {"token": "stars", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "for", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "news", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "*", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "research", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "and", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "development", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "*", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "list", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    ],
                ]
            ]
        ]
        self.assertEqual(cmp_tok, tkeir_doc["content_tokens"])

    def test_tokenizer(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        res_path = os.path.abspath(os.path.join(dir_path, "../../../app/projects/default/resources/modeling/tokenizer/en/"))
        TestTokenizer.tokenizer_config["tokenizers"]["segmenters"][0]["resources-base-path"] = res_path
        config = TokenizerConfiguration()
        config.loads(TestTokenizer.tokenizer_config)
        ThotLogger.loads(config.logger_config.configuration)
        cid = "autogenerated-" + str("xxx")
        log_context = LogUserContext(cid)

        text = [
            [
                "A new study is the first to identify how human brains grow much larger, with three times as many neurons, compared with chimpanzee and gorilla brains. The study, led by researchers at the Medical Research Council (MRC) Laboratory of Molecular Biology in Cambridge, UK, identified a key molecular switch that can make ape brain organoids grow more like human organoids, and vice versa."
            ],
            [
                "The study, published in the journal Cell, compared brain organoids -- 3D tissues grown from stem cells which model early brain development -- that were grown from human, gorilla and chimpanzee stem cells.Similar to actual brains, the human brain organoids grew a lot larger than the organoids from other apes.Dr Madeline Lancaster, from the MRC Laboratory of Molecular Biology, who led the study, said: This provides some of the first insight into what is different about the developing human brain that sets us apart from our closest living relatives, the other great apes. The most striking difference between us and other apes is just how incredibly big our brains are.During the early stages of brain development, neurons are made by stem cells called neural progenitors. These progenitor cells initially have a cylindrical shape that makes it easy for them to split into identical daughter cells with the same shape."
            ],
        ]

        tkeir_doc = {
            "data_source": "tokenizer-service",
            "source_doc_id": "file://test.txt",
            "title": "Access to UBSWenergy Production Environment",
            "content": text,
        }

        tokenizer = Tokenizer(config=config, call_context=log_context)
        es_time = time.time()
        tkeir_doc = tokenizer.tokenize(tkeir_doc, call_context=log_context)

        content_tokens = [
            [
                [
                    [
                        {"token": "A", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "new", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "study", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "is", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "first", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "to", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "identify", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "how", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "human", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "brains", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "grow", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "much", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "larger", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "with", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "three", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "times", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "as", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "many", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "neurons", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "compared", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "with", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "chimpanzee", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "and", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "gorilla", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "brains", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    ],
                    [
                        {"token": "The", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "study", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "led", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "by", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "researchers", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "at", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "Medical", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "Research", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "Council", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "(", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "MRC", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ")", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "Laboratory", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "of", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "Molecular", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "Biology", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "in", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "Cambridge", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "UK", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "identified", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "a", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "key", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "molecular", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "switch", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "that", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "can", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "make", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "ape", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "brain", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "organoids", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "grow", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "more", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "like", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "human", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "organoids", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "and", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "vice", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "versa", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    ],
                ]
            ],
            [
                [
                    [
                        {"token": "The", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "study", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "published", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "in", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "journal", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "Cell", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "compared", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "brain", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "organoids", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "--", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "3D", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "tissues", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "grown", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "from", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "stem", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "cells", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "which", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "model", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "early", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "brain", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "development", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "--", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "that", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "were", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "grown", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "from", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "human", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "gorilla", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "and", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "chimpanzee", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "stem", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "cells", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "Similar", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "to", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "actual", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "brains", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "human", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "brain", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "organoids", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "grew", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "a", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "lot", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "larger", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "than", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "organoids", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "from", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "other", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "apes", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "Dr", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "Madeline", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "Lancaster", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "from", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "MRC", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "Laboratory", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "of", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "Molecular", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "Biology", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "who", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "led", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "study", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "said", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ":", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "This", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "provides", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "some", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "of", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "first", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "insight", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "into", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "what", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "is", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "different", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "about", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "developing", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "human", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "brain", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "that", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "sets", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "us", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "apart", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "from", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "our", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "closest", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "living", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "relatives", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "other", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "great", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "apes", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    ],
                    [
                        {"token": "The", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "most", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "striking", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "difference", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "between", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "us", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "and", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "other", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "apes", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "is", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "just", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "how", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "incredibly", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "big", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "our", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "brains", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "are", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "During", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "early", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "stages", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "of", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "brain", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "development", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ",", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "neurons", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "are", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "made", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "by", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "stem", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "cells", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "called", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "neural", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "progenitors", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    ],
                    [
                        {"token": "These", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "progenitor", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "cells", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "initially", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "have", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "a", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "cylindrical", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "shape", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "that", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "makes", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "it", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "easy", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "for", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "them", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "to", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "split", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "into", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "identical", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "daughter", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "cells", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "with", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "the", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "same", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": "shape", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                        {"token": ".", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                    ],
                ]
            ],
        ]
        title_tokens = [
            [
                {"token": "Access", "start_sentence": True, "mwe": {"is-compound": False, "data": {}}},
                {"token": "to", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                {"token": "UBSWenergy", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                {"token": "Production", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
                {"token": "Environment", "start_sentence": False, "mwe": {"is-compound": False, "data": {}}},
            ]
        ]
        es_time = time.time() - es_time
        ThotLogger.info("Tokenize time:" + str(es_time))
        self.assertEqual(tkeir_doc["content_tokens"], content_tokens)
        self.assertEqual(tkeir_doc["title_tokens"], title_tokens)
