# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
from bs4 import BeautifulSoup
from thot.core.ThotLogger import ThotLogger, LogUserContext


class RawConverter:
    @staticmethod
    def convert(data: bytes, source_doc_id, call_context=None):
        """convert raw data to tkeir content

        Args:
            data (bytes): document in byte format
            source_doc_id ([type]): source of the document

        Returns:
            [dict]: tkeir document
        """
        ThotLogger.debug("Call Raw Converter", context=call_context)
        soup = BeautifulSoup(data.decode(), "html.parser")
        document = {
            "data_source": "converter-service",
            "source_doc_id": source_doc_id,
            "title": "",
            "content": [
                soup.get_text()
            ],
            "kg": [],
            "error": False,
        }
        return document
