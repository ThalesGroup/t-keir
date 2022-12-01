# -*- coding: utf-8 -*-
"""Convert source document (get from url) to tkeir indexer document

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
import requests
import os
from bs4 import BeautifulSoup
from html.parser import HTMLParser
import re

from thot.core.ThotLogger import ThotLogger
import thot.core.Constants as Constants
import traceback


def do_doc_error(source_doc_id):
    """ Generate empty T-KEIR file
    """
    return {
        "data_source": "converter-service",
        "source_doc_id": source_doc_id,
        "title": "",
        "content": "",
        "kg": [],
        "error": True,
    }


class URIConverter:
    @staticmethod
    def convert(data: bytes, source_doc_id, call_context=None):
        """convert raw data to tkeir content

        Args:
            data (bytes): document in byte format
            source_doc_id ([type]): source of the document

        Returns:
            [dict]: tkeir document
        """
        ThotLogger.debug("Call URI Converter", context=call_context)
        url_to_request = data.decode()
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "3600",
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0",
        }

        proxyDict = {}
        if "HTTP_PROXY" in os.environ:
            proxyDict["http"] = os.environ["HTTP_PROXY"]
        if "HTTPS_PROXY" in os.environ:
            proxyDict["https"] = os.environ["HTTPS_PROXY"]

        create_doc = False
        try:
            if proxyDict:
                r = requests.get(url_to_request, headers, proxies=proxyDict)
            else:
                r = requests.get(url_to_request, headers)
            if ("content-type" in r.headers) and (
                ("text" in r.headers["content-type"]) or ("json" in r.headers["content-type"])
            ):
                create_doc = True
        except Exception as e:
            ThotLogger.warning(
                "URI '"
                + url_to_request
                + "' GET failed:"
                + Constants.exception_error_and_trace(str(e), str(traceback.format_exc()))
            )
        if create_doc:

            if r.status_code == 200:
                kg = []
                soup = BeautifulSoup(r.content, "html.parser")
                for n in soup.find_all("nav"):
                    n.extract()
                for h in soup.find_all("header"):
                    h.extract()
                for f in soup.find_all("footer"):
                    f.extract()
                for s in soup.find_all("script"):
                    s.extract()
                for k in range(1, 6):
                    for hi in soup.find_all("h" + str(k)):
                        content = hi.text.strip()
                        if content:
                            kg.append(
                                {
                                    "automatically_fill": True,
                                    "confidence": 1.0,
                                    "field_type": "keywords",
                                    "property": {
                                        "content": "rel:is_a",
                                        "label_content": "",
                                        "lemma_content": "rel:is_a",
                                        "class": -1,
                                        "positions": [-1],
                                    },
                                    "subject": {
                                        "content": content,
                                        "label_content": "",
                                        "lemma_content": content.lower(),
                                        "class": -1,
                                        "positions": [-1],
                                    },
                                    "value": {
                                        "content": "keyword",
                                        "label_content": "",
                                        "lemma_content": "keyword",
                                        "class": -1,
                                        "positions": [-1],
                                    },
                                    "weight": 0.0,
                                }
                            )
                doc_title = ""
                doc_content = ""
                if soup.title:
                    doc_title = soup.title.text
                h = HTMLParser()
                doc_content = h.unescape(soup.get_text())
                if doc_content or doc_title:
                    raw_text = re.sub(r'\n+', '\n', soup.get_text()).strip()
                    document = {
                        "data_source": "converter-service",
                        "source_doc_id": source_doc_id,
                        "title": doc_title,
                        "content": [raw_text],
                        "kg": kg,
                        "error": False,
                    }
                else:
                    document = do_doc_error(source_doc_id)
            else:
                document = do_doc_error(source_doc_id)
        else:
            document = do_doc_error(source_doc_id)
        return document
