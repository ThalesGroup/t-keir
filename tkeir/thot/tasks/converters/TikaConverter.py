# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
from bs4 import BeautifulSoup
import requests
import traceback
from thot.core.ThotLogger import ThotLogger, LogUserContext
from thot.core.Constants import exception_error_and_trace


class TikaConverter:
    @staticmethod
    def convert(data: bytes, source_doc_id, config, call_context=None):
        """ Convert raw document into tkeir doc by using Tika
        Args:
            data: raw document
            source_doc_id : uniq document id
            config: configuration (for tika host and port)
            call_context : logger context
        Returns:
            tkeir document
        """
        there_is_error = False
        parsed = None
        try:
            mimetype = "text/html"
            if source_doc_id.lower().endswith("pdf"):
                mimetype = "application/pdf"
            elif source_doc_id.lower().endswith("rtf"):
                mimetype = "application/rtf"
            elif source_doc_id.lower().endswith("docx"):
                mimetype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            elif source_doc_id.lower().endswith("doc"):
                mimetype = "application/msword"
            elif source_doc_id.lower().endswith("pptx"):
                mimetype = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            elif source_doc_id.lower().endswith("ppt"):
                mimetype = "application/vnd.ms-powerpoint"
            elif source_doc_id.lower().endswith("odt"):
                mimetype = "application/vnd.oasis.opendocument.text"
            tika_url = (
                "http://"
                + config.configuration["settings"]["tika"]["host"]
                + ":"
                + str(config.configuration["settings"]["tika"]["port"])
                + "/tika"
            )
            r = requests.put(tika_url, data=data, headers={"Content-Type": mimetype})
            if r.status_code == 200:
                parsed = {"content": r.text}
            else:
                ThotLogger.error("Cannot connect to tika:" + tika_url, trace=traceback.format_exc(), context=call_context)
                raise ValueError("tika does not answer correctly")
        except Exception as e:
            ThotLogger.error(
                "Exception occured with tika",
                trace=exception_error_and_trace(str(e), str(traceback.format_exc())),
                context=call_context,
            )
            parsed = {"content": "***NOT AVAILABLE***" + str(e)}
            there_is_error = True
        if (not parsed) or (not parsed["content"]):
            parsed = {"content": "***NOT AVAILABLE***"}
            there_is_error = True
        soup = BeautifulSoup(parsed["content"], "html.parser")
        document = {
            "data_source": "converter-service",
            "source_doc_id": source_doc_id,
            "title": source_doc_id,
            "content": [
                soup.get_text()
            ],
            "kg": [],
            "error": there_is_error,
        }
        return document
