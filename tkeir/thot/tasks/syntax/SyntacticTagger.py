"""Syntax tagger
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES
All Rights Reserved.
"""

import collections
import gc
import hashlib
import json
import os
import warnings
from operator import attrgetter

import numpy
from spacy.attrs import ENT_TYPE, IS_ALPHA, LOWER, POS
from spacy.matcher import Matcher
from spacy.symbols import (
    agent,
    dobj,
)
from spacy.tokens import Doc, Span, Token

from thot.core.SpacyModelLoader import load_spacy_model
from thot.core.ThotLogger import ThotLogger
from thot.core.Utils import ThotTokenizerToSpacy
from thot.tasks.syntax import __date_syntax__, __version_syntax__
from thot.tasks.syntax.SyntacticTaggerConfiguration import (
    SyntacticTaggerConfiguration,
)
from thot.tasks.TaskInfo import TaskInfo

warnings.filterwarnings("ignore")


def remove_tokens_on_match(doc):
    """remove_tokens_on_match API.

    Example:
        >>> callable(remove_tokens_on_match)
        True
    """
    indexes = []
    for index, token in enumerate(doc):
        if token.pos_ in ("SPACE"):
            indexes.append(index)
    np_array = doc.to_array([LOWER, POS, ENT_TYPE, IS_ALPHA])
    np_array = numpy.delete(np_array, indexes, axis=0)
    doc2 = Doc(
        doc.vocab,
        words=[t.text for i, t in enumerate(doc) if i not in indexes],
    )
    doc2.from_array([LOWER, POS, ENT_TYPE, IS_ALPHA], np_array)
    return doc2


SVOTriple: tuple[list[Token], list[Token], list[Token]] = (
    collections.namedtuple("SVOTriple", ["subject", "verb", "object"])
)

_NOMINAL_SUBJ_DEPS = {"nsubj", "nsubjpass"}
_CLAUSAL_SUBJ_DEPS = {"csubj", "csubjpass"}
_VERB_MODIFIER_DEPS = {"aux", "auxpass", "neg"}


