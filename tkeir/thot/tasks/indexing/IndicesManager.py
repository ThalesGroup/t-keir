# -*- coding: utf-8 -*-
"""E.S Indice manager

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
import os
import logging
import json
from elasticsearch import Elasticsearch
from thot.core.ThotLogger import ThotLogger
from thot.core.Utils import get_elastic_url


class IndicesManager:
    def __init__(self):
        pass

    @staticmethod
    def testIndicesExistence(config=None):
        idx_exist = []
        (es_url, es_verify_cert) = get_elastic_url(config["elasticsearch"])
        es_hosts = [{"host": config["elasticsearch"]["network"]["host"], "port": config["elasticsearch"]["network"]["port"]}]
        es = Elasticsearch(hosts=[es_url], verify_certs=es_verify_cert, maxsize=25)
        idx_exist = dict()
        for index_field in ["nms-index", "text-index", "relation-index"]:
            try:
                idx_exist[index_field] = es.indices.exists(index=config["elasticsearch"][index_field]["index-name"])
            except Exception as e:
                ThotLogger.warning("Create index issue: '" + str(e) + "'")
        return idx_exist

    @staticmethod
    def createIndices(config=None):
        if config is None:
            raise ValueError("Configuration is mandatory")
        (es_url, es_verify_cert) = get_elastic_url(config["elasticsearch"])
        es_hosts = [{"host": config["elasticsearch"]["network"]["host"], "port": config["elasticsearch"]["network"]["port"]}]
        es = Elasticsearch(hosts=[es_url], verify_certs=es_verify_cert, maxsize=25)
        for index_field in ["nms-index", "text-index", "relation-index"]:
            with open(config["elasticsearch"][index_field]["mapping-file"]) as json_mapping_f:
                idx_data = json.load(json_mapping_f)
                ThotLogger.info("Create index '" + index_field + "'")
                try:
                    es.indices.create(index=config["elasticsearch"][index_field]["name"], body=idx_data)
                except Exception as e:
                    ThotLogger.warning("Create index issue: '" + str(e) + "'")

        @staticmethod
        def dump_index(index_name=None):
            pass

        @staticmethod
        def del_index():
            pass
