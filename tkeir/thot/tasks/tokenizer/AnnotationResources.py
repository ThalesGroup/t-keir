# -*- coding: utf-8 -*-
"""Annotation resources
It reads a configuration file in JSON format. This file contains link to resources (like list, syntactic dictionary ..)

Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import os
import sys
import string
import pickle
import traceback
import tempfile
import pandas as pd
from fold_to_ascii import fold

import requests
import zipfile


dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))

from thot.core.ThotLogger import ThotLogger
from thot.core.DictionaryTrie import Trie
from thot.tasks.tokenizer import __version_tokenizer__, __date_tokenizer__


class AnnotationResources:
    """Create an annotation Trie structure according the configuration file"""

    @staticmethod
    def createModel(configuration=None, output=None):
        """Initialize resources and create directory architecture if need
        :param configfile: configuration file
        :param outputfile
        """
        if not configuration:
            raise ValueError("Annotation description is mandatory")
        if not output:
            raise ValueError("Output file is mandatory")

        if "data" in configuration:
            for data_i in configuration["data"]:
                # create directories
                patterns = []
                basepath = configuration["resources-base-path"]
                if "lists" in data_i:
                    remove_duplicate = set()
                    for list_item in data_i["lists"]:
                        concept_type = dict()
                        pattern_exception = set()
                        list_patterns = []
                        if "download" in list_item:
                            if "url" in list_item["download"]:
                                try:
                                    r = requests.get(list_item["download"]["url"])
                                    tmpzip = os.path.join(tempfile.gettempdir(), "tmp.zip")
                                    with open(tmpzip, "wb") as fzip:
                                        fzip.write(r.content)
                                        fzip.close()
                                    z = zipfile.ZipFile(tmpzip)
                                    ThotLogger.info("Extract to [" + configuration["resources-base-path"] + "]")
                                    z.extractall(path=configuration["resources-base-path"])
                                    z.close()
                                    os.remove(tmpzip)

                                except Exception as e:
                                    ThotLogger.error(
                                        "Cannot download '"
                                        + list_item["download"]["url"]
                                        + "' exception:"
                                        + str(e)
                                        + ", trace:"
                                        + str(traceback.format_exc())
                                    )
                            else:
                                ThotLogger.error("With download option you must give url")
                        if "name" in list_item:
                            ThotLogger.info("Load '" + list_item["name"] + "'")
                        if "exceptions" in list_item:
                            if not isinstance(list_item["exceptions"], list):
                                list_item["exceptions"] = [list_item["exceptions"]]
                            for except_i in list_item["exceptions"]:
                                try:
                                    with open(os.path.join(basepath, except_i)) as exc_f:
                                        pattern_exception = set(exc_f.read().split("\n"))
                                        exc_f.close()
                                except Exception as e:
                                    ThotLogger.error("Cannot open file '" + except_i + "'")

                        if ("path" in list_item) and os.path.isfile(os.path.join(basepath, list_item["path"])):
                            label = None
                            pos = "NOUN"
                            weight = 1
                            if "label" in list_item:
                                label = list_item["label"]
                            else:
                                ThotLogger.error("Label must be set")
                            if "pos" in list_item:
                                pos = list_item["pos"]
                            else:
                                ThotLogger.warning("POS should be set, default is NOUN")
                            if "weight" in list_item:
                                weight = list_item["weight"]

                            if label and ("format" in list_item):
                                if "type" in list_item["format"]:
                                    if (list_item["format"]["type"] == "csv") or (list_item["format"]["type"] == "csv-zip"):
                                        if list_item["format"]["type"] == "csv-zip":
                                            z = zipfile.ZipFile(os.path.join(basepath, list_item["path"]))
                                            ThotLogger.info("Extract to [" + configuration["resources-base-path"] + "]")
                                            z.extractall(path=basepath)
                                            z.close()
                                            list_item["path"] = list_item["path"].replace(".zip", "")
                                        sep = ","
                                        try:
                                            if "sep" in list_item["format"]:
                                                sep = list_item["format"]["sep"]
                                            if ("headers" in list_item["format"]) and (not list_item["format"]["header"]):
                                                df = pd.read_csv(
                                                    os.path.join(basepath, list_item["path"]), sep=sep, header=None
                                                )
                                            else:
                                                df = pd.read_csv(os.path.join(basepath, list_item["path"]), sep=sep)
                                            columns = dict()
                                            list_concepts = []
                                            concept_parent_col = -1
                                            if "columns" in list_item["format"]:
                                                for column_i in list_item["format"]["columns"]:
                                                    if "id" in column_i:
                                                        spliton = ""
                                                        if "split-on" in column_i:
                                                            spliton = column_i["split-on"]
                                                        columns[int(column_i["id"])] = spliton
                                                        if "concept-type" in column_i:
                                                            concept_type[int(column_i["id"])] = column_i["concept-type"]
                                                            if column_i["concept-type"] == "parent-instance":
                                                                concept_parent_col = int(column_i["id"])
                                                        columns[int(column_i["id"])] = spliton
                                                    else:
                                                        ThotLogger.error("CSV column id undefined")
                                            else:
                                                for col_i in range(len(df.columns)):
                                                    columns[col_i] = ""
                                            concept_col_list = []
                                            if concept_parent_col != -1:
                                                concept_col_list = list(df.iloc[:, concept_parent_col].values)
                                            for col_i in columns:
                                                try:
                                                    if not columns[col_i]:
                                                        term_list = list(df.iloc[:, col_i].values)
                                                        list_patterns = list_patterns + term_list
                                                        if concept_parent_col != -1:
                                                            list_concepts = list_concepts + concept_col_list
                                                    else:
                                                        rows_to_split = list(df.iloc[:, col_i].values)
                                                        for ri_id in range(len(rows_to_split)):
                                                            ri = rows_to_split[ri_id]
                                                            if isinstance(ri, str):
                                                                multiple_pattern = ri.split(columns[col_i])
                                                                for mpi in multiple_pattern:
                                                                    list_patterns.append(mpi)
                                                                if concept_parent_col != -1:
                                                                    list_concepts.append(concept_col_list[ri_id])
                                                except Exception as e:
                                                    ThotLogger.error(
                                                        "Error int file '"
                                                        + list_item["path"]
                                                        + "' Exception:"
                                                        + str(e)
                                                        + ", Trace:"
                                                        + str(traceback.format_exc())
                                                    )
                                        except Exception as e:
                                            ThotLogger.error(
                                                "Error int file '"
                                                + list_item["path"]
                                                + "' Exception:"
                                                + str(e)
                                                + ", Trace:"
                                                + str(traceback.format_exc())
                                            )
                                    elif list_item["format"]["type"] == "list":
                                        with open(os.path.join(basepath, list_item["path"])) as list_f:
                                            list_patterns = list_f.read().split("\n")
                                            list_f.close()
                                else:
                                    ThotLogger.error("Format is not defined, not type.")
                            else:
                                ThotLogger.error("Format is not defined.")
                        else:
                            ThotLogger.error("Resource file problem")
                        ThotLogger.info("Add [" + str(len(list_patterns)) + "] items from [" + list_item["path"] + "]")
                        for e_i in range(len(list_patterns)):
                            pattern_i = list_patterns[e_i].lower()
                            word_with_punct = set(pattern_i) & set(string.punctuation + "0123456789 ")
                            pattern_set_len = len(set(pattern_i))
                            # only punctuations, spaces and number : skip
                            if len(word_with_punct) == pattern_set_len:
                                continue
                            data_type = "named-entity"
                            add_ascii_folding = False
                            if "add-ascii-folding" in list_item:
                                add_ascii_folding = list_item["add-ascii-folding"]
                            if "type" in list_item:
                                data_type = list_item["type"]
                            if list_patterns[e_i] not in pattern_exception:
                                duplicate_id = pattern_i + "#" + label + "#" + pos
                                if duplicate_id not in remove_duplicate:
                                    patterns.append(
                                        {
                                            "pattern": pattern_i,
                                            "label": label,
                                            "pos": pos,
                                            "data": {"type": data_type},
                                            "weight": weight,
                                        }
                                    )
                                    if concept_type:
                                        patterns[-1]["data"]["concept"] = list_concepts[e_i]
                                    remove_duplicate.add(duplicate_id)
                                if add_ascii_folding:
                                    duplicate_id = fold(pattern_i) + "#" + label + "#" + pos
                                    if duplicate_id not in remove_duplicate:
                                        fold_pattern = fold(pattern_i)
                                        if len(fold_pattern) == len(pattern_i):
                                            patterns.append(
                                                {
                                                    "pattern": fold_pattern,
                                                    "label": label,
                                                    "pos": pos,
                                                    "data": {"type": data_type},
                                                    "weight": weight,
                                                }
                                            )
                                        remove_duplicate.add(duplicate_id)
                count_patterns = len(patterns)
                words_hash = set()
                delete_pattern = set()
                for p_i in range(count_patterns):
                    lower_pattern = []
                    asHyphen = False
                    hyphen_letter = "-"
                    if len(patterns[p_i]["pattern"]) > 2048:
                        ThotLogger.error("Sequence '" + patterns[p_i]["pattern"] + "' too long")
                        delete_pattern.add(p_i)
                        continue
                    if "-" in patterns[p_i]["pattern"]:
                        asHyphen = True
                    if "&" in patterns[p_i]["pattern"]:
                        asHyphen = True
                        hyphen_letter = "&"
                    entity_items = patterns[p_i]["pattern"].split(" ")

                    if len(entity_items) == 1:
                        word_with_punct = set(patterns[p_i]["pattern"]) & set(string.punctuation + "0123456789")
                        pattern_set_len = len(set(patterns[p_i]["pattern"]))
                        pattern_len = len(patterns[p_i]["pattern"])
                        if (pattern_len < 512) and len(word_with_punct) and (len(word_with_punct) != pattern_set_len):
                            words_hash.add(patterns[p_i]["pattern"].lower())
                    patterns[p_i]["pattern"] = tuple(entity_items)
                    patterns[p_i]["in_vocab"] = True
                    if asHyphen:
                        lower_pattern = []
                        for e_i in entity_items:
                            if hyphen_letter in e_i:
                                toks = e_i.split(hyphen_letter)
                                for ti in range(len(toks)):
                                    lower_pattern.append(toks[ti].lower())
                                    if ti != (len(toks) - 1):
                                        lower_pattern.append(hyphen_letter)
                            else:
                                lower_pattern.append(e_i.lower())
                        patterns.append(
                            {
                                "label": patterns[p_i]["label"],
                                "pattern": tuple(lower_pattern),
                                "pos": patterns[p_i]["pos"],
                                "data": patterns[p_i]["data"],
                                "weight": patterns[p_i]["weight"],
                                "in_vocab": True,
                            }
                        )
                max_pattern_length = 0
                max_word_len = 0
                for pi in patterns:
                    if len(pi) > max_pattern_length:
                        max_pattern_length = len(pi)
                for w in words_hash:
                    if len(w) > max_word_len:
                        max_word_len = len(w)
                pruned_patterns = []
                for pi in range(len(patterns)):
                    if pi not in delete_pattern:
                        pruned_patterns.append(patterns[pi])

                mwes = Trie(pruned_patterns)
                mwes_data = {
                    "punctuated-words": list(words_hash),
                    "trie": mwes,
                    "max-pattern-length": max_pattern_length,
                    "max-word-length": max_word_len,
                    "version": __version_tokenizer__,
                    "date": __date_tokenizer__,
                }
                ThotLogger.info(
                    "Save '"
                    + output
                    + "' with '"
                    + str(len(patterns))
                    + "' patterns and a max size of '"
                    + str(max_pattern_length)
                    + "'"
                    + " and '"
                    + str(len(words_hash))
                    + "' simple words with a size max of '"
                    + str(max_word_len)
                    + "'. "
                )
                with open(output, "wb") as pd_f:
                    pickle.dump(mwes_data, pd_f)
                    pd_f.close()
                """
                import json
                with open(output+".json","w") as pd_f:
                    json.dump(mwes_data, pd_f,indent=1)
                    pd_f.close()
                """