class SyntacticTagger:
    def __init__(
        self, config: SyntacticTaggerConfiguration = None, call_context=None
    ):
        """Initialize tagger

        Args:
            config (SyntacticTaggerConfiguration, optional): The tagger configuration. Defaults to None.

        Raises:
            ValueError: If configuration is not set
            ValueError: If language is not managed

                Example:
                    >>> callable(SyntacticTagger)
                    True
        """
        if not config:
            raise ValueError("tagger configuration is mandatory")
        language = config.configuration["taggers"][0][
            "language"
        ]  # TODO : management multiple language
        if language == "en" or language == "fr":
            self._nlp, self._spacy_model = load_spacy_model(
                language,
                size="md",
                call_context=call_context,
                download_if_missing=True,
                task_name="syntax",
            )
        else:
            raise ValueError("Language is not managed")
        self._nlp.tokenizer = ThotTokenizerToSpacy(
            self._nlp.vocab, config.configuration["taggers"]
        )

        self.NUMERIC_NE_TYPES = {
            "ORDINAL",
            "CARDINAL",
            "MONEY",
            "QUANTITY",
            "PERCENT",
            "TIME",
            "DATE",
        }
        self.SUBJ_DEPS = {
            "csubj",
            "csubjpass",
            "expl",
            "nsubj",
            "nsubjpass",
            "rsubj",
        }
        self.OBJ_DEPS = {
            "attr",
            "dobj",
            "dative",
            "oprd",
            "obj",
            "pobj",
            "iobj",
        }
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
                            self._rule_settings["suppress-bounds-sw"] = rules[
                                "settings"
                            ]["suppress-bounds-sw"]
                        if "pos-to-suppress" in rules["settings"]:
                            self._rule_settings["pos-to-suppress"] = rules[
                                "settings"
                            ]["pos-to-suppress"]
                    else:
                        if set(rules[r_i]["type"]) & self._basic_types:
                            self._matcher.add(
                                r_i, rules[r_i]["rule"], greedy="LONGEST"
                            )
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
        """linkRule API.

        Example:
            >>> callable(SyntacticTagger.linkRule)
            True
        """
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

    def expand_noun(self, tok: Token) -> list[Token]:
        """expand_noun API.

        Example:
            >>> callable(SyntacticTagger.expand_noun)
            True
        """
        tok_and_conjuncts = [tok] + list(tok.conjuncts)
        compounds = [
            child
            for tc in tok_and_conjuncts
            for child in tc.children
            if child.dep_ == "compound"
        ]
        return tok_and_conjuncts + compounds

    def expand_verb(self, tok: Token) -> list[Token]:
        """Expand a verb token to include all associated auxiliary and negation tokens.

        Example:
            >>> callable(SyntacticTagger.expand_verb)
            True
        """
        verb_modifiers = [
            child
            for child in tok.children
            if child.dep_ in _VERB_MODIFIER_DEPS
        ]
        return [tok] + verb_modifiers

    def _ensure_verb_entry(self, verb_sos, tok):
        if tok.pos_ in ["VERB", "AUX"]:
            _ = verb_sos[tok]

    def _collect_token_svo(self, tok, verb_sos):
        head = tok.head
        if tok.dep_ in _NOMINAL_SUBJ_DEPS:
            if head.pos_ in ["VERB", "AUX"]:
                verb_sos[head]["subjects"].update(self.expand_noun(tok))
            return
        if tok.dep_ in _CLAUSAL_SUBJ_DEPS:
            if head.pos_ in ["VERB", "AUX"]:
                verb_sos[head]["subjects"].update(tok.subtree)
            return
        if tok.dep_ == "dobj":
            if head.pos_ in ["VERB", "AUX"]:
                verb_sos[head]["objects"].update(self.expand_noun(tok))
            return
        if tok.dep_ == "pobj":
            if head.dep == agent and head.head.pos_ in ["VERB", "AUX"]:
                verb_sos[head.head]["objects"].update(self.expand_noun(tok))
            return
        if tok.dep_ != "xcomp":
            return
        if head.pos_ in ["VERB", "AUX"] and not any(
            child.dep == dobj for child in head.children
        ):
            verb_sos[head]["objects"].update(tok.subtree)

    def _propagate_conjunct_svos(self, verb_sos):
        for verb, so_dict in verb_sos.items():
            conjuncts = verb.conjuncts
            if so_dict.get("subjects"):
                for conj in conjuncts:
                    conj_so_dict = verb_sos.get(conj)
                    if conj_so_dict and not conj_so_dict.get("subjects"):
                        conj_so_dict["subjects"].update(so_dict["subjects"])
            if not so_dict.get("objects"):
                so_dict["objects"].update(
                    obj
                    for conj in conjuncts
                    for obj in verb_sos.get(conj, {}).get("objects", [])
                )

    def _yield_dependency_svo_triples(self, verb_sos):
        for verb, so_dict in verb_sos.items():
            if so_dict["subjects"] and so_dict["objects"]:
                yield SVOTriple(
                    subject=sorted(so_dict["subjects"], key=attrgetter("i")),
                    verb=sorted(self.expand_verb(verb), key=attrgetter("i")),
                    object=sorted(so_dict["objects"], key=attrgetter("i")),
                )

    def dependency_svo(self, doc):
        """dependency_svo API.

        Example:
            >>> callable(SyntacticTagger.dependency_svo)
            True
        """
        for sent in doc.sents:
            # connect subjects/objects to direct verb heads
            # and expand them to include conjuncts, compound nouns, ...
            verb_sos = collections.defaultdict(
                lambda: collections.defaultdict(set)
            )
            for tok in sent:
                self._ensure_verb_entry(verb_sos, tok)
                self._collect_token_svo(tok, verb_sos)
            self._propagate_conjunct_svos(verb_sos)
            yield from self._yield_dependency_svo_triples(verb_sos)

    def apply_link_rule(self, matches_content):
        """apply_link_rule API.

        Example:
            >>> callable(SyntacticTagger.apply_link_rule)
            True
        """
        for span_i in range(len(matches_content)):
            for span_j in range(span_i + 1, len(matches_content)):
                if matches_content[span_i].start == (
                    matches_content[span_j].end - 1
                ):
                    self.linkRule(
                        matches_content[span_j], matches_content[span_i]
                    )
                if matches_content[span_j].start == (
                    matches_content[span_i].end - 1
                ):
                    self.linkRule(
                        matches_content[span_i], matches_content[span_j]
                    )

    def add_svo(self, svos, svo):
        # compute cache key:
        """add_svo API.

        Example:
            >>> callable(SyntacticTagger.add_svo)
            True
        """
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
        """search_svos API.

        Example:
            >>> callable(SyntacticTagger.search_svos)
            True
        """
        svos = []
        for span_i in range(len(matches_content)):
            for pattern in self._svo_patterns:
                current_span = span_i
                matched_pattern = []
                end_pattern = -1
                for item in pattern:
                    if (end_pattern != -1) and (
                        end_pattern != matches_content[current_span].start
                    ):
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
                        and (
                            matches_content[next_span].start
                            >= matches_content[current_span].start
                        )
                        and (
                            matches_content[next_span].end
                            <= matches_content[current_span].end
                        )
                    ):
                        pattern_positions.append(matches_content[next_span])
                        test_labels.add(matches_content[next_span].label_)
                        current_span = next_span
                    # check if next pattern is in current pattern
                    elif (
                        (next_span < len(matches_content))
                        and (
                            matches_content[next_span].start
                            == matches_content[current_span].start
                        )
                        and (
                            matches_content[next_span].end
                            >= matches_content[current_span].end
                        )
                    ):
                        pattern_positions.append(matches_content[next_span])
                        current_span = next_span
                        test_labels.add(matches_content[next_span].label_)
                        end_pattern = matches_content[next_span].end
                    if (current_span < len(matches_content)) and (
                        test_labels & possible_pattern_labels
                    ):
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
        """get_dependencies API.

        Example:
            >>> callable(SyntacticTagger.get_dependencies)
            True
        """
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

    def _relation_item(self, alternate):
        return {
            "content": [token.text for token in alternate],
            "lemma_content": [token.lemma_ for token in alternate],
            "pos": [token.pos_ for token in alternate],
            "positions": [token.i for token in alternate],
            "label": alternate.label_,
        }

    def _merge_triple_entry(
        self, current_triples, triple_entry, triple_position
    ):
        sz_alt = len(triple_entry)
        sz_triple = len(current_triples)
        if sz_triple:
            for alti in range(sz_alt):
                item = self._relation_item(triple_entry[alti])
                if alti == 0:
                    for t in range(sz_triple):
                        current_triples[t][triple_position] = item
                else:
                    for t in range(sz_triple):
                        current_triples.append(current_triples[t])
                        current_triples[-1][triple_position] = item
            return current_triples

        for alti in range(sz_alt):
            item = self._relation_item(triple_entry[alti])
            current_triples.append([item, None, None])
        return current_triples

    def _build_svo_triples(self, svo):
        current_triples = []
        triple_position = 0
        for triple_entry in svo:
            current_triples = self._merge_triple_entry(
                current_triples,
                triple_entry,
                triple_position,
            )
            triple_position = triple_position + 1
        return current_triples

    def _relation_checksum(self, ct):
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
        return hashlib.md5(triple_str.encode()).hexdigest()

    def _trim_relation_bounds(self, ct):
        if not self._rule_settings["suppress-bounds-sw"]:
            return
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

    def _should_discard_relation(self, ct):
        discard_pos = {"PART", "DET", "PRON", "CONJ", "CCONJ"}
        if (
            len(ct[0]["pos"]) == 1
            and len(ct[2]["pos"]) == 1
            and ct[0]["pos"][0] in discard_pos
            and ct[2]["pos"][0] in discard_pos
        ):
            return True
        return (
            len(ct[0]["pos"]) == 0
            or len(ct[1]["pos"]) == 0
            or len(ct[2]["pos"]) == 0
        )

    def _append_relation(self, triple_list, ct, field):
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

    def get_relations(self, svos, field):
        """get_relations API.

        Example:
            >>> callable(SyntacticTagger.get_relations)
            True
        """
        triple_list = []
        no_replicate = set()
        for svo in svos:
            for ct in self._build_svo_triples(svo):
                ct_check_sum = self._relation_checksum(ct)
                if ct_check_sum in no_replicate:
                    continue
                self._trim_relation_bounds(ct)
                if not self._should_discard_relation(ct):
                    self._append_relation(triple_list, ct, field)
                no_replicate.add(ct_check_sum)
        return triple_list

    def _validate_tag_input(self, tkeir_doc):
        if ("title_tokens" not in tkeir_doc) and (
            "content_tokens" not in tkeir_doc
        ):
            raise ValueError("title tokens or content tokens should be set")

    def _prepare_spacy_doc(self, tokens):
        search_doc = self._nlp.tokenizer(tokens)
        return self._nlp(
            search_doc,
            disable=["tagger", "ner", "attribute_ruler", "lemmatizer"],
        )

    def _apply_morphosyntax(self, doc, morphosyntax):
        with doc.retokenize() as retokenizer:
            for token_i in range(len(doc)):
                attrs = {
                    "POS": morphosyntax[token_i]["pos"],
                    "LEMMA": morphosyntax[token_i]["lemma"],
                }
                retokenizer.merge(doc[token_i : token_i + 1], attrs=attrs)

    def _should_add_ner_span(self, doc, span):
        if (span["end"] - span["start"]) != 1:
            return True
        return doc[span["start"]].pos_ not in [
            "PART",
            "DET",
            "PRON",
            "CCONJ",
            "CONJ",
            "INT",
        ]

    def _append_ner_spans(self, doc, matches, ner_spans):
        for span in ner_spans or []:
            if not self._should_add_ner_span(doc, span):
                continue
            matches.append(
                Span(
                    doc=doc,
                    start=span["start"],
                    end=span["end"],
                    label=span["label"],
                )
            )

    def _dep_svo_spans(self, doc, dep_svo):
        d_subject = [
            Span(
                doc,
                start=dep_svo.subject[0].i,
                end=dep_svo.subject[-1].i + 1,
                label="dep_subject",
            )
        ]
        d_verb = [
            Span(
                doc,
                start=dep_svo.verb[0].i,
                end=dep_svo.verb[-1].i + 1,
                label="dep_verb",
            )
        ]
        d_object = [
            Span(
                doc,
                start=dep_svo.object[0].i,
                end=dep_svo.object[-1].i + 1,
                label="dep_object",
            )
        ]
        return [d_subject, d_verb, d_object]

    def _tag_field(
        self,
        doc,
        tkeir_doc,
        morph_key,
        ner_key,
        deps_key,
        field_type,
    ):
        if doc is None or not len(doc):
            return

        self._apply_morphosyntax(doc, tkeir_doc[morph_key])
        matches = self._matcher(doc, as_spans=True)
        self.apply_link_rule(matches)
        self._append_ner_spans(doc, matches, tkeir_doc.get(ner_key))
        matches = sorted(matches, key=attrgetter("start"))
        svos = self.search_svos(matches)
        for dep_svo in self.dependency_svo(doc):
            svos = self.add_svo(svos, self._dep_svo_spans(doc, dep_svo))
        svos = sorted(svos, key=lambda x: x[0][0].start)
        tkeir_doc[deps_key] = self.get_dependencies(doc)
        relations = self.get_relations(svos, field_type)
        if relations:
            tkeir_doc["kg"] = tkeir_doc["kg"] + relations

    def tag(self, tkeir_doc: dict):
        """POS tag the tkeir document

        Args:
            tkeir_doc (dict): the document to tag in tkeir format

        Returns:
            [dict]: the document in tkeir format with POS tags

                Example:
                    >>> callable(SyntacticTagger.tag)
                    True
        """
        self._cache_svos = set()
        self._validate_tag_input(tkeir_doc)
        doc_title = None
        doc_content = None
        if "title_tokens" in tkeir_doc:
            doc_title = self._prepare_spacy_doc(tkeir_doc["title_tokens"])
        if "content_tokens" in tkeir_doc:
            doc_content = self._prepare_spacy_doc(tkeir_doc["content_tokens"])

        if "kg" not in tkeir_doc:
            tkeir_doc["kg"] = []

        self._tag_field(
            doc_content,
            tkeir_doc,
            "content_morphosyntax",
            "content_ner",
            "content_deps",
            "content",
        )
        self._tag_field(
            doc_title,
            tkeir_doc,
            "title_morphosyntax",
            "title_ner",
            "title_deps",
            "title",
        )

        taskInfo = TaskInfo(
            task_name="syntax",
            task_version=__version_syntax__,
            task_date=__date_syntax__,
        )
        tkeir_doc = taskInfo.addInfo(tkeir_doc)
        self._count_run = self._count_run + 1
        if self._count_run > 100:
            gc.collect()
            self._count_run = 0
        return tkeir_doc

    def run(self, tkeir_doc: dict):
        """Run the run task step on a T-KEIR document.

        Example:
            >>> callable(SyntacticTagger.run)
            True
        """
        return self.tag(tkeir_doc)
