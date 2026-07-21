"""NER Tagger

Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES
All Rights Reserved.
"""

import gc
import json
import os
import pickle
import traceback

from spacy.tokens import Span

import thot.core.Constants as Constants
from thot.core.DictionaryTrie import Trie
from thot.core.SpacyModelLoader import load_spacy_model
from thot.core.ThotLogger import ThotLogger
from thot.core.Utils import ThotTokenizerToSpacy
from thot.tasks.ner import __date_ner__, __version_ner__
from thot.tasks.ner.NERTaggerConfiguration import NERTaggerConfiguration
from thot.tasks.TaskInfo import TaskInfo


class SpacyNERFromMWE:
    def __init__(self, config: dict = None, call_context=None):
        """Initialize the instance.

        Example:
            >>> callable(SpacyNERFromMWE)
            True
        """
        if not config:
            raise ValueError("Spacy NER module needs ner configuration")
        self._mwes = None

        label = config["label"][0]
        mwe_file = label.get("mwe")
        if mwe_file:
            try:
                mwefile = os.path.join(
                    label["resources-base-path"],
                    mwe_file,
                )
                ThotLogger.info("Load mwe:" + mwefile, context=call_context)
                with open(mwefile, "rb") as pattern_f:
                    self._mwes = pickle.load(pattern_f)
            except Exception as e:
                ThotLogger.warning(
                    "Exception occured.",
                    trace=Constants.exception_error_and_trace(
                        str(e), str(traceback.format_exc())
                    ),
                    context=call_context,
                )

    def __call__(self, doc):
        """Call tokenizer trought spacy pipeline

        Args:
            doc ([spacy.Doc]): The spacy doc analyzer

        Returns:
            [span like ne]: named entities

                Example:
                    >>> callable(SpacyNERFromMWE.__call__)
                    True
        """
        if not self._mwes:
            return []
        ners = []
        tok_idx = 0
        for mwe_tok in doc:
            # document is already tokenized with mwe : just recreate tokens
            if mwe_tok["pos"] not in [
                "PART",
                "DET",
                "CONJ",
                "CCONJ",
                "VERB",
                "AUX",
                "ADV",
                "ADP",
                "PUNCT",
                "NUM",
                "PRON",
            ]:
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
                        if (
                            trie[Trie.LEAF]["label_info"][label]["weight"]
                            > best_weight
                        ):
                            best_label = label
                            best_weight = trie[Trie.LEAF]["label_info"][label][
                                "weight"
                            ]
                    if best_label:
                        ners.append(
                            {
                                "start": tok_idx,
                                "end": tok_idx + 1,
                                "label": best_label,
                                "text": mwe_tok["text"],
                            }
                        )
            tok_idx = tok_idx + 1
        return ners


