# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.tasks.searching.SearchingConfiguration import SearchingConfiguration
import unittest
import json
import os


class TestSearchingConfiguration(unittest.TestCase):

    test_dict = {
        "logger": {"logging-level": "debug"},
        "searching": {
            "document-index-name": "default-text-index",
            "disable-document-analysis": True,
            "aggregator": {"host": "localhost", "port": "18888", "index": True, "engines": ["wikipedia", "github"]},
            "qa": {
                "host": "localhost",
                "port": 10011,
                "associate-environment": {"host": "QA_HOST", "port": "QA_PORT"},
                "max-ranked-doc": -1,
                "use-ssl": True,
                "no-ssl-verify": True,
            },
            "search-policy": {
                "semantic-cluster": {
                    "semantic-quantizer-model": "/home/tkeir_svc/tkeir/app/projects/default/resources/modeling/relation_names.model.pkl"
                },
                "settings": {
                    "basic-querying": {"uniq-word-query": True, "boosted-uniq-word-query": False, "cut-query": 4096},
                    "advanced-querying": {
                        "use-lemma": False,
                        "use-keywords": False,
                        "use-knowledge-graph": False,
                        "use-semantic-keywords": False,
                        "use-semantic-knowledge-graph": True,
                        "use-concepts": True,
                        "use-sentences": False,
                        "querying": {
                            "match-phrase-slop": 1,
                            "match-phrase-boosting": 0.5,
                            "match-sentence": {"number-and-symbol-filtering": True, "max-number-of-words": 30},
                            "match-keyword": {
                                "number-and-symbol-filtering": True,
                                "semantic-skip-highest-ranked-classes": 3,
                                "semantic-max-boosting": 5,
                            },
                            "match-svo": {
                                "semantic-use-class-triple": False,
                                "semantic-use-lemma-property-object": False,
                                "semantic-use-subject-lemma-object": False,
                                "semantic-use-subject-property-lemma": False,
                                "semantic-use-lemma-lemma-object": True,
                                "semantic-use-lemma-property-lemma": True,
                                "semantic-use-subject-lemma-lemma": True,
                                "semanic-max-boosting": 5,
                            },
                            "match-concept": {"concept-boosting": 0.2, "concept-pruning": 10},
                        },
                    },
                    "query-expansion": {
                        "term-pruning": 128,
                        "suppress-number": True,
                        "keep-word-collection-thresold-under": 0.4,
                        "word-boost-thresold-above": 0.25,
                    },
                    "scoring": {
                        "normalize-score": True,
                        "document-query-intersection-penalty": "by-query-size",
                        "run-clause-separately": True,
                        "expand-results": 50,
                    },
                    "results": {"set-highlight": False, "excludes": []},
                },
            },
            "elasticsearch": {
                "network": {
                    "host": "http://opendistro:9200",
                    "port": 0,
                    "use_ssl": False,
                    "verify_certs": False,
                    "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"},
                }
            },
            "network": {
                "host": "0.0.0.0",
                "port": 8000,
                "associate-environment": {"host": "SEARCH_HOST", "port": "SEARCH_PORT"},
                "ssl": {
                    "cert": "/home/tkeir_svc/tkeir/app/ssl/certificate.crt",
                    "key": "/home/tkeir_svc/tkeir/app/ssl/privateKey.key",
                },
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
        "tokenizers": {
            "segmenters": [
                {
                    "language": "en",
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/default/resources/modeling/tokenizer/en",
                    "normalization-rules": "tokenizer-rules.json",
                    "mwe": "tkeir_mwe.pkl",
                }
            ],
            "network": {
                "host": "0.0.0.0",
                "port": 10001,
                "associate-environment": {"host": "TOKENIZER_HOST", "port": "TOKENIZER_PORT"},
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
        "morphosyntax": {
            "taggers": [
                {
                    "language": "en",
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/default/resources/modeling/tokenizer/en",
                    "mwe": "tkeir_mwe.pkl",
                    "pre-sentencizer": True,
                    "pre-tagging-with-concept": True,
                    "add-concept-in-knowledge-graph": True,
                }
            ],
            "network": {
                "host": "0.0.0.0",
                "port": 10002,
                "associate-environment": {"host": "MSTAGGER_HOST", "port": "MSTAGGER_PORT"},
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
        "named-entities": {
            "label": [
                {
                    "language": "en",
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/default/resources/modeling/tokenizer/en",
                    "mwe": "tkeir_mwe.pkl",
                    "use-pre-label": True,
                }
            ],
            "network": {
                "host": "0.0.0.0",
                "port": 10003,
                "associate-environment": {"host": "NERTAGGER_HOST", "port": "NERTAGGER_PORT"},
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
        "embeddings": {
            "models": [{"language": "multi"}],
            "network": {
                "host": "0.0.0.0",
                "port": 10005,
                "associate-environment": {"host": "SENT_EMBEDDING_HOST", "port": "SENT_EMBEDDING_PORT"},
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
        "syntax": {
            "taggers": [
                {
                    "language": "en",
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/default/configs",
                    "syntactic-rules": "syntactic-rules.json",
                }
            ],
            "network": {
                "host": "0.0.0.0",
                "port": 10004,
                "associate-environment": {"host": "SYNTAXTAGGER_HOST", "port": "SYNTAXTAGGER_PORT"},
            },
            "runtime": {
                "request-max-size": 100000000,
                "request-buffer-queue-size": 100,
                "keep-alive": True,
                "keep-alive-timeout": 5,
                "graceful-shutown-timeout": 15.0,
                "request-timeout": 60,
                "response-timeout": 60,
                "workers": 20,
            },
            "serialize": {
                "input": {"path": "/tmp", "keep-service-info": True},
                "output": {"path": "/tmp", "keep-service-info": True},
            },
        },
        "keywords": {
            "extractors": [
                {
                    "language": "en",
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/default/resources/modeling/tokenizer/en",
                    "stopwords": "en.stopwords.lst",
                    "use-lemma": True,
                    "use-pos": True,
                    "use-form": False,
                }
            ],
            "network": {
                "host": "0.0.0.0",
                "port": 10007,
                "associate-environment": {"host": "KEYWORD_HOST", "port": "KEYWORD_PORT"},
            },
            "runtime": {
                "request-max-size": 100000000,
                "request-buffer-queue-size": 100,
                "keep-alive": True,
                "keep-alive-timeout": 5,
                "graceful-shutown-timeout": 15.0,
                "request-timeout": 60,
                "response-timeout": 60,
                "workers": 20,
            },
            "serialize": {
                "input": {"path": "/tmp", "keep-service-info": True},
                "output": {"path": "/tmp", "keep-service-info": True},
            },
        },
    }

    def test_load(self):
        try:
            with open("/tmp/cfg.json", "w") as f:
                json.dump(TestSearchingConfiguration.test_dict, f)
                f.close()
        except Exception as e:
            self.assertFalse(True)
        fh = open("/tmp/cfg.json")
        searchingConfig = SearchingConfiguration()
        searchingConfig.load(fh)
        fh.close()
        self.assertEqual(searchingConfig.logger_config.configuration["logger"], TestSearchingConfiguration.test_dict["logger"])
        TestSearchingConfiguration.test_dict["searching"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            searchingConfig.configuration["elasticsearch"], TestSearchingConfiguration.test_dict["searching"]["elasticsearch"]
        )

    def test_loads(self):
        searchingConfig = SearchingConfiguration()
        searchingConfig.loads(TestSearchingConfiguration.test_dict)
        self.assertEqual(searchingConfig.logger_config.configuration["logger"], TestSearchingConfiguration.test_dict["logger"])
        TestSearchingConfiguration.test_dict["searching"]["serialize"]["do-serialization"] = True
        self.assertEqual(
            searchingConfig.configuration["elasticsearch"], TestSearchingConfiguration.test_dict["searching"]["elasticsearch"]
        )

    def test_clear(self):
        searchingConfig = SearchingConfiguration()
        searchingConfig.loads(TestSearchingConfiguration.test_dict)
        searchingConfig.clear()
        self.assertEqual(searchingConfig.logger_config.logger_name, "default")
        self.assertEqual(searchingConfig.logger_config.configuration, None)
        self.assertEqual(searchingConfig.configuration, dict())
