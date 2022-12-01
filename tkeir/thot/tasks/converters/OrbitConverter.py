# -*- coding: utf-8 -*-
"""Search ai searver: the search server.
It reads the default configuration file containing all information about the server (host, port, number of thread, NLP configuration ...)

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

# OS import
import os
import sys
import argparse
import csv
import re
import errno
import traceback
import json
import time
from thot.core.ThotLogger import ThotLogger, LogUserContext


dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../../thot")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))


def callback_pipe__(document, rule, cell, start_storage=0):
    item_split = cell.split("|")
    if rule["kg"]:
        for kg_entry in item_split[start_storage:]:
            rule_value = rule["value"]
            if len(rule["value"]) > 4096:
                rule_value = rule["value"][0:4096]
            document["kg"].append(
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "orbit-csv",
                    "property": {"content": "rel:is_a", "label_content": "", "lemma_content": "rel:is_a", "positions": [-1]},
                    "subject": {
                        "content": kg_entry.lower(),
                        "label_content": "",
                        "lemma_content": kg_entry.lower(),
                        "positions": [-1],
                    },
                    "value": {"content": rule_value, "label_content": "", "lemma_content": rule_value, "positions": [-1]},
                    "weight": 0.0,
                }
            )
    else:
        if rule["value"] == "title":
            for kg_entry in item_split[start_storage:]:
                document["title"].append(kg_entry)
        else:
            document["content"].append(rule["value"])
            for kg_entry in item_split[start_storage:]:
                document["content"].append(kg_entry)
    if rule["value"] == "abstract":
        document["content"].append(rule["value"])
        for kg_entry in item_split[start_storage:]:
            document["content"].append(kg_entry)
    if rule["value"] == "claims":
        document["content"].append(rule["value"])
        for kg_entry in item_split[start_storage:]:
            document["content"].append(kg_entry)
    if rule["value"] == "independent-claims":
        document["content"].append(rule["value"])
        for kg_entry in item_split[start_storage:]:
            document["content"].append(kg_entry)
    if rule["value"] == "english-description":
        test_desciption = ""
        for kg_entry in item_split[start_storage:]:
            test_desciption = test_desciption + " " + kg_entry
        if len(test_desciption) < 256:
            document["convertion"] = False
        else:
            document["convertion"] = True


def callback_simplestorage(document, rule, cell):
    document["kg"].append(
        {
            "automatically_fill": True,
            "confidence": 1.0,
            "field_type": "orbit-csv",
            "property": {"content": "rel:is_a", "label_content": "", "lemma_content": "rel:is_a", "positions": [-1]},
            "subject": {"content": cell.lower(), "label_content": "", "lemma_content": cell.lower(), "positions": [-1]},
            "value": {"content": rule["value"], "label_content": "", "lemma_content": rule["value"], "positions": [-1]},
            "weight": 0.0,
        }
    )


def callback_pipe(document, rule, cell):
    callback_pipe__(document, rule, cell, start_storage=0)


def callback_cut_after_pipe(document, rule, cell):
    callback_pipe__(document, rule, cell, start_storage=1)


def callback_cut_after_2pipes(document, rule, cell):
    callback_pipe__(document, rule, cell, start_storage=2)


def callback_pipe_remove_parenthesis(document, rule, cell):
    x = re.sub(r"\([^)]*\)", "#####", cell)
    x = x.replace("|", "").split("#####")
    for kg_entry in x:
        if kg_entry:
            document["kg"].append(
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "orbit-csv",
                    "property": {"content": "rel:is_a", "label_content": "", "lemma_content": "rel:is_a", "positions": [-1]},
                    "subject": {
                        "content": kg_entry.lower(),
                        "label_content": "",
                        "lemma_content": kg_entry.lower(),
                        "positions": [-1],
                    },
                    "value": {"content": rule["value"], "label_content": "", "lemma_content": rule["value"], "positions": [-1]},
                    "weight": 0.0,
                }
            )


class OrbitConverter:
    @staticmethod
    def convert(data: bytes, source_doc_id, call_context=None):
        ThotLogger.debug("Call Orbit Converter", context=call_context)
        """convert csv line of orbit extract to tkeir content

        Args:
            data (bytes): document in byte format
            source_doc_id ([type]): source of the document

        Returns:
            [dict]: tkeir document 
        """
        csv.field_size_limit(sys.maxsize)
        csv_keep = {
            2: {"value": "publication-number", "rule": callback_simplestorage, "kg": True},
            5: {"value": "priority-date", "rule": callback_simplestorage, "kg": True},
            6: {"value": "application-date", "rule": callback_simplestorage, "kg": True},
            7: {"value": "publication-date", "rule": callback_simplestorage, "kg": True},
            10: {"value": "title", "rule": callback_cut_after_pipe, "kg": False},
            11: {"value": "abstract", "rule": callback_cut_after_pipe, "kg": True},
            12: {"value": "current-assignee", "rule": callback_simplestorage, "kg": True},
            13: {"value": "inventors", "rule": callback_pipe, "kg": True},
            15: {"value": "advantages-drawback", "rule": callback_cut_after_pipe, "kg": False},
            16: {"value": "independent-claims", "rule": callback_cut_after_pipe, "kg": True},
            17: {"value": "object-of-invention", "rule": callback_cut_after_pipe, "kg": False},
            20: {"value": "claims", "rule": callback_cut_after_pipe, "kg": True},
            21: {"value": "english-description", "rule": callback_pipe, "kg": False},
            24: {"value": "cpc", "rule": callback_simplestorage, "kg": True},
            25: {"value": "ipc", "rule": callback_simplestorage, "kg": True},
            42: {"value": "original-document", "rule": callback_simplestorage, "kg": True},
        }
        line = data.decode()
        items = list(csv.reader([line]))[0]
        document = {
            "data_source": "filesystem",
            "source_doc_id": "file://" + source_doc_id + "/questel/" + items[3],
            "title": [],
            "content": [],
            "kg": [],
            "convertion": False,
        }
        for item_id in csv_keep:
            csv_keep[item_id]["rule"](document, csv_keep[item_id], items[item_id])
        return document
