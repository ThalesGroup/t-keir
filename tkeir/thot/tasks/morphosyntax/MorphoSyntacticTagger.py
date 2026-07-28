# -*- coding: utf-8 -*-
"""Morphosyntactic tagger

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
import spacy
import gc


from thot.tasks.morphosyntax.MorphoSyntacticTaggerConfiguration import MorphoSyntacticTaggerConfiguration
from thot.core.Utils import ThotTokenizerToSpacy
from thot.tasks.morphosyntax import __version_morphosyntax__, __date_morphosyntax__
from thot.tasks.TaskInfo import TaskInfo


class MorphoSyntacticTagger:
    def __init__(self, config: MorphoSyntacticTaggerConfiguration = None, call_context=None):
        """Initialize tagger

        Args:
            config (MorphoSyntacticTaggerConfiguration, optional): The tagger configuration. Defaults to None.

        Raises:
            ValueError: If configuration is not set
            ValueError: If language is not managed
        """
        if not config:
            raise ValueError("tagger configuration is mandatory")
        language = config.configuration["taggers"][0]["language"]  # TODO : management multiple language
        self._pre_tagging_with_concept = False
        self._add_concept_in_kg = False
        if "pre-tagging-with-concept" in config.configuration["taggers"][0]:
            self._pre_tagging_with_concept = config.configuration["taggers"][0]["pre-tagging-with-concept"]
        if "add-concept-in-knowledge-graph" in config.configuration["taggers"][0]:
            self._add_concept_in_kg = config.configuration["taggers"][0]["add-concept-in-knowledge-graph"]
        if language == "en":
            self._nlp = spacy.load("en_core_web_md")
        elif language == "fr":
            self._nlp = spacy.load("fr_core_news_md")
        else:
            raise ValueError("Language is not managed")
        self._nlp.tokenizer = ThotTokenizerToSpacy(self._nlp.vocab, config.configuration["taggers"], call_context=call_context)
        self._count_run = 0

    def _retag_punct(self, tok):
        if tok["text"] in ["*", ",", ";", "?", "!", "/"]:
            tok["pos"] = "PUNCT"
        return tok

    def _do_concept(self, position, text, lemma, concept, concept_label):
        return {
            "subject": {"content": text, "lemma_content": lemma, "class": -1, "positions": [position]},
            "property": {"content": "rel:has-concept", "lemma_content": "rel:has-concept", "class": -1, "positions": [-1]},
            "value": {"content": concept, "lemma_content": concept, "class": -1, "positions": [-1], "label": concept_label},
            "automatically_fill": True,
            "confidence": 0.0,
            "weight": 0.0,
            "field_type": "concept",
        }

    def tag(self, tkeir_doc: dict):
        """POS tag the tkeir document

        Args:
            tkeir_doc (dict): the document to tag in tkeir format

        Returns:
            [dict]: the document in tkeir format with POS tags
        """
        doc_title = []
        doc_content = []
        if ("title_tokens" not in tkeir_doc) and ("content_tokens" not in tkeir_doc):
            raise ValueError("Tagger need title_tokens and/or content_tokens fields")
        if "title_tokens" in tkeir_doc:
            titleDoc = self._nlp.tokenizer(tkeir_doc["title_tokens"])
            doc_title = self._nlp(titleDoc, disable=["parser", "ner"])
        if "content_tokens" in tkeir_doc:
            contentDoc = self._nlp.tokenizer(tkeir_doc["content_tokens"])
            doc_content = self._nlp(contentDoc, disable=["parser", "ner"])
        title = []
        content = []
        kg = []
        for tok_i in doc_title:
            tok_assign = {
                "pos": tok_i.pos_,
                "lemma": tok_i.lemma_,
                "text": tok_i.text,
                "is_oov": tok_i.is_oov,
                "is_sent_start": tok_i.is_sent_start,
            }
            title.append(self._retag_punct(tok_assign))
            if self._add_concept_in_kg:
                for concept_i in tok_i._.advanced_tag:
                    for concept_label in concept_i:
                        if concept_i[concept_label]["type"] == "concept":
                            if "concept" in concept_i[concept_label]:
                                kg.append(
                                    self._do_concept(
                                        tok_i.i, tok_i.text, tok_i.lemma_, [concept_i[concept_label]["concept"]], concept_label
                                    )
                                )
        for tok_i in doc_content:
            tok_assign = {
                "pos": tok_i.pos_,
                "lemma": tok_i.lemma_,
                "text": tok_i.text,
                "is_oov": tok_i.is_oov,
                "is_sent_start": tok_i.is_sent_start,
            }
            content.append(self._retag_punct(tok_assign))
            if self._add_concept_in_kg:
                for concept_i in tok_i._.advanced_tag:
                    for concept_label in concept_i:
                        if concept_i[concept_label]["type"] == "concept":
                            if "concept" in concept_i[concept_label]:
                                kg.append(
                                    self._do_concept(
                                        tok_i.i, tok_i.text, tok_i.lemma_, [concept_i[concept_label]["concept"]], concept_label
                                    )
                                )
        tkeir_doc["title_morphosyntax"] = title
        tkeir_doc["content_morphosyntax"] = content
        if kg:
            if "kg" not in tkeir_doc:
                tkeir_doc["kg"] = []
            tkeir_doc["kg"] = tkeir_doc["kg"] + kg
        taskInfo = TaskInfo(task_name="morphosyntax", task_version=__version_morphosyntax__, task_date=__date_morphosyntax__)
        tkeir_doc = taskInfo.addInfo(tkeir_doc)
        # prevent memory leak
        self._count_run = self._count_run + 1
        if self._count_run > 100:
            gc.collect()
            self._count_run = 0
        return tkeir_doc

    def run(self, tkeir_doc):
        return self.tag(tkeir_doc)
