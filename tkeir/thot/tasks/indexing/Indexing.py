# -*- coding: utf-8 -*-
"""Indexing

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
from copy import deepcopy
import hashlib

from thot.core.ThotLogger import ThotLogger
from thot.tasks.indexing.IndexingConfiguration import IndexingConfiguration
from thot.tasks.indexing.ESDocumentIndexer import ESDocumentIndexer
import re


class Indexing:
    def __init__(self, config: IndexingConfiguration = None):
        self.config = config
        self.pos_filter = set(["AUX", "CONJ", "CCONJ", "DET", "INTJ", "PART" "SCONJ", "SYM", "SPACE", "PRON", "PUNCT"])
        self.countIdx = 0
        ESDocumentIndexer.configure(config.configuration)

    def doc2index(self, tkeir_doc, remove_duplicate=True):
        self.countIdx=self.countIdx+1
        if ("data_source" not in tkeir_doc):
            tkeir_doc["data_source"]="Unkown/Filesystem" 
        if ("source_doc_id" not in tkeir_doc):
            source_doc_id=str(tkeir_doc["title"])+"#"+str(self.countIdx)
            tkeir_doc["source_doc_id"]=source_doc_id
        if ("data_source" in tkeir_doc) and ("source_doc_id" in tkeir_doc):
            doc2index = {
                "date":"0000-01-01",
                "position":[0,0],
                "title": [],
                "lemma_title": [],
                "content": [],
                "lemma_content": [],
                "kg": [],
                "categories": [],
                "sentiment": [],
                "summary": [],
                "text_suggester": [],
                "data_source": tkeir_doc["data_source"],
                "source_doc_id": tkeir_doc["source_doc_id"],
                "indexed_document": tkeir_doc["source_doc_id"],
            }
            hash_kg_item = set()
            uniq_suggest = set()
            for kg_item_i in tkeir_doc["kg"]:
                kg_item = deepcopy(kg_item_i)
                for triple_item in ["subject", "property", "value"]:
                    if "pos" in kg_item[triple_item]:
                        del kg_item[triple_item]["pos"]
                    if "class" not in kg_item[triple_item]:
                        kg_item[triple_item]["class"] = -1
                    for content in ["content", "lemma_content"]:
                        if (content in kg_item[triple_item]) and isinstance(kg_item[triple_item][content], list):
                            kg_item[triple_item][content] = " ".join(kg_item[triple_item][content])
                        if remove_duplicate:
                            if "positions" in kg_item[triple_item]:
                                kg_item[triple_item]["positions"] = [-1]
                m = hashlib.md5()
                m.update(str(kg_item).encode())
                hash_item = m.hexdigest()
                if hash_item not in hash_kg_item:
                    hash_kg_item.add(hash_item)
                    doc2index["kg"].append(kg_item)
            kg_duplicate = set()
            for field in ["title", "content"]:
                ms_field_name = field + "_morphosyntax"
                ner_field_name = field + "_ner"
                if (ms_field_name in tkeir_doc) and tkeir_doc[ms_field_name]:
                    current_lemma_sent = ""
                    current_text_sent = ""
                    for toks in tkeir_doc[field + "_morphosyntax"]:
                        toks["lemma"] = re.sub(r"\s+", " ", toks["lemma"])
                        toks["text"] = re.sub(r"\s+", " ", toks["text"])
                        if toks["is_sent_start"]:
                            if current_text_sent:
                                doc2index[field].append(current_text_sent.strip())
                                current_text_sent = ""
                            if current_lemma_sent:
                                doc2index["lemma_" + field].append(current_lemma_sent.strip())
                                current_lemma_sent = ""
                        if toks["pos"] not in self.pos_filter:
                            current_lemma_sent = current_lemma_sent + " " + toks["lemma"]
                        current_text_sent = current_text_sent + " " + toks["text"]
                    if current_lemma_sent:
                        doc2index["lemma_" + field].append(current_lemma_sent.strip())
                    if current_text_sent:
                        doc2index[field].append(current_text_sent.strip())
                if (ner_field_name in tkeir_doc) and tkeir_doc[ner_field_name]:
                    for ner_i in tkeir_doc[ner_field_name]:
                        if ner_i["text"] not in uniq_suggest:
                            doc2index["text_suggester"].append({"input": ner_i["text"], "weight": 100})
                            uniq_suggest.add(ner_i["text"])
                        ner_data = {
                            "subject": {
                                "content": ner_i["text"],
                                "lemma_content": "",
                                "label": "",
                                "class": -1,
                                "positions": list(range(ner_i["start"], ner_i["end"])),
                            },
                            "property": {
                                "content": "rel:instanceof",
                                "lemma_content": "rel:instanceof",
                                "label": "",
                                "class": -1,
                                "positions": [-1],
                            },
                            "value": {
                                "content": ner_i["label"],
                                "lemma_content": ner_i["label"],
                                "label": ner_i["label"],
                                "class": -1,
                                "positions": [-1],
                            },
                            "automatically_fill": True,
                            "confidence": 0.0,
                            "weight": 0.0,
                            "field_type": "named-entity",
                        }
                        m = hashlib.md5()
                        m.update(str(ner_data).encode())
                        hash_item = m.hexdigest()
                        if hash_item not in kg_duplicate:
                            doc2index["kg"].append(ner_data)
                            kg_duplicate.add(hash_item)
            if doc2index["title"]:
                suggest_title = " ".join(doc2index["title"])
                if suggest_title not in uniq_suggest:
                    doc2index["text_suggester"].append({"input": suggest_title, "weight": 100})
                    uniq_suggest.add(suggest_title)
            kg_duplicate = set()
            if "keywords" in tkeir_doc:
                for kw in tkeir_doc["keywords"]:
                    if kw["text"] not in uniq_suggest:
                        doc2index["text_suggester"].append({"input": kw["text"], "weight": kw["score"]})
                        uniq_suggest.add(kw["text"])
                    if "class" not in kw:
                        kw["class"] = -1
                    kw_data = {
                        "subject": {
                            "content": kw["text"],
                            "lemma_content": "",
                            "label": "",
                            "class": kw["class"],
                            "positions": list(range(kw["span"]["start"], kw["span"]["end"])),
                        },
                        "property": {
                            "content": "rel:is_a",
                            "lemma_content": "rel:is_a",
                            "label": "",
                            "class": -1,
                            "positions": [-1],
                        },
                        "value": {
                            "content": "keyword",
                            "lemma_content": "keyword",
                            "label": "",
                            "class": -1,
                            "positions": [-1],
                        },
                        "automatically_fill": True,
                        "confidence": 0.0,
                        "weight": 0.0,
                        "field_type": "keywords",
                    }
                    m = hashlib.md5()
                    m.update(str(kw_data).encode())
                    hash_item = m.hexdigest()
                    if hash_item not in kg_duplicate:
                        doc2index["kg"].append(kw_data)
                        kg_duplicate.add(hash_item)
            if "sentiment" in tkeir_doc:
                doc2index["sentiment"] = tkeir_doc["sentiment"]
            if "zero-shot-classification" in tkeir_doc:
                doc2index["categories"] = tkeir_doc["zero-shot-classification"]
            if "summaries" in tkeir_doc:
                doc2index["summary"] = tkeir_doc["summaries"]
            if "location" in tkeir_doc:
                doc2index["location"] = tkeir_doc["location"]
            if "position" in tkeir_doc:
                doc2index["position"] = tkeir_doc["position"]
            if "date" in tkeir_doc:
                doc2index["date"] = tkeir_doc["date"]
            m = hashlib.md5()
            m.update((str(tkeir_doc["title"]) + str(tkeir_doc["content"]) + str(tkeir_doc["source_doc_id"])).encode())
            hash_id = "tkeir-id-" + m.hexdigest()
            return (hash_id, doc2index)

    def index(self, tkeir_doc, call_context=None):
        indexableDoc = self.doc2index(tkeir_doc)
        return ESDocumentIndexer.index(indexableDoc[1], doc_id=indexableDoc[0], call_context=call_context)

    def run(self, tkeir_doc, call_context=None):
        return self.index(tkeir_doc, call_context=call_context)

    def remove(self, id, call_context=None):
        return ESDocumentIndexer.delete_with_id(id, call_context=call_context)
