# -*- coding: utf-8 -*-
"""NER Tagger 

Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
import os
import pickle
from subprocess import call

import traceback
import json
import gc

import spacy
from spacy.tokens import Span


from thot.tasks.ner.NERTaggerConfiguration import NERTaggerConfiguration
from thot.core.ThotLogger import ThotLogger
import thot.core.Constants as Constants
from thot.core.Utils import ThotTokenizerToSpacy
from thot.core.DictionaryTrie import Trie
from thot.tasks.ner import __version_ner__, __date_ner__
from thot.tasks.TaskInfo import TaskInfo


class SpacyNERFromMWE:
    def __init__(self, config: dict = None, call_context=None):
        if not config:
            raise ValueError("Spacy NER module needs ner configuration")
        self._mwes = None

        try:
            mwefile = os.path.join(config["label"][0]["resources-base-path"], config["label"][0]["mwe"])
            ThotLogger.info("Load mwe:" + mwefile, context=call_context)
            with open(mwefile, "rb") as pattern_f:
                self._mwes = pickle.load(pattern_f)
        except Exception as e:
            ThotLogger.warning(
                "Exception occured.",
                trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
                context=call_context,
            )

    def __call__(self, doc):
        """Call tokenizer trought spacy pipeline

        Args:
            doc ([spacy.Doc]): The spacy doc analyzer

        Returns:
            [span like ne]: named entities
        """
        ners = []
        tok_idx = 0
        for mwe_tok in doc:
            # document is already tokenized with mwe : just recreate tokens
            if mwe_tok["pos"] not in ["PART", "DET", "CONJ", "CCONJ", "VERB", "AUX", "ADV", "ADP", "PUNCT", "NUM", "PRON"]:
                toks = mwe_tok["text"].split(" ")
                trie = self._mwes["trie"]
                mwe_found = True
                for tok_i in toks:
                    if tok_i.lower() in trie:
                        trie = trie[tok_i.lower()]
                    else:
                        mwe_found = False
                        break
                if mwe_found and Trie.LEAF in trie:
                    best_label = ""
                    best_weight = -1
                    for label in trie[Trie.LEAF]["label_info"]:
                        if trie[Trie.LEAF]["label_info"][label]["weight"] > best_weight:
                            best_label = label
                            best_weight = trie[Trie.LEAF]["label_info"][label]["weight"]
                    if best_label:
                        ners.append({"start": tok_idx, "end": tok_idx + 1, "label": best_label, "text": mwe_tok["text"]})
            tok_idx = tok_idx + 1
        return ners


class NERTagger:
    def __init__(self, config: NERTaggerConfiguration = None, call_context=None):
        """Initialize tagger

        Args:
            config (NERTaggerConfiguration, optional): The tagger configuration. Defaults to None.

        Raises:
            ValueError: If configuration is not set
            ValueError: If language is not managed
        """
        if not config:
            raise ValueError("label configuration is mandatory")
        language = config.configuration["label"][0]["language"]  # TODO : management multiple language
        self._unwanted_entities_punct = set(["<", ">", "!", "?", "[", "]", "{", "}", "=", "+", "/", "\\", ";", ",", "|", "#"])
        self._config = config
        if language == "fr":
            self._nlp = spacy.load("fr_core_news_md")
            self._entities_mapping = {
                "PERSON": "person",
                "PER": "person",
                "ORG": "organization",
                "LOC": "location",
                "MISC": "misc",
                "url": "url",
                "email": "email",
                "cite_person": "cite_person",
            }

        elif language == "en":
            self._nlp = spacy.load("en_core_web_md")
            self._entities_mapping = {
                "PER": "person",
                "PERSON": "person",
                "ORG": "organization",
                "GPE": "location",
                "LOC": "location",
                "PRODUCT": "product",
                "FAC": "facility",
                "EVENT": "event",
                "MONEY": "money",
                "QUANTITY": "quantity",
                "DATE": "date",
                "TIME": "time",
                "url": "url",
                "email": "email",
                "cite_person": "cite_person",
            }
        else:
            raise ValueError("Language is not managed")

        self._nlp.tokenizer = ThotTokenizerToSpacy(self._nlp.vocab, config.configuration["label"], call_context=call_context)
        self._ner_from_mwe = SpacyNERFromMWE(config=self._config.configuration, call_context=call_context)
        patterns = []
        self._ner_validation = dict()
        if "ner-rules" in self._config.configuration["label"][0]:
            ner_rules = os.path.join(
                self._config.configuration["label"][0]["resources-base-path"],
                self._config.configuration["label"][0]["ner-rules"],
            )
            ThotLogger.info("Load rules:" + ner_rules, context=call_context)
            with open(ner_rules) as json_f:
                ner_rules_data = json.load(json_f)
                if "ner-pos-validation" in ner_rules_data:
                    for rule_i in ner_rules_data["ner-pos-validation"]:
                        self._ner_validation[rule_i["label"]] = {
                            "possible": set(rule_i["possible-pos-in-syntagm"]),
                            "at-least": set(rule_i["at-least"]),
                        }
                    ThotLogger.info("[" + str(len(self._ner_validation)) + "] Validation rules Loaded.", context=call_context)
                if "rule-based-ner" in ner_rules_data:
                    for rule in ner_rules_data["rule-based-ner"]:                        
                        patterns.append({"label":rule["label"],"pattern":rule["pattern"]})
                    
        self._count_run = 0
        ruler = self._nlp.add_pipe("entity_ruler")
        ruler.add_patterns(patterns)


    def discard_ner(self, ent_i, doc, with_mapping=True):
        discard_ner_entry = False
        ner_label = ent_i.label_
        if with_mapping:
            ner_label = self._entities_mapping[ent_i.label_]
        if ((ent_i.end - ent_i.start) == 1) and (
            doc[ent_i.start].pos_ in ["PART", "DET", "CONJ", "CCONJ", "VERB", "AUX", "ADV", "ADP", "PUNCT", "NUM", "PRON"]
        ):
            discard_ner_entry = True
        if (not discard_ner_entry) and (ner_label in self._ner_validation):
            pos_table = set()
            for tok in ent_i:
                pos_table.add(tok.pos_)
            validation = self._ner_validation[ner_label]["possible"] & pos_table
            if len(validation) == len(pos_table):
                validation = self._ner_validation[ner_label]["at-least"] & pos_table
                discard_ner_entry = len(validation) == 0
            else:
                discard_ner_entry = True
        return discard_ner_entry

    def tag(self, tkeir_doc: dict):
        """Extract an tag in named entities

        Args:
            tkeir_doc (dict): the input document in tkeir format

        Returns:
            [dict]: a tkeir document with named entities
        """
        doc_title = []
        doc_content = []
        if "title_tokens" in tkeir_doc:
            doc = self._nlp.tokenizer(tkeir_doc["title_tokens"])
            doc_title = self._nlp(doc, disable=["tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer"])
        if "content_tokens" in tkeir_doc:
            doc = self._nlp.tokenizer(tkeir_doc["content_tokens"])
            doc_content = self._nlp(doc, disable=["tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer"])
        title = []
        content = []
        tkeir_doc["error"] = False
        if (not doc_title) and (not doc_content):
            tkeir_doc["error"] = True
            raise ValueError("Tagger need title_tokens and/or content_tokens fields")
        if doc_title:
            len_doc = len(doc_title)
            if "title_morphosyntax" not in tkeir_doc:
                raise ValueError("Morphosyntactic tagger MUST be applied")
            if len_doc:
                with doc_title.retokenize() as retokenizer:
                    for token_i in range(len_doc):
                        attrs = {
                            "POS": tkeir_doc["title_morphosyntax"][token_i]["pos"],
                            "LEMMA": tkeir_doc["title_morphosyntax"][token_i]["lemma"],
                        }
                        retokenizer.merge(doc_title[token_i : token_i + 1], attrs=attrs)
            for ent_i in doc_title.ents:
                if ent_i.label_ in self._entities_mapping:
                    discard_ner_entry = self.discard_ner(ent_i, doc_title)
                    if not discard_ner_entry:
                        title.append(
                            {
                                "start": ent_i.start,
                                "end": ent_i.end,
                                "label": self._entities_mapping[ent_i.label_],
                                "text": ent_i.text,
                            }
                        )
        if doc_content:
            len_doc = len(doc_content)
            if len_doc:
                if "content_morphosyntax" not in tkeir_doc:
                    raise ValueError("Morphosyntactic tagger MUST be applied")
                with doc_content.retokenize() as retokenizer:
                    for token_i in range(len_doc):
                        attrs = {
                            "POS": tkeir_doc["content_morphosyntax"][token_i]["pos"],
                            "LEMMA": tkeir_doc["content_morphosyntax"][token_i]["lemma"],
                        }
                        retokenizer.merge(doc_content[token_i : token_i + 1], attrs=attrs)

            for ent_i in doc_content.ents:
                if ent_i.label_ in self._entities_mapping:
                    discard_ner_entry = self.discard_ner(ent_i, doc_content)
                    if not discard_ner_entry:
                        content.append(
                            {
                                "start": ent_i.start,
                                "end": ent_i.end,
                                "label": self._entities_mapping[ent_i.label_],
                                "text": ent_i.text,
                            }
                        )

        mwe_ner_content = []
        mwe_ner_title = []
        if "content_morphosyntax" in tkeir_doc:
            mwe_ner_content = self._ner_from_mwe(tkeir_doc["content_morphosyntax"])
        if "title_morphosyntax" in tkeir_doc:
            mwe_ner_title = self._ner_from_mwe(tkeir_doc["title_morphosyntax"])
        for ner_title in mwe_ner_title:
            has_overlap = False
            for cmp_ner in title:
                if (
                    ((ner_title["start"] <= cmp_ner["start"]) and (ner_title["end"] <= cmp_ner["end"]))
                    or ((ner_title["start"] >= cmp_ner["start"]) and (ner_title["end"] <= cmp_ner["end"]))
                    or ((ner_title["start"] <= cmp_ner["end"]) and (ner_title["end"] >= cmp_ner["end"]))
                ):
                    has_overlap = True
            if not has_overlap:
                ent = Span(doc_title, start=ner_title["start"], end=ner_title["end"], label=ner_title["label"])
                if not self.discard_ner(ent, doc_title, with_mapping=False):
                    title.append(ner_title)
        for ner_content in mwe_ner_content:
            has_overlap = False
            for cmp_ner in content:
                if (
                    ((ner_content["start"] <= cmp_ner["start"]) and (ner_content["end"] <= cmp_ner["end"]))
                    or ((ner_content["start"] >= cmp_ner["start"]) and (ner_content["end"] <= cmp_ner["end"]))
                    or ((ner_content["start"] <= cmp_ner["end"]) and (ner_content["end"] >= cmp_ner["end"]))
                ):
                    has_overlap = True
            if not has_overlap:
                ent = Span(doc_content, start=ner_content["start"], end=ner_content["end"], label=ner_content["label"])
                if not self.discard_ner(ent, doc_content, with_mapping=False):
                    content.append(ner_content)
        tkeir_doc["title_ner"] = title
        tkeir_doc["content_ner"] = content
        taskInfo = TaskInfo(task_name="ner", task_version=__version_ner__, task_date=__date_ner__)
        tkeir_doc = taskInfo.addInfo(tkeir_doc)
        # prevent memory leak
        self._count_run = self._count_run + 1
        if self._count_run > 100:
            self._count_run = 0
            gc.collect()
        return tkeir_doc

    def run(self, tkeir_doc):
        return self.tag(tkeir_doc)
