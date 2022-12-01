# -*- coding: utf-8 -*-
"""Syntax tagger 
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
import os
import json
import collections
from operator import attrgetter
from typing import Iterable, List, Optional, Pattern, Tuple
import gc

import spacy
import numpy
import hashlib
from spacy.tokens import Doc, Span, Token
from spacy.matcher import Matcher
from spacy.symbols import (
    AUX,
    VERB,
    agent,
    attr,
    aux,
    auxpass,
    csubj,
    csubjpass,
    dobj,
    neg,
    nsubj,
    nsubjpass,
    obj,
    pobj,
    xcomp,
)
from thot.tasks.syntax.SyntacticTaggerConfiguration import SyntacticTaggerConfiguration
from thot.core.Utils import ThotTokenizerToSpacy
from thot.core.ThotLogger import ThotLogger
from thot.tasks.TaskInfo import TaskInfo
from thot.tasks.syntax import __version_syntax__, __date_syntax__


import warnings

warnings.filterwarnings("ignore")

from spacy.attrs import LOWER, POS, ENT_TYPE, IS_ALPHA


def remove_tokens_on_match(doc):
    indexes = []
    for index, token in enumerate(doc):
        if token.pos_ in ("SPACE"):
            indexes.append(index)
    np_array = doc.to_array([LOWER, POS, ENT_TYPE, IS_ALPHA])
    np_array = numpy.delete(np_array, indexes, axis=0)
    doc2 = Doc(doc.vocab, words=[t.text for i, t in enumerate(doc) if i not in indexes])
    doc2.from_array([LOWER, POS, ENT_TYPE, IS_ALPHA], np_array)
    return doc2


SVOTriple: Tuple[List[Token], List[Token], List[Token]] = collections.namedtuple("SVOTriple", ["subject", "verb", "object"])

_NOMINAL_SUBJ_DEPS = {"nsubj", "nsubjpass"}
_CLAUSAL_SUBJ_DEPS = {"csubj", "csubjpass"}
_VERB_MODIFIER_DEPS = {"aux", "auxpass", "neg"}


class SyntacticTagger:
    def __init__(self, config: SyntacticTaggerConfiguration = None, call_context=None):
        """Initialize tagger

        Args:
            config (SyntacticTaggerConfiguration, optional): The tagger configuration. Defaults to None.

        Raises:
            ValueError: If configuration is not set
            ValueError: If language is not managed
        """
        if not config:
            raise ValueError("tagger configuration is mandatory")
        language = config.configuration["taggers"][0]["language"]  # TODO : management multiple language
        if language == "en":
            self._nlp = spacy.load("en_core_web_md")
        elif language == "fr":
            self._nlp = spacy.load("fr_core_news_md")
        else:
            raise ValueError("Language is not managed")
        self._nlp.tokenizer = ThotTokenizerToSpacy(self._nlp.vocab, config.configuration["taggers"])

        self.NUMERIC_NE_TYPES = {"ORDINAL", "CARDINAL", "MONEY", "QUANTITY", "PERCENT", "TIME", "DATE"}
        self.SUBJ_DEPS = {"csubj", "csubjpass", "expl", "nsubj", "nsubjpass", "rsubj"}
        self.OBJ_DEPS = {"attr", "dobj", "dative", "oprd", "obj", "pobj", "iobj"}
        self.AUX_DEPS = {"aux", "auxpass", "neg"}

        if ("resources-base-path" in config.configuration["taggers"][0]) and (
            "syntactic-rules" in config.configuration["taggers"][0]
        ):
            with open(
                os.path.join(
                    config.configuration["taggers"][0]["resources-base-path"],
                    config.configuration["taggers"][0]["syntactic-rules"],
                )
            ) as rules_f:
                ThotLogger.info("Load Syntactic Rules", context=call_context)
                rules = json.load(rules_f)
                rules_f.close()
                self._matcher = Matcher(self._nlp.vocab)
                self._basic_types = set(["subject", "predicate", "object"])
                self._custom_svo = []
                self._rule_type = dict()
                self._named_entity_list = set()
                self._link_rules = dict()
                self._rule_settings = {
                    "suppress-bounds-sw": False,
                    "pos-to-suppress": set(
                        [
                            "ADP",
                            "ADV",
                            "AUX",
                            "CONJ",
                            "CCONJ",
                            "DET",
                            "INTJ",
                            "PART",
                            "SCONJ",
                            "SYM",
                            "SPACE",
                            "X",
                            "PRON",
                            "PUNCT",
                        ]
                    ),
                }

                for r_i in rules:
                    # rule is in triple
                    if r_i == "settings":
                        if "suppress-bounds-sw" in rules["settings"]:
                            self._rule_settings["suppress-bounds-sw"] = rules["settings"]["suppress-bounds-sw"]
                        if "pos-to-suppress" in rules["settings"]:
                            self._rule_settings["pos-to-suppress"] = rules["settings"]["pos-to-suppress"]
                    else:
                        if set(rules[r_i]["type"]) & self._basic_types:
                            self._matcher.add(r_i, rules[r_i]["rule"], greedy="LONGEST")
                            self._rule_type[r_i] = set(rules[r_i]["type"])

                        elif "triple" in set(rules[r_i]["type"]):
                            self._svo_patterns = rules[r_i]["rule"]

                        elif "named-entity-list" in set(rules[r_i]["type"]):
                            self._named_entity_list = set(rules[r_i]["list"])
                            self._rule_type[r_i] = set(rules[r_i]["type"])

                        elif "link" in set(rules[r_i]["type"]):
                            rule_id = (
                                rules[r_i]["rule"][0]["match-rule"]
                                + "#"
                                + rules[r_i]["rule"][0]["end-with"]
                                + "##"
                                + rules[r_i]["rule"][1]["match-rule"]
                                + "#"
                                + rules[r_i]["rule"][1]["start-with"]
                            )
                            self._link_rules[rule_id] = rules[r_i]
        else:
            self._rules = None
            self._matcher = None

        self._cache_svos = set()
        self._count_run = 0

    def linkRule(self, span_left, span_right):
        rule_applied = False
        for link_rule in self._link_rules:
            rule = self._link_rules[link_rule]
            if (
                (span_left.label_ == rule["rule"][0]["match-rule"])
                and (span_right.label_ == rule["rule"][1]["match-rule"])
                and (span_left[-1].pos_ == rule["rule"][0]["end-with"])
                and (span_right[0].pos_ == rule["rule"][1]["start-with"])
            ):
                action = rule["action"]
                if action["on"] == "span-right":
                    if action["shift"] == "right":
                        span_right.start = span_right.start + 1
                    elif action["shift"] == "left":
                        span_right.start = span_right.start - 1
                    rule_applied = True
                if action["on"] == "span-left":
                    if action["shift"] == "right":
                        span_left.start = span_left.start + 1
                    elif action["shift"] == "left":
                        span_left.start = span_left.start - 1
                    rule_applied = True
        return rule_applied

    def expand_noun(self, tok: Token) -> List[Token]:
        tok_and_conjuncts = [tok] + list(tok.conjuncts)
        compounds = [child for tc in tok_and_conjuncts for child in tc.children if child.dep_ == "compound"]
        return tok_and_conjuncts + compounds

    def expand_verb(self, tok: Token) -> List[Token]:
        """Expand a verb token to include all associated auxiliary and negation tokens."""
        verb_modifiers = [child for child in tok.children if child.dep_ in _VERB_MODIFIER_DEPS]
        return [tok] + verb_modifiers

    def dependency_svo(self, doc):
        for sent in doc.sents:
            # connect subjects/objects to direct verb heads
            # and expand them to include conjuncts, compound nouns, ...
            verb_sos = collections.defaultdict(lambda: collections.defaultdict(set))
            for tok in sent:
                head = tok.head
                # ensure entry for all verbs, even if empty
                # to catch conjugate verbs without direct subject/object deps
                if tok.pos_ in ["VERB", "AUX"]:
                    _ = verb_sos[tok]
                # nominal subject of active or passive verb
                if tok.dep_ in _NOMINAL_SUBJ_DEPS:
                    if head.pos_ in ["VERB", "AUX"]:
                        verb_sos[head]["subjects"].update(self.expand_noun(tok))
                # clausal subject of active or passive verb
                elif tok.dep_ in _CLAUSAL_SUBJ_DEPS:
                    if head.pos_ in ["VERB", "AUX"]:
                        verb_sos[head]["subjects"].update(tok.subtree)
                # nominal direct object of transitive verb
                elif tok.dep_ == "dobj":
                    if head.pos_ in ["VERB", "AUX"]:
                        verb_sos[head]["objects"].update(self.expand_noun(tok))
                # prepositional object acting as agent of passive verb
                elif tok.dep_ == "pobj":
                    if head.dep == agent and head.head.pos_ in ["VERB", "AUX"]:
                        verb_sos[head.head]["objects"].update(self.expand_noun(tok))
                # open clausal complement, but not as a secondary predicate
                elif tok.dep_ == "xcomp":
                    if head.pos_ in ["VERB", "AUX"] and not any(child.dep == dobj for child in head.children):
                        verb_sos[head]["objects"].update(tok.subtree)
            # fill in any indirect relationships connected via verb conjuncts
            for verb, so_dict in verb_sos.items():
                conjuncts = verb.conjuncts
                if so_dict.get("subjects"):
                    for conj in conjuncts:
                        conj_so_dict = verb_sos.get(conj)
                        if conj_so_dict and not conj_so_dict.get("subjects"):
                            conj_so_dict["subjects"].update(so_dict["subjects"])
                if not so_dict.get("objects"):
                    so_dict["objects"].update(obj for conj in conjuncts for obj in verb_sos.get(conj, {}).get("objects", []))
            # expand verbs and restructure into svo triples
            for verb, so_dict in verb_sos.items():
                if so_dict["subjects"] and so_dict["objects"]:
                    yield SVOTriple(
                        subject=sorted(so_dict["subjects"], key=attrgetter("i")),
                        verb=sorted(self.expand_verb(verb), key=attrgetter("i")),
                        object=sorted(so_dict["objects"], key=attrgetter("i")),
                    )

    def apply_link_rule(self, matches_content):
        for span_i in range(len(matches_content)):
            for span_j in range(span_i + 1, len(matches_content)):
                if matches_content[span_i].start == (matches_content[span_j].end - 1):
                    self.linkRule(matches_content[span_j], matches_content[span_i])
                if matches_content[span_j].start == (matches_content[span_i].end - 1):
                    self.linkRule(matches_content[span_i], matches_content[span_j])

    def add_svo(self, svos, svo):
        # compute cache key:
        triple_str = ""
        for triple_entry in svo:
            for alternate in triple_entry:
                for token in alternate:
                    triple_str = triple_str + "#" + str(token.i)
        md5key = hashlib.md5(triple_str.encode()).hexdigest()
        if md5key not in self._cache_svos:
            self._cache_svos.add(md5key)
            svos.append(svo)
        return svos

    def search_svos(self, matches_content):
        svos = []
        for span_i in range(len(matches_content)):
            for pattern in self._svo_patterns:
                current_span = span_i
                matched_pattern = []
                end_pattern = -1
                for item in pattern:
                    if (end_pattern != -1) and (end_pattern != matches_content[current_span].start):
                        break
                    pattern_positions = [matches_content[current_span]]
                    item_key = list(item.keys())[0]
                    possible_pattern_labels = set()
                    if "named-entity-list" in self._rule_type[item[item_key]]:
                        possible_pattern_labels = self._named_entity_list
                    else:
                        possible_pattern_labels = set([item[item_key]])
                    test_labels = set([matches_content[current_span].label_])

                    end_pattern = matches_content[current_span].end
                    next_span = current_span + 1

                    # check if next pattern overide the current one:
                    if (
                        (next_span < len(matches_content))
                        and (matches_content[next_span].start >= matches_content[current_span].start)
                        and (matches_content[next_span].end <= matches_content[current_span].end)
                    ):
                        pattern_positions.append(matches_content[next_span])
                        test_labels.add(matches_content[next_span].label_)
                        current_span = next_span
                    # check if next pattern is in current pattern
                    elif (
                        (next_span < len(matches_content))
                        and (matches_content[next_span].start == matches_content[current_span].start)
                        and (matches_content[next_span].end >= matches_content[current_span].end)
                    ):
                        pattern_positions.append(matches_content[next_span])
                        current_span = next_span
                        test_labels.add(matches_content[next_span].label_)
                        end_pattern = matches_content[next_span].end
                    if (current_span < len(matches_content)) and (test_labels & possible_pattern_labels):
                        matched_pattern.append(pattern_positions)
                        current_span = current_span + 1
                        if current_span == len(matches_content):
                            break
                    else:
                        break
                if (len(matched_pattern)) == len(pattern):
                    svos = self.add_svo(svos, matched_pattern)
        return svos

    def get_dependencies(self, content):
        deps = []
        for token in content:
            deps.append(
                {
                    "text": token.text,
                    "lemma": token.lemma_,
                    "pos": token.pos_,
                    "head": token.head.i,
                    "dep": token.dep_,
                    "lefts": [tok.i for tok in token.lefts],
                    "rights": [tok.i for tok in token.rights],
                }
            )
        return deps

    def get_relations(self, svos, field):
        triple_list = []
        no_replicate = set()
        for svo in svos:
            current_triples = []
            triple_position = 0
            for triple_entry in svo:
                sz_alt = len(triple_entry)
                sz_triple = len(current_triples)
                if sz_triple:
                    for alti in range(sz_alt):
                        alternate = triple_entry[alti]
                        item = {
                            "content": [token.text for token in alternate],
                            "lemma_content": [token.lemma_ for token in alternate],
                            "pos": [token.pos_ for token in alternate],
                            "positions": [token.i for token in alternate],
                            "label": alternate.label_,
                        }
                        if alti == 0:
                            for t in range(sz_triple):
                                current_triples[t][triple_position] = item
                        else:
                            for t in range(sz_triple):
                                current_triples.append(current_triples[t])
                                current_triples[-1][triple_position] = item
                else:
                    for alti in range(sz_alt):
                        alternate = triple_entry[alti]
                        item = {
                            "content": [token.text for token in alternate],
                            "lemma_content": [token.lemma_ for token in alternate],
                            "pos": [token.pos_ for token in alternate],
                            "positions": [token.i for token in alternate],
                            "label": alternate.label_,
                        }
                        current_triples.append([item, None, None])
                triple_position = triple_position + 1
            for ct in current_triples:
                triple_str = ""
                for item_i in ct:
                    triple_str = (
                        triple_str
                        + "#"
                        + str(item_i["content"])
                        + "#"
                        + str(item_i["pos"])
                        + "#"
                        + str(item_i["lemma_content"])
                        + "#"
                        + str(item_i["positions"])
                        + "#"
                        + str(item_i["label"])
                    )
                ct_check_sum = hashlib.md5(triple_str.encode()).hexdigest()
                if ct_check_sum not in no_replicate:
                    if self._rule_settings["suppress-bounds-sw"]:
                        for c_p_o in [0, 2]:
                            while (len(ct[c_p_o]["pos"]) > 0) and (
                                ct[c_p_o]["pos"][0] in self._rule_settings["pos-to-suppress"]
                            ):
                                del ct[c_p_o]["pos"][0]
                                del ct[c_p_o]["positions"][0]
                                del ct[c_p_o]["content"][0]
                                del ct[c_p_o]["lemma_content"][0]
                            while (len(ct[c_p_o]["pos"]) > 0) and (
                                ct[c_p_o]["pos"][-1] in self._rule_settings["pos-to-suppress"]
                            ):
                                del ct[c_p_o]["pos"][-1]
                                del ct[c_p_o]["positions"][-1]
                                del ct[c_p_o]["content"][-1]
                                del ct[c_p_o]["lemma_content"][-1]

                    discard_svo = (
                        (len(ct[0]["pos"]) == 1)
                        and (len(ct[2]["pos"]) == 1)
                        and (
                            ct[0]["pos"][0] in ["PART", "DET", "PRON", "CONJ", "CCONJ"]
                            and (ct[2]["pos"][0] in ["PART", "DET", "PRON", "CONJ", "CCONJ"])
                        )
                    )
                    if not discard_svo:
                        discard_svo = (len(ct[0]["pos"]) == 0) or (len(ct[1]["pos"]) == 0) or (len(ct[2]["pos"]) == 0)
                    if not discard_svo:
                        triple_list.append(
                            {
                                "subject": ct[0],
                                "property": ct[1],
                                "value": ct[2],
                                "automatically_fill": True,
                                "confidence": 0.0,
                                "weight": 0.0,
                                "field_type": field,
                            }
                        )
                    no_replicate.add(ct_check_sum)
        return triple_list

    def tag(self, tkeir_doc: dict):
        """POS tag the tkeir document

        Args:
            tkeir_doc (dict): the document to tag in tkeir format

        Returns:
            [dict]: the document in tkeir format with POS tags
        """
        self._cache_svos = set()
        doc_title = dict()
        search_doc_title = dict()
        doc_content = dict()
        search_doc_content = dict()
        if ("title_tokens" not in tkeir_doc) and ("content_tokens" not in tkeir_doc):
            raise ValueError("title tokens or content tokens should be set")
        if "title_tokens" in tkeir_doc:
            search_doc_title = self._nlp.tokenizer(tkeir_doc["title_tokens"])
            doc_title = self._nlp(search_doc_title, disable=["tagger", "ner", "attribute_ruler", "lemmatizer"])
        if "content_tokens" in tkeir_doc:
            search_doc_content = self._nlp.tokenizer(tkeir_doc["content_tokens"])
            doc_content = self._nlp(search_doc_content, disable=["tagger", "ner", "attribute_ruler", "lemmatizer"])
        token_i = 0

        if "kg" not in tkeir_doc:
            tkeir_doc["kg"] = []

        len_doc = len(doc_content)
        if len_doc:
            with doc_content.retokenize() as retokenizer:
                for token_i in range(len_doc):
                    attrs = {
                        "POS": tkeir_doc["content_morphosyntax"][token_i]["pos"],
                        "LEMMA": tkeir_doc["content_morphosyntax"][token_i]["lemma"],
                    }
                    retokenizer.merge(doc_content[token_i : token_i + 1], attrs=attrs)
            matches_content = self._matcher(doc_content, as_spans=True)
            self.apply_link_rule(matches_content)
            if "content_ner" in tkeir_doc:
                for span in tkeir_doc["content_ner"]:
                    add_ner = True
                    if (span["end"] - span["start"]) == 1:
                        if doc_content[span["start"]].pos_ in ["PART", "DET", "PRON", "CCONJ", "CONJ", "INT"]:
                            add_ner = False
                    if add_ner:
                        matches_content.append(Span(doc=doc_content, start=span["start"], end=span["end"], label=span["label"]))
            matches_content = sorted(matches_content, key=attrgetter("start"))
            svos_content = self.search_svos(matches_content)
            dep_svos_content = self.dependency_svo(doc_content)
            for dep_svo in dep_svos_content:
                d_subject = [Span(doc_content, start=dep_svo.subject[0].i, end=dep_svo.subject[-1].i + 1, label="dep_subject")]
                d_verb = [Span(doc_content, start=dep_svo.verb[0].i, end=dep_svo.verb[-1].i + 1, label="dep_verb")]
                d_object = [Span(doc_content, start=dep_svo.object[0].i, end=dep_svo.object[-1].i + 1, label="dep_object")]
                current_svo = [d_subject, d_verb, d_object]
                svos_content = self.add_svo(svos_content, current_svo)
            svos_content = sorted(svos_content, key=lambda x: x[0][0].start)
            tkeir_doc["content_deps"] = self.get_dependencies(doc_content)
            content_relation = self.get_relations(svos_content, "content")
            if content_relation:
                tkeir_doc["kg"] = tkeir_doc["kg"] + content_relation

        len_doc = len(doc_title)
        if len_doc:
            with doc_title.retokenize() as retokenizer:
                for token_i in range(len_doc):
                    attrs = {
                        "POS": tkeir_doc["title_morphosyntax"][token_i]["pos"],
                        "LEMMA": tkeir_doc["title_morphosyntax"][token_i]["lemma"],
                    }
                    retokenizer.merge(doc_title[token_i : token_i + 1], attrs=attrs)
            matches_title = self._matcher(doc_title, as_spans=True)
            self.apply_link_rule(matches_title)
            if "title_ner" in tkeir_doc:
                for span in tkeir_doc["title_ner"]:
                    add_ner = True
                    if (span["end"] - span["start"]) == 1:
                        if doc_title[span["start"]].pos_ in ["PART", "DET", "PRON", "CCONJ", "CONJ", "INT"]:
                            add_ner = False
                    if add_ner:
                        matches_title.append(Span(doc=doc_title, start=span["start"], end=span["end"], label=span["label"]))
            matches_title = sorted(matches_title, key=attrgetter("start"))
            svos_title = self.search_svos(matches_title)
            dep_svos_title = self.dependency_svo(doc_title)
            for dep_svo in dep_svos_title:
                d_subject = [Span(doc_title, start=dep_svo.subject[0].i, end=dep_svo.subject[-1].i + 1, label="dep_subject")]
                d_verb = [Span(doc_title, start=dep_svo.verb[0].i, end=dep_svo.verb[-1].i + 1, label="dep_verb")]
                d_object = [Span(doc_title, start=dep_svo.object[0].i, end=dep_svo.object[-1].i + 1, label="dep_object")]
                current_svo = [d_subject, d_verb, d_object]
                svos_title = self.add_svo(svos_title, current_svo)
            svos_title = sorted(svos_title, key=lambda x: x[0][0].start)
            tkeir_doc["title_deps"] = self.get_dependencies(doc_title)
            title_relation = self.get_relations(svos_title, "title")
            if title_relation:
                tkeir_doc["kg"] = tkeir_doc["kg"] + title_relation

        taskInfo = TaskInfo(task_name="syntax", task_version=__version_syntax__, task_date=__date_syntax__)
        tkeir_doc = taskInfo.addInfo(tkeir_doc)
        self._count_run = self._count_run + 1
        if self._count_run > 100:
            gc.collect()
            self._count_run = 0
        return tkeir_doc

    def run(self, tkeir_doc: dict):
        return self.tag(tkeir_doc)
