"""Convert source document to tkeir indexer document

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import base64
import json
from thot.core.ThotLogger import ThotLogger, LogUserContext
from thot.tasks.converters.RawConverter import RawConverter
from thot.tasks.converters.EmailConverter import EmailConverter
from thot.tasks.converters.TikaConverter import TikaConverter
from thot.tasks.converters.OrbitConverter import OrbitConverter
from thot.tasks.converters.URIConverter import URIConverter
from thot.tasks.converters import __version_converter__, __date_converter__
from thot.tasks.TaskInfo import TaskInfo


class Converter:
    def __init__(self, config=None):
        """Initialize converters
        Args:
            config : ConverterConfiguration structure
        """

        self.config = config
        self._managed_type = set(["tkeir", "raw", "email", "docx", "odt", "pdf", "rtf", "orbit-csv", "uri"])

    def listTypes(self) -> list:
        """return the liste of type

        Returns:
            list: return the manager list of format to convert
        """
        return list(self._managed_type)

    def convert(self, data_type: str = "raw", data: str = None, source: str = "empty", call_context=None, tags=[]):
        """Convert document

        Args:
            data_type (str, optional): type of managed (should be in managed list). Defaults to "raw".
            data (str, optional): document in base64. Defaults to None.
            source (str, optional): source of the document. Defaults to "empty".
            call_context : logger call context

        Raises:
            ValueError: exception raised when the data_type is not managed

        Returns:
            [dict]: return a pre-fill document compliant with tkeir tools
        """
        if data_type not in self._managed_type:
            raise ValueError("Type '" + data_type + "' is not managed.")
        data_decode = base64.b64decode(data)

        if data_type == "tkeir":
            loaded_tkeir_doc = json.loads(data_decode.decode())
            if "title" not in loaded_tkeir_doc:
                loaded_tkeir_doc["title"] = ""
            if "content" not in loaded_tkeir_doc:
                loaded_tkeir_doc["content"] = ""
            if "data_source" not in loaded_tkeir_doc:
                loaded_tkeir_doc["data_source"] = ""
            if "source_doc_id" not in loaded_tkeir_doc:
                loaded_tkeir_doc["source_doc_id"] = ""
            if "kg" not in loaded_tkeir_doc:
                loaded_tkeir_doc["kg"] = []
            tkeir_doc = {
                "data_source": loaded_tkeir_doc["data_source"],
                "source_doc_id": loaded_tkeir_doc["source_doc_id"],
                "title": loaded_tkeir_doc["title"],
                "content": loaded_tkeir_doc["content"],
                "kg": loaded_tkeir_doc["kg"],
                "error": False,
            }
        elif data_type == "email":
            tkeir_doc = EmailConverter.convert(data_decode, source, call_context=call_context)
        elif data_type == "raw":
            tkeir_doc = RawConverter.convert(data_decode, source, call_context=call_context)
        elif data_type == "orbit-csv":
            tkeir_doc = OrbitConverter.convert(data_decode, source, call_context=call_context)
        elif data_type == "uri":
            tkeir_doc = URIConverter.convert(data_decode, source, call_context=call_context)
        elif self.config:
            tkeir_doc = TikaConverter.convert(data_decode, source, self.config.configuration, call_context=call_context)
        else:
            raise ValueError("Bad converter")
        if ("title" not in tkeir_doc) and ("content" not in tkeir_doc):
            raise ValueError("Title and/or Content is mandatory")
        if (not tkeir_doc["content"]) and (not tkeir_doc["title"]):
            raise ValueError("Document is empty")
        
        for tag in tags:
            tkeir_doc["kg"].append(
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
                                        "content": tag,
                                        "label_content": "",
                                        "lemma_content": tag.lower(),
                                        "class": -1,
                                        "positions": [-1],
                                    },
                                    "value": {
                                        "content": "tag",
                                        "label_content": "",
                                        "lemma_content": "tag",
                                        "class": -1,
                                        "positions": [-1],
                                    },
                                    "weight": 0.0,
                                }
                            )
        taskInfo = TaskInfo(task_name="converter", task_version=__version_converter__, task_date=__date_converter__)
        tkeir_doc = taskInfo.addInfo(tkeir_doc)
        return tkeir_doc

    def run(self, data: dict, call_context=None):
        """Run conversion (used in REST Service)
        Args:
            data: data to convert in tkeir doc format
            call_context : logger context
        Returns:
            dict : tkeir document
        """
        return self.convert(data_type=data["datatype"], data=data["data"], source=data["source"], call_context=call_context)
