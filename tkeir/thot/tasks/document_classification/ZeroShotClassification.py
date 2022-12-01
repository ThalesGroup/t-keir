# -*- coding: utf-8 -*-
"""Zero shot classification

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

from thot.tasks.document_classification import __version_document_classification__, __date_document_classification__
from thot.tasks.document_classification.ZeroShotClassificationConfiguration import ZeroShotClassificationConfiguration
from thot.core.ThotLogger import ThotLogger
from thot.tasks.TaskInfo import TaskInfo
import json
import traceback
from transformers import pipeline


class ZeroShotClassification:
    def __init__(self, config: ZeroShotClassificationConfiguration):
        """
        Initialise Zero shot classifier
        Args:
            - config : Zeroshot classifier configuration
        """
        self.config = config
        language = "en"
        device = 0
        use_cuda = False
        if "use-cuda" in config.configuration["settings"]:
            use_cuda = config.configuration["settings"]["use-cuda"]
        if "cuda-device" in config.configuration["settings"]:
            device = config.configuration["settings"]["cuda-device"]
        if "language" in config.configuration["settings"]:
            language = config.configuration["settings"]["language"]
        if language == "en":
            if use_cuda:
                self.model = pipeline("zero-shot-classification", device=device)
            else:
                self.model = pipeline("zero-shot-classification")
        elif language == "fr":
            self.model = pipeline("zero-shot-classification", model="BaptisteDoyen/camembert-base-xnli")
        else:
            raise ValueError("Language should be set")
        self.classes = []
        self.map_classes = dict()
        for classe in config.configuration["classes"]:
            self.classes = self.classes + classe["content"]
            for ci in classe["content"]:
                if ci not in self.map_classes:
                    self.map_classes[ci] = []
                self.map_classes[ci].append(classe["label"])
        self.classes = list(set(self.classes))
        self.pos_filter = set(["AUX", "CONJ", "CCONJ", "DET", "INTJ", "PART", "SCONJ", "SYM", "SPACE", "PRON", "PUNCT"])

    def _getSentences(self, msTokens):
        """ Return sentences according to tkeir-doc segmentation
            Args;
                msTokens : list of tkeir tokens (title_tokens of content_tokens part)
            Returns: list of tuples (sentence, significant term ration)

        """
        sentences = []
        current_sentence = ""
        count_significant_word = 0
        count_tokens = 0
        for tok in msTokens:
            if tok["is_sent_start"]:
                if current_sentence:
                    if count_tokens == 0:
                        count_tokens = 1
                    if count_tokens > 400:
                        sentences.append((current_sentence, count_significant_word / count_tokens))
                        count_tokens = 0
                        count_significant_word = 0
                current_sentence = ""
            count_tokens = count_tokens + 1
            # if tok["pos"] != "PUNCT":
            current_sentence = current_sentence + " " + tok["text"]
            if tok["pos"] not in self.pos_filter:
                count_significant_word = count_significant_word + 1
        if current_sentence:
            if count_tokens == 0:
                count_tokens = 1
            sentences.append((current_sentence.strip(), count_significant_word / count_tokens))
        return sentences

    def _fromSubClassesToMasterClasses(self, zsc_classes, map_classes=None):
        """ Aggregate scores of subclasses to a master classes according to aggregation strategy:
            - max : take max score
            - mean : mean of score
            - class score
            Args:
                - zsc_classes : master classes
                - map_classes : sub classes

            Return: table of one element with sequence and class scores                
        """
        class_scores = dict()
        max_scores = {}
        count_scores = {}
        if map_classes == None:
            map_classes = self.map_classes

        for ci in range(len(zsc_classes["labels"])):
            label = zsc_classes["labels"][ci]
            for c in map_classes[label]:
                if c not in class_scores:
                    class_scores[c] = 0.0
                    count_scores[c] = 0.0
                    max_scores[c] = 0.0
                class_scores[c] = class_scores[c] + zsc_classes["scores"][ci]
                if zsc_classes["scores"][ci] > max_scores[c]:
                    max_scores[c] = zsc_classes["scores"][ci]
                count_scores[c] = count_scores[c] + 1
        if self.config.configuration["re-labelling-strategy"] == "max":
            master_scores = sorted(
                map(lambda label: {"label": label, "score": max_scores[label]}, max_scores),
                key=lambda x: x["score"],
                reverse=True,
            )
        elif self.config.configuration["re-labelling-strategy"] == "mean":
            master_scores = sorted(
                map(lambda label: {"label": label, "score": class_scores[label] / count_scores[label]}, max_scores),
                key=lambda x: x["score"],
                reverse=True,
            )
        else:
            master_scores = sorted(
                map(lambda label: {"label": label, "score": class_scores[label]}, class_scores),
                key=lambda x: x["score"],
                reverse=True,
            )
        sum_score = 0.0
        for score_i in range(len(master_scores)):
            sum_score = master_scores[score_i]["score"] + sum_score
        if sum_score > 0.0:
            for score_i in range(len(master_scores)):
                master_scores[score_i]["score"] = master_scores[score_i]["score"] / sum_score
        return [{"sequence": zsc_classes["sequence"], "classes": master_scores}]

    def classify(self, tkeir_doc: dict, classes=None, map_classes=None, call_context=None):
        """ Classify a document MUST be tokenized with sentence tags
            Args :
                - tkeir_doc : a tkeir-document at least tokenized by sentences
                - classes : list of classes
                - map_classes : map between classes and subclasses
                - call_context : logging context
            Return the tkeir-doc with classification information
        """
        s_title_classif = []
        s_content_classif = []
        if not classes:
            classes = self.classes
        if ("title_morphosyntax" not in tkeir_doc) and ("content_morphosyntax" not in tkeir_doc):
            raise ValueError("title_morphosyntax and/or content_morphosyntax should be defined")
        if "title_morphosyntax" in tkeir_doc:
            title_sentences = self._getSentences(tkeir_doc["title_morphosyntax"])
            for s in title_sentences:
                s_title_classif = s_title_classif + self._fromSubClassesToMasterClasses(self.model(s[0], classes), map_classes)
        if "content_morphosyntax" in tkeir_doc:
            content_sentences = self._getSentences(tkeir_doc["content_morphosyntax"])
            ThotLogger.info("Classify '" + str(len(content_sentences)) + "' blocks.", context=call_context)
            for s in content_sentences:
                s_content_classif = s_content_classif + self._fromSubClassesToMasterClasses(
                    self.model(s[0], classes), map_classes
                )

        # document classes
        norm_count_s = 0
        count_s = 0
        labels = dict()
        norm_labels = dict()
        doc_s = s_title_classif + s_content_classif
        sentences = title_sentences + content_sentences

        for s_i in range(len(doc_s)):
            s = doc_s[s_i]
            for c in s["classes"]:
                if c["label"] not in labels:
                    labels[c["label"]] = 0.0
                if c["label"] not in norm_labels:
                    norm_labels[c["label"]] = 0.0
                norm_labels[c["label"]] = norm_labels[c["label"]] + c["score"] * sentences[s_i][1]
                labels[c["label"]] = labels[c["label"]] + c["score"]
            norm_count_s = norm_count_s + sentences[s_i][1]
            count_s = count_s + 1
        if count_s == 0:
            count_s = 1
        if norm_count_s == 0:
            norm_count_s = 1
        norm_doc_score = sorted(
            map(lambda label: {"label": label, "score": norm_labels[label] / norm_count_s}, norm_labels),
            key=lambda x: x["score"],
            reverse=True,
        )
        doc_score = sorted(
            map(lambda label: {"label": label, "score": labels[label] / count_s}, labels),
            key=lambda x: x["score"],
            reverse=True,
        )
        tkeir_doc["zero-shot-classification"] = {
            "document": doc_score,
            "normalized-document": norm_doc_score,
            "title_sentences": s_title_classif,
            "content_sentences": s_content_classif,
        }
        taskInfo = TaskInfo(
            task_name="zeroshotclassification",
            task_version=__version_document_classification__,
            task_date=__date_document_classification__,
        )
        tkeir_doc = taskInfo.addInfo(tkeir_doc)
        return tkeir_doc

    def run(self, tkeir_doc, call_context=None):
        """ run a classification
            Args:
            - tkeir_doc a tkeir document
            - call_context : logging context
            Returns a tkeir document with classification information
        """
        return self.classify(tkeir_doc, call_context=call_context)
