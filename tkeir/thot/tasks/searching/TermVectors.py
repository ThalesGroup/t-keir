# -*- coding: utf-8 -*-
"""Term vectors
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""


import requests
import json


class TermVectors:
    def __init__(self, config):
        self.es_url = config["es-url"]
        self.es_verify = config["es-verify"]
        self.index = config["index"]

    def docId2TermVector(self, docid: str, fields: list):
        fields_str = ",".join(fields)
        q_url = (
            self.es_url
            + "/"
            + self.index
            + "/_termvectors/"
            + docid
            + "?fields="
            + fields_str
            + "&field_statistics=true"
            + "&term_statistics=true"
        )
        r = requests.get(q_url, headers={"Content-Type": "application/json"}, verify=self.es_verify, timeout=(600, 600))
        return r.json()

    def query2TermVector(self, query: dict):
        q_url = self.es_url + "/" + self.index + "/_termvectors" + "?field_statistics=true" + "&term_statistics=true"
        r = requests.get(
            q_url,
            data=json.dumps({"doc": query}),
            headers={"Content-Type": "application/json"},
            verify=self.es_verify,
            timeout=(600, 600),
        )
        return r.json()
