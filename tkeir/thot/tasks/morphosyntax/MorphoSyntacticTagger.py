"""Morphosyntactic tagger

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES
All Rights Reserved.
"""

import gc

from thot.core.SpacyModelLoader import load_spacy_model
from thot.core.Utils import ThotTokenizerToSpacy
from thot.tasks.morphosyntax import (
    __date_morphosyntax__,
    __version_morphosyntax__,
)
from thot.tasks.morphosyntax.MorphoSyntacticTaggerConfiguration import (
    MorphoSyntacticTaggerConfiguration,
)
from thot.tasks.TaskInfo import TaskInfo


class MorphoSyntacticTagger:
    def __init__(
        self,
        config: MorphoSyntacticTaggerConfiguration = None,
        call_context=None,
    ):
        """Initialize tagger

        Args:
            config (MorphoSyntacticTaggerConfiguration, optional): The tagger configuration. Defaults to None.

        Raises:
            ValueError: If configuration is not set
            ValueError: If language is not managed

                Example:
                    >>> callable(MorphoSyntacticTagger)
                    True
        """
        if not config:
            raise ValueError("tagger configuration is mandatory")
        language = config.configuration["taggers"][0][
            "language"
        ]  # TODO : management multiple language
        self._pre_tagging_with_concept = False
        self._add_concept_in_kg = False
        if "pre-tagging-with-concept" in config.configuration["taggers"][0]:
            self._pre_tagging_with_concept = config.configuration["taggers"][
                0
            ]["pre-tagging-with-concept"]
        if (
            "add-concept-in-knowledge-graph"
            in config.configuration["taggers"][0]
        ):
            self._add_concept_in_kg = config.configuration["taggers"][0][
                "add-concept-in-knowledge-graph"
            ]
        if language == "en" or language == "fr":
            self._nlp, self._spacy_model = load_spacy_model(
                language,
                size="md",
                call_context=call_context,
                download_if_missing=True,
                task_name="morphosyntax",
            )
        else:
            raise ValueError("Language is not managed")
        self._nlp.tokenizer = ThotTokenizerToSpacy(
            self._nlp.vocab,
            config.configuration["taggers"],
            call_context=call_context,
        )
        self._count_run = 0

    def _retag_punct(self, tok):
        """Retag punct helper.

        Example:
            >>> tagger = object.__new__(MorphoSyntacticTagger)
            >>> tagger._retag_punct({'text': '?', 'pos': 'NOUN'})['pos']
            'PUNCT'
        """
        if tok["text"] in ["*", ",", ";", "?", "!", "/"]:
            tok["pos"] = "PUNCT"
        return tok

    def _do_concept(self, position, text, lemma, concept, concept_label):
        """Do concept helper.

        Example:
            >>> tagger = object.__new__(MorphoSyntacticTagger)
            >>> triple = tagger._do_concept(0, 'cat', 'cat', ['animal'], 'bio')
            >>> triple['field_type']
            'concept'
        """
        return {
            "subject": {
                "content": text,
                "lemma_content": lemma,
                "class": -1,
                "positions": [position],
            },
            "property": {
                "content": "rel:has-concept",
                "lemma_content": "rel:has-concept",
                "class": -1,
                "positions": [-1],
            },
            "value": {
                "content": concept,
                "lemma_content": concept,
                "class": -1,
                "positions": [-1],
                "label": concept_label,
            },
            "automatically_fill": True,
            "confidence": 0.0,
            "weight": 0.0,
            "field_type": "concept",
        }

    def _token_assignment(self, tok_i):
        return self._retag_punct(
            {
                "pos": tok_i.pos_,
                "lemma": tok_i.lemma_,
                "text": tok_i.text,
                "is_oov": tok_i.is_oov,
                "is_sent_start": bool(tok_i.is_sent_start),
            }
        )

    def _concept_triples_for_token(self, tok_i):
        if not self._add_concept_in_kg or not isinstance(
            tok_i._.advanced_tag, list
        ):
            return []
        triples = []
        for concept_i in tok_i._.advanced_tag:
            for concept_label in concept_i:
                if concept_i[concept_label]["type"] != "concept":
                    continue
                if "concept" not in concept_i[concept_label]:
                    continue
                triples.append(
                    self._do_concept(
                        tok_i.i,
                        tok_i.text,
                        tok_i.lemma_,
                        [concept_i[concept_label]["concept"]],
                        concept_label,
                    )
                )
        return triples

    def _process_doc_tokens(self, doc_tokens):
        morphosyntax = []
        kg = []
        for tok_i in doc_tokens:
            morphosyntax.append(self._token_assignment(tok_i))
            kg.extend(self._concept_triples_for_token(tok_i))
        return morphosyntax, kg

    def tag(self, tkeir_doc: dict):
        """POS tag the tkeir document

        Args:
            tkeir_doc (dict): the document to tag in tkeir format

        Returns:
            [dict]: the document in tkeir format with POS tags

                Example:
                    >>> callable(MorphoSyntacticTagger.tag)
                    True
        """
        doc_title = []
        doc_content = []
        if ("title_tokens" not in tkeir_doc) and (
            "content_tokens" not in tkeir_doc
        ):
            raise ValueError(
                "Tagger need title_tokens and/or content_tokens fields"
            )
        if "title_tokens" in tkeir_doc:
            titleDoc = self._nlp.tokenizer(tkeir_doc["title_tokens"])
            doc_title = self._nlp(titleDoc, disable=["parser", "ner"])
        if "content_tokens" in tkeir_doc:
            contentDoc = self._nlp.tokenizer(tkeir_doc["content_tokens"])
            doc_content = self._nlp(contentDoc, disable=["parser", "ner"])
        title, title_kg = self._process_doc_tokens(doc_title)
        content, content_kg = self._process_doc_tokens(doc_content)
        kg = title_kg + content_kg
        tkeir_doc["title_morphosyntax"] = title
        tkeir_doc["content_morphosyntax"] = content
        if kg:
            if "kg" not in tkeir_doc:
                tkeir_doc["kg"] = []
            tkeir_doc["kg"] = tkeir_doc["kg"] + kg
        taskInfo = TaskInfo(
            task_name="morphosyntax",
            task_version=__version_morphosyntax__,
            task_date=__date_morphosyntax__,
        )
        tkeir_doc = taskInfo.addInfo(tkeir_doc)
        # prevent memory leak
        self._count_run = self._count_run + 1
        if self._count_run > 100:
            gc.collect()
            self._count_run = 0
        return tkeir_doc

    def run(self, tkeir_doc):
        """Run the run task step on a T-KEIR document.

        Example:
            >>> callable(MorphoSyntacticTagger.run)
            True
        """
        return self.tag(tkeir_doc)