class NERTagger:
    def __init__(
        self, config: NERTaggerConfiguration = None, call_context=None
    ):
        """Initialize tagger

        Args:
            config (NERTaggerConfiguration, optional): The tagger configuration. Defaults to None.

        Raises:
            ValueError: If configuration is not set
            ValueError: If language is not managed

                Example:
                    >>> callable(NERTagger)
                    True
        """
        if not config:
            raise ValueError("label configuration is mandatory")
        language = config.configuration["label"][0][
            "language"
        ]  # TODO : management multiple language
        self._unwanted_entities_punct = set(
            [
                "<",
                ">",
                "!",
                "?",
                "[",
                "]",
                "{",
                "}",
                "=",
                "+",
                "/",
                "\\",
                ";",
                ",",
                "|",
                "#",
            ]
        )
        self._config = config
        if language == "fr":
            self._nlp, self._spacy_model = load_spacy_model(
                language,
                size="md",
                call_context=call_context,
                download_if_missing=True,
                task_name="ner",
            )
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
            self._nlp, self._spacy_model = load_spacy_model(
                language,
                size="md",
                call_context=call_context,
                download_if_missing=True,
                task_name="ner",
            )
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

        self._nlp.tokenizer = ThotTokenizerToSpacy(
            self._nlp.vocab,
            config.configuration["label"],
            call_context=call_context,
        )
        self._ner_from_mwe = SpacyNERFromMWE(
            config=self._config.configuration, call_context=call_context
        )
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
                    ThotLogger.info(
                        "["
                        + str(len(self._ner_validation))
                        + "] Validation rules Loaded.",
                        context=call_context,
                    )
                if "rule-based-ner" in ner_rules_data:
                    for rule in ner_rules_data["rule-based-ner"]:
                        patterns.append(
                            {
                                "label": rule["label"],
                                "pattern": rule["pattern"],
                            }
                        )

        self._count_run = 0
        ruler = self._nlp.add_pipe("entity_ruler")
        ruler.add_patterns(patterns)

    def discard_ner(self, ent_i, doc, with_mapping=True):
        """discard_ner API.

        Example:
            >>> callable(NERTagger.discard_ner)
            True
        """
        discard_ner_entry = False
        ner_label = ent_i.label_
        if with_mapping:
            ner_label = self._entities_mapping[ent_i.label_]
        if ((ent_i.end - ent_i.start) == 1) and (
            doc[ent_i.start].pos_
            in [
                "PART",
                "DET",
                "CONJ",
                "CCONJ",
                "VERB",
                "AUX",
                "ADV",
                "ADP",
                "PUNCT",
                "NUM",
                "PRON",
            ]
        ):
            discard_ner_entry = True
        if (not discard_ner_entry) and (ner_label in self._ner_validation):
            pos_table = set()
            for tok in ent_i:
                pos_table.add(tok.pos_)
            validation = (
                self._ner_validation[ner_label]["possible"] & pos_table
            )
            if len(validation) == len(pos_table):
                validation = (
                    self._ner_validation[ner_label]["at-least"] & pos_table
                )
                discard_ner_entry = len(validation) == 0
            else:
                discard_ner_entry = True
        return discard_ner_entry

    _NLP_DISABLE = [
        "tok2vec",
        "tagger",
        "parser",
        "attribute_ruler",
        "lemmatizer",
    ]

    def _nlp_from_tokens(self, tokens):
        doc = self._nlp.tokenizer(tokens)
        return self._nlp(doc, disable=self._NLP_DISABLE)

    def _apply_morphosyntax(self, doc, morphosyntax):
        len_doc = len(doc)
        with doc.retokenize() as retokenizer:
            for token_i in range(len_doc):
                attrs = {
                    "POS": morphosyntax[token_i]["pos"],
                    "LEMMA": morphosyntax[token_i]["lemma"],
                }
                retokenizer.merge(doc[token_i : token_i + 1], attrs=attrs)

    def _collect_mapped_entities(self, doc):
        entities = []
        for ent_i in doc.ents:
            if ent_i.label_ not in self._entities_mapping:
                continue
            if self.discard_ner(ent_i, doc):
                continue
            entities.append(
                {
                    "start": ent_i.start,
                    "end": ent_i.end,
                    "label": self._entities_mapping[ent_i.label_],
                    "text": ent_i.text,
                }
            )
        return entities

    def _tag_title_section(self, doc_title, tkeir_doc):
        if "title_morphosyntax" not in tkeir_doc:
            raise ValueError("Morphosyntactic tagger MUST be applied")
        if len(doc_title):
            self._apply_morphosyntax(
                doc_title, tkeir_doc["title_morphosyntax"]
            )
        return self._collect_mapped_entities(doc_title)

    def _tag_content_section(self, doc_content, tkeir_doc):
        if len(doc_content):
            if "content_morphosyntax" not in tkeir_doc:
                raise ValueError("Morphosyntactic tagger MUST be applied")
            self._apply_morphosyntax(
                doc_content, tkeir_doc["content_morphosyntax"]
            )
        return self._collect_mapped_entities(doc_content)

    def _ner_spans_overlap(self, ner_a, ner_b):
        return (
            (
                (ner_a["start"] <= ner_b["start"])
                and (ner_a["end"] <= ner_b["end"])
            )
            or (
                (ner_a["start"] >= ner_b["start"])
                and (ner_a["end"] <= ner_b["end"])
            )
            or (
                (ner_a["start"] <= ner_b["end"])
                and (ner_a["end"] >= ner_b["end"])
            )
        )

    def _merge_mwe_ners(self, mwe_ners, existing_ners, doc, target_list):
        for ner_mwe in mwe_ners:
            has_overlap = any(
                self._ner_spans_overlap(ner_mwe, cmp_ner)
                for cmp_ner in existing_ners
            )
            if has_overlap:
                continue
            ent = Span(
                doc,
                start=ner_mwe["start"],
                end=ner_mwe["end"],
                label=ner_mwe["label"],
            )
            if not self.discard_ner(ent, doc, with_mapping=False):
                target_list.append(ner_mwe)

    def tag(self, tkeir_doc: dict):
        """Extract an tag in named entities

        Args:
            tkeir_doc (dict): the input document in tkeir format

        Returns:
            [dict]: a tkeir document with named entities

                Example:
                    >>> callable(NERTagger.tag)
                    True
        """
        doc_title = []
        doc_content = []
        if "title_tokens" in tkeir_doc:
            doc_title = self._nlp_from_tokens(tkeir_doc["title_tokens"])
        if "content_tokens" in tkeir_doc:
            doc_content = self._nlp_from_tokens(tkeir_doc["content_tokens"])
        title = []
        content = []
        tkeir_doc["error"] = False
        if (not doc_title) and (not doc_content):
            tkeir_doc["error"] = True
            raise ValueError(
                "Tagger need title_tokens and/or content_tokens fields"
            )
        if doc_title:
            title = self._tag_title_section(doc_title, tkeir_doc)
        if doc_content:
            content = self._tag_content_section(doc_content, tkeir_doc)

        mwe_ner_content = []
        mwe_ner_title = []
        if "content_morphosyntax" in tkeir_doc:
            mwe_ner_content = self._ner_from_mwe(
                tkeir_doc["content_morphosyntax"]
            )
        if "title_morphosyntax" in tkeir_doc:
            mwe_ner_title = self._ner_from_mwe(tkeir_doc["title_morphosyntax"])
        self._merge_mwe_ners(mwe_ner_title, title, doc_title, title)
        self._merge_mwe_ners(mwe_ner_content, content, doc_content, content)
        tkeir_doc["title_ner"] = title
        tkeir_doc["content_ner"] = content
        taskInfo = TaskInfo(
            task_name="ner",
            task_version=__version_ner__,
            task_date=__date_ner__,
        )
        tkeir_doc = taskInfo.addInfo(tkeir_doc)
        # prevent memory leak
        self._count_run = self._count_run + 1
        if self._count_run > 100:
            self._count_run = 0
            gc.collect()
        return tkeir_doc

    def run(self, tkeir_doc):
        """Run the run task step on a T-KEIR document.

        Example:
            >>> callable(NERTagger.run)
            True
        """
        return self.tag(tkeir_doc)
