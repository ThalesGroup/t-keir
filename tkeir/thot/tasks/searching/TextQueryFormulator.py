# -*- coding: utf-8 -*-
"""Text query formaulator
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import re
import numpy as np
from math import sqrt
from tkeir.thot.core.ThotLogger import ThotLogger

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
from collections import OrderedDict
from sklearn.metrics import pairwise_distances
from scipy.spatial.distance import cosine
from sklearn.cluster import DBSCAN

# import hdbscan


from thot.core.Utils import ThotTokenizerToSpacy


class TextQueryFormulator:

    DUMMY_QUERY = 0
    SENTENCES_QUERY = 1
    KEYWORDS_QUERY = 2
    SVO_QUERY = 3
    SEMANTIC_KEYWORDS_QUERY = 4
    SEMANTIC_SVO_QUERY = 5
    CONCEPT_QUERY = 6

    def __init__(self):
        pass

    def dummyContent(self, query: dict = None, maxsize=1000, uniqword=True, boost_uniqword=False):
        lemma_text = []
        content_text = []
        pos_filter = set(
            ["ADP", "ADV", "AUX", "CONJ", "CCONJ", "DET", "INTJ", "PART", "TO" "SCONJ", "SYM", "SPACE", "PRON", "PUNCT", "NUM"]
        )
        text_fiter = [
            "%",
            "°",
            "was",
            "were",
            "does",
            "did",
            "will",
            "is",
            "be",
            "have",
            "can",
            "could",
            "would",
            "must",
            "has",
        ]
        hash_lemma = dict()
        hash_content = dict()
        count_lemma = 0
        count_word = 0
        if ("content_morphosyntax" in query) and query["content_morphosyntax"]:
            count_toks = 0
            for toks in query["content_morphosyntax"]:
                if (toks["pos"] not in pos_filter) and (toks["text"] not in text_fiter) and (toks["lemma"] not in text_fiter):
                    count_toks = count_toks + 1
            if count_toks == 0:
                pos_filter = set(
                    ["ADP", "AUX", "CONJ", "CCONJ", "DET", "INTJ", "PART", "TO" "SCONJ", "SYM", "SPACE", "PRON", "PUNCT"]
                )
            for toks in query["content_morphosyntax"]:
                toks["lemma"] = re.sub(r"\s+", " ", toks["lemma"])
                if (toks["pos"] not in pos_filter) and (toks["text"] not in text_fiter) and (toks["lemma"] not in text_fiter):
                    lemma_text.append(toks["lemma"])
                    content_text.append(toks["text"])
                    if toks["lemma"] not in hash_lemma:
                        hash_lemma[toks["lemma"]] = 0
                    if toks["text"] not in hash_content:
                        hash_content[toks["text"]] = 0
                    hash_lemma[toks["lemma"]] = hash_lemma[toks["lemma"]] + 1
                    hash_content[toks["text"]] = hash_content[toks["text"]] + 1
                    count_lemma = count_lemma + 1
                    count_word = count_word + 1
            query["lemma_content"] = [" ".join(lemma_text)]

            min_lemma = 10000000
            min_word = 10000000
            for w in hash_lemma:
                hash_lemma[w] = maxsize * hash_lemma[w] / count_lemma
                if hash_lemma[w] < min_lemma:
                    min_lemma = hash_lemma[w]

            for w in hash_content:
                hash_content[w] = maxsize * hash_content[w] / count_word
                if hash_content[w] < min_word:
                    min_word = hash_content[w]

            for w in hash_lemma:
                hash_lemma[w] = int(hash_lemma[w] / min_lemma)

            for w in hash_content:
                hash_content[w] = int(hash_content[w] / min_word)

            if boost_uniqword:
                lemma2_q = list(
                    map(lambda x: [x[0]] * x[1], sorted(hash_lemma.items(), key=lambda item: item[1], reverse=True))
                )
                content2_q = list(
                    map(lambda x: [x[0]] * x[1], sorted(hash_content.items(), key=lambda item: item[1], reverse=True))
                )
            elif uniqword:
                lemma2_q = list(map(lambda x: [x[0]], sorted(hash_lemma.items(), key=lambda item: item[1], reverse=True)))
                content2_q = list(map(lambda x: [x[0]], sorted(hash_content.items(), key=lambda item: item[1], reverse=True)))
            else:
                lemma2_q = [lemma_text]
                content2_q = [content_text]

            lemma_q = []
            for l in lemma2_q:
                lemma_q = lemma_q + l
            content_q = []
            for l in content2_q:
                content_q = content_q + l
            lemma_q = " ".join(lemma_q[0:maxsize])
            content_q = " ".join(content_q[0:maxsize])
            return (TextQueryFormulator.DUMMY_QUERY, [[1.0, content_q, lemma_q]])
        return (
            TextQueryFormulator.DUMMY_QUERY,
            [[1.0, " ".join(query["content"]).strip(), " ".join(query["content"]).strip()]],
        )

    def _scoreSentences(self, lemma_sentences, text_sentences):
        lemma_vectorizer = TfidfVectorizer()
        lemma_X = np.array(lemma_vectorizer.fit_transform(lemma_sentences).toarray())
        norm_lemmaX = np.linalg.norm(lemma_X, axis=1).reshape(lemma_X.shape[0], 1)
        lemma_X = lemma_X / norm_lemmaX
        np.nan_to_num(lemma_X, copy=False)
        sentence_weight = np.nansum(lemma_X, axis=1)
        sentence_weight = np.array(sentence_weight).ravel()
        # TODO
        # lemma_clusterer = hdbscan.HDBSCAN(min_cluster_size=3)
        # lemma_clusterer.fit(lemma_X)
        lemma_clusterer = None  # hdbscan.HDBSCAN(min_cluster_size=3)
        """
        lemma_clusterer.fit(lemma_X)
        best_sentences=dict()
        sid = 0
        """
        for k in lemma_clusterer.labels_:
            if k != -1:  # suppress outliers
                if k not in best_sentences:
                    best_sentences[k] = [sentence_weight[sid], text_sentences[sid], lemma_sentences[sid]]
                if sentence_weight[sid] > best_sentences[k][0]:
                    best_sentences[k] = [sentence_weight[sid], text_sentences[sid], lemma_sentences[sid]]
                sid = sid + 1

        """
        sorted_sentences=sorted(list(best_sentences.values()),key=lambda x:x[0],reverse=True)
        return sorted_sentences
        """
        return dict()

    def splitSentenceInPhrase(self, sentence, max_sentence_size=30, split_pos=["PUNCT"]):
        tok_phrases = []
        if len(sentence) > max_sentence_size:
            start_idx = 0
            sent_split = []
            split_pos = set(split_pos)
            for tok_i in range(len(sentence)):
                if sentence[tok_i]["pos"] in split_pos:
                    if start_idx < tok_i:
                        sent_split.append(sentence[start_idx:tok_i])
                    start_idx = tok_i + 1
            if start_idx < len(sentence):
                sent_split.append(sentence[start_idx:])
            lsplit = len(sent_split)

            for si in range(lsplit):
                if si < (lsplit - 1):
                    if len(sent_split[si]) < max_sentence_size:
                        if len(sent_split[si] + sent_split[si + 1]) < max_sentence_size:
                            sent_split[si + 1] = sent_split[si] + sent_split[si + 1]
                        else:
                            tok_phrases.append(sent_split[si])
                    elif "PUNCT" in split_pos:
                        tok_phrases = tok_phrases + self.splitSentenceInPhrase(
                            sent_split[si], max_sentence_size, ["CONJ", "CCONJ"]
                        )
                    else:
                        hard_cut = [
                            sent_split[si][x : x + max_sentence_size] for x in range(0, len(sent_split[si]), max_sentence_size)
                        ]
                        tok_phrases = tok_phrases + hard_cut
                else:
                    if len(sent_split[si]) < max_sentence_size:
                        tok_phrases.append(sent_split[si])
                    elif "PUNCT" in split_pos:
                        tok_phrases = tok_phrases + self.splitSentenceInPhrase(
                            sent_split[si], max_sentence_size, ["CONJ", "CCONJ"]
                        )
                    else:
                        hard_cut = [
                            sent_split[si][x : x + max_sentence_size] for x in range(0, len(sent_split[si]), max_sentence_size)
                        ]
                        tok_phrases = tok_phrases + hard_cut
        else:
            tok_phrases.append(sentence)
        return tok_phrases

    def sentencesByScore(self, tkeir_doc, max_sentence_size=16):
        lemma_sentences = []
        text_sentences = []
        hash_lemma = set()
        pos_filter = set(
            ["ADP", "ADV", "AUX", "CONJ", "CCONJ", "DET", "INTJ", "PART", "TO" "SCONJ", "SYM", "SPACE", "PRON", "PUNCT", "NUM"]
        )
        text_fiter = ["%", "°", "is", "be", "have", "can", "could", "would", "must", "has"]
        if ("content_morphosyntax" in tkeir_doc) and tkeir_doc["content_morphosyntax"]:
            sentence = []
            text = []
            if "title_morphosyntax" in tkeir_doc:
                for toks in tkeir_doc["title_morphosyntax"]:
                    if (
                        (toks["pos"] not in pos_filter)
                        and (toks["text"] not in text_fiter)
                        and (toks["lemma"] not in text_fiter)
                    ):
                        sentence.append(toks["lemma"])
                    text.append(toks["text"])
                sentence = " ".join(sentence)
                text = " ".join(text)
                hash_lemma.add(sentence)
                lemma_sentences.append(sentence)
                text_sentences.append(text)
            sentence = []
            text = []
            if "content_morphosyntax" in tkeir_doc:
                for toks in tkeir_doc["content_morphosyntax"]:
                    if toks["is_sent_start"]:
                        if len(sentence):
                            phrases = self.splitSentenceInPhrase(sentence)
                            for phrase in phrases:
                                sentence = []
                                text = []
                                for ptoks in phrase:
                                    if (
                                        (ptoks["pos"] not in pos_filter)
                                        and (ptoks["text"] not in text_fiter)
                                        and (ptoks["lemma"] not in text_fiter)
                                    ):
                                        sentence.append(ptoks["lemma"])
                                    text.append(ptoks["text"])
                                sentence = " ".join(sentence)
                                text = " ".join(text)
                                if sentence not in hash_lemma:
                                    lemma_sentences.append(sentence)
                                    text_sentences.append(text)
                                    hash_lemma.add(sentence)
                            sentence = []
                            text = []
                    sentence.append(toks)
                if len(sentence):
                    phrases = self.splitSentenceInPhrase(sentence)
                    for phrase in phrases:
                        sentence = []
                        text = []
                        for ptoks in phrase:
                            if (
                                (ptoks["pos"] not in pos_filter)
                                and (ptoks["text"] not in text_fiter)
                                and (ptoks["lemma"] not in text_fiter)
                            ):
                                sentence.append(ptoks["lemma"])
                            text.append(ptoks["text"])
                        sentence = " ".join(sentence)
                        text = " ".join(text)
                        if sentence not in hash_lemma:
                            lemma_sentences.append(sentence)
                            text_sentences.append(text)
                            hash_lemma.add(sentence)
                    sentence = []
                    text = []

        if len(lemma_sentences) > 0:
            try:
                score_sent = self._scoreSentences(lemma_sentences, text_sentences)
                return (TextQueryFormulator.SENTENCES_QUERY, score_sent)
            except Exception as e:
                ThotLogger.warning("Score sentence :" + str(e))
        return (TextQueryFormulator.SENTENCES_QUERY, [])

    def keywordsByScore(self, tkeir_doc):
        if "keywords" in tkeir_doc:
            kws = sorted(tkeir_doc["keywords"], key=lambda x: x["score"], reverse=True)
            # clean single words
            kws = list(map(lambda x: [x["score"], "", x["text"]], list(filter(lambda x: len(x["text"].split()) > 1, kws))))
            return (TextQueryFormulator.KEYWORDS_QUERY, kws)
        return (TextQueryFormulator.KEYWORDS_QUERY, [])

    def queryTermVector(self, doc_termvector):
        pass

    def svoByScore(self, tkeir_doc):
        if "kg" in tkeir_doc:
            hash_lemma = dict()
            lemma_sentences = []
            text_sentences = []
            for kg_item in tkeir_doc["kg"]:
                if kg_item["field_type"] == "content":
                    lemma_phrase = (
                        " ".join(kg_item["subject"]["lemma_content"])
                        + " "
                        + " ".join(kg_item["property"]["lemma_content"])
                        + " "
                        + " ".join(kg_item["value"]["lemma_content"])
                    )
                    if lemma_phrase not in hash_lemma:
                        hash_lemma[lemma_phrase] = kg_item
                        phrase = (
                            " ".join(kg_item["subject"]["content"])
                            + " "
                            + " ".join(kg_item["property"]["content"])
                            + " "
                            + " ".join(kg_item["value"]["content"])
                        )
                        if lemma_phrase and phrase:
                            lemma_sentences.append(lemma_phrase)
                            text_sentences.append(phrase)
            if len(lemma_sentences) > 0:
                try:
                    score_sent = self._scoreSentences(lemma_sentences, text_sentences)
                    best_svos = []
                    for svo_i in score_sent:
                        if svo_i[2] in hash_lemma:
                            best_svos.append(hash_lemma[svo_i[2]])
                    return (TextQueryFormulator.SVO_QUERY, best_svos)
                except Exception as e:
                    ThotLogger.warning("Score sentence :" + str(e))
        return (TextQueryFormulator.SVO_QUERY, [])

    def semanticKeywords(self, tkeir_doc, advanced_querying: dict):
        classes = dict()

        for kg_item in tkeir_doc["kg"]:
            if kg_item["value"]["content"] == ["keyword"]:
                if kg_item["value"]["class"] not in classes:
                    classes[kg_item["value"]["class"]] = 0
                classes[kg_item["value"]["class"]] = classes[kg_item["value"]["class"]] + 1

        classes = sorted(classes.items(), key=lambda x: x[1], reverse=True)
        classes = classes[advanced_querying["querying"]["match-keyword"]["semantic-skip-highest-ranked-classes"] :]
        count_max = 0
        count_min = 1000000
        for k in range(len(classes)):
            if count_max < classes[k][1]:
                count_max = classes[k][1]
            if count_min > classes[k][1]:
                count_min = classes[k][1]
        if count_min == count_max:
            count_max = count_min + 1
        for k in range(len(classes)):
            classes[k] = (
                classes[k][0],
                int(
                    1
                    + (advanced_querying["querying"]["match-keyword"]["semantic-max-boosting"] - 1)
                    * (classes[k][1] - count_min)
                    / (count_max - count_min)
                ),
            )

        return (TextQueryFormulator.SEMANTIC_KEYWORDS_QUERY, classes)

    def semanticSVO(self, tkeir_doc, config: dict):
        if "kg" in tkeir_doc:
            hash_lemma = dict()
            # svo unicity

            hash_class_only = dict()
            hash_sp_class = dict()
            hash_so_class = dict()
            hash_po_class = dict()
            hash_s_class = dict()
            hash_p_class = dict()
            hash_o_class = dict()

            for kg_item in tkeir_doc["kg"]:
                if kg_item["field_type"] == "content":
                    class_phrase = (
                        str(kg_item["subject"]["class"])
                        + " "
                        + str(kg_item["property"]["class"])
                        + " "
                        + str(kg_item["value"]["class"])
                    )
                    sp_class_phrase = (
                        str(kg_item["subject"]["class"])
                        + " "
                        + str(kg_item["property"]["class"])
                        + " "
                        + str(kg_item["value"]["lemma_content"])
                    )
                    so_class_phrase = (
                        str(kg_item["subject"]["class"])
                        + " "
                        + str(kg_item["property"]["lemma_content"])
                        + " "
                        + str(kg_item["value"]["class"])
                    )
                    po_class_pgrase = (
                        str(kg_item["subject"]["lemma_content"])
                        + " "
                        + str(kg_item["property"]["class"])
                        + " "
                        + str(kg_item["value"]["class"])
                    )
                    s_class_phrase = (
                        str(kg_item["subject"]["class"])
                        + " "
                        + str(kg_item["property"]["lemma_content"])
                        + " "
                        + str(kg_item["value"]["lemma_content"])
                    )
                    p_class_phrase = (
                        str(kg_item["subject"]["lemma_content"])
                        + " "
                        + str(kg_item["property"]["class"])
                        + " "
                        + str(kg_item["value"]["lemma_content"])
                    )
                    o_class_phrase = (
                        str(kg_item["subject"]["lemma_content"])
                        + " "
                        + str(kg_item["property"]["lemma_content"])
                        + " "
                        + str(kg_item["value"]["class"])
                    )
                    if class_phrase not in hash_class_only:
                        hash_class_only[class_phrase] = dict()
                        hash_class_only[class_phrase]["count"] = 0
                        hash_class_only[class_phrase]["item"] = kg_item
                    if sp_class_phrase not in hash_sp_class:
                        hash_sp_class[sp_class_phrase] = dict()
                        hash_sp_class[sp_class_phrase]["count"] = 0
                        hash_sp_class[sp_class_phrase]["item"] = kg_item
                    if so_class_phrase not in hash_so_class:
                        hash_so_class[so_class_phrase] = dict()
                        hash_so_class[so_class_phrase]["count"] = 0
                        hash_so_class[so_class_phrase]["item"] = kg_item
                    if po_class_pgrase not in hash_po_class:
                        hash_po_class[po_class_pgrase] = dict()
                        hash_po_class[po_class_pgrase]["count"] = 0
                        hash_po_class[po_class_pgrase]["item"] = kg_item
                    if s_class_phrase not in hash_s_class:
                        hash_s_class[s_class_phrase] = dict()
                        hash_s_class[s_class_phrase]["count"] = 0
                        hash_s_class[s_class_phrase]["item"] = kg_item
                    if p_class_phrase not in hash_p_class:
                        hash_p_class[p_class_phrase] = dict()
                        hash_p_class[p_class_phrase]["count"] = 0
                        hash_p_class[p_class_phrase]["item"] = kg_item
                    if o_class_phrase not in hash_o_class:
                        hash_o_class[o_class_phrase] = dict()
                        hash_o_class[o_class_phrase]["count"] = 0
                        hash_o_class[o_class_phrase]["item"] = kg_item

                    hash_class_only[class_phrase]["count"] = hash_class_only[class_phrase]["count"] + 1
                    hash_sp_class[sp_class_phrase]["count"] = hash_sp_class[sp_class_phrase]["count"] + 1
                    hash_so_class[so_class_phrase]["count"] = hash_so_class[so_class_phrase]["count"] + 1
                    hash_po_class[po_class_pgrase]["count"] = hash_po_class[po_class_pgrase]["count"] + 1
                    hash_s_class[s_class_phrase]["count"] = hash_s_class[s_class_phrase]["count"] + 1
                    hash_p_class[p_class_phrase]["count"] = hash_p_class[p_class_phrase]["count"] + 1
                    hash_o_class[o_class_phrase]["count"] = hash_o_class[o_class_phrase]["count"] + 1

            hash_class_only = sorted(hash_class_only.items(), key=lambda x: x[1]["count"], reverse=True)
            hash_sp_class = sorted(hash_sp_class.items(), key=lambda x: x[1]["count"], reverse=True)
            hash_so_class = sorted(hash_so_class.items(), key=lambda x: x[1]["count"], reverse=True)
            hash_po_class = sorted(hash_po_class.items(), key=lambda x: x[1]["count"], reverse=True)
            hash_s_class = sorted(hash_s_class.items(), key=lambda x: x[1]["count"], reverse=True)
            hash_p_class = sorted(hash_p_class.items(), key=lambda x: x[1]["count"], reverse=True)
            hash_o_class = sorted(hash_o_class.items(), key=lambda x: x[1]["count"], reverse=True)
            return (
                TextQueryFormulator.SEMANTIC_SVO_QUERY,
                {
                    "semantic-use-class-triple": hash_class_only,
                    "semantic-use-lemma-property-object": hash_po_class,
                    "semantic-use-subject-lemma-object": hash_so_class,
                    "semantic-use-subject-property-lemma": hash_sp_class,
                    "semantic-use-lemma-lemma-object": hash_o_class,
                    "semantic-use-lemma-property-lemma": hash_p_class,
                    "semantic-use-subject-lemma-lemma": hash_s_class,
                },
            )
        return (TextQueryFormulator.SEMANTIC_SVO_QUERY, [])

    def concepts(self, tkeir_doc, advanced_querying: dict):
        concept_list = dict()

        for kg_item in tkeir_doc["kg"]:
            if (kg_item["field_type"] == "concept") and (kg_item["property"]["content"] == "rel:has-concept"):
                if kg_item["value"]["content"] not in concept_list:
                    concept_list[kg_item["value"]["content"]] = 0
                concept_list[kg_item["value"]["content"]] = concept_list[kg_item["value"]["content"]] + 1
        count_max = 0
        count_min = 1000000
        for k in concept_list:
            if count_max < concept_list[k]:
                count_max = concept_list[k]
            if count_min > concept_list[k]:
                count_min = concept_list[k]
        concept_boosting = advanced_querying["querying"]["match-concept"]["concept-boosting"]
        if count_min == count_max:
            count_max = count_min + 1
        for k in concept_list:
            concept_list[k] = concept_boosting * (concept_list[k] - count_min + 0.001) / (count_max - count_min)
        concept_list = list(sorted(concept_list.items(), key=lambda x: x[1], reverse=True))
        return (TextQueryFormulator.CONCEPT_QUERY, concept_list)

    def generateQuery(self, scoredQueries: list, advanced_querying: dict):
        clauses = []
        text_query = set()
        for scoredQuery in scoredQueries:
            # run in content, title and optionally in lemma_content, lemma_title

            lemma_case = [(1, "")]
            if advanced_querying["use-lemma"]:
                lemma_case.append((2, "lemma_"))

            for field in ["content", "title"]:
                for lemma_field in lemma_case:
                    if scoredQuery[0] == TextQueryFormulator.DUMMY_QUERY:
                        if scoredQuery[1][0][lemma_field[0]]:
                            clauses = clauses + [
                                {"match": {lemma_field[1] + field: {"query": scoredQuery[1][0][lemma_field[0]]}}},
                                {
                                    "match": {
                                        lemma_field[1] + field: {"query": scoredQuery[1][0][lemma_field[0]], "operator": "and"}
                                    }
                                },
                            ]
                            text_query = text_query | set(scoredQuery[1][0][lemma_field[0]].split(" "))
                    if scoredQuery[0] == TextQueryFormulator.SENTENCES_QUERY:
                        for sqi in range(len(scoredQuery[1])):
                            if scoredQuery[1][sqi][lemma_field[0]]:
                                clauses = clauses + [
                                    {"match": {lemma_field[1] + field: {"query": scoredQuery[1][sqi][lemma_field[0]]}}},
                                    {
                                        "match": {
                                            lemma_field[1]
                                            + field: {"query": scoredQuery[1][sqi][lemma_field[0]], "operator": "and"}
                                        }
                                    },
                                    {
                                        "match_phrase": {
                                            lemma_field[1]
                                            + field: {
                                                "query": scoredQuery[1][sqi][lemma_field[0]],
                                                "boost": advanced_querying["querying"]["match-phrase-boosting"],
                                                "slop": advanced_querying["querying"]["match-phrase-slop"],
                                            }
                                        }
                                    },
                                ]
                                text_query = text_query | set(scoredQuery[1][sqi][lemma_field[0]].split(" "))

            if scoredQuery[0] == TextQueryFormulator.KEYWORDS_QUERY:
                for sqi in range(len(scoredQuery[1])):
                    if scoredQuery[1][sqi][2]:
                        kw_class_clause = []
                        kw_class_clause.append(
                            {"nested": {"path": "kg.value", "query": {"match": {"kg.value.lemma_content": "keyword"}}}}
                        )
                        kw_class_clause.append(
                            {
                                "nested": {
                                    "path": "kg.subject",
                                    "query": {
                                        "match_phrase": {
                                            "kg.subject.content": {
                                                "query": scoredQuery[1][sqi][2],
                                                "boost": advanced_querying["querying"]["match-phrase-boosting"],
                                                "slop": advanced_querying["querying"]["match-phrase-slop"],
                                            }
                                        }
                                    },
                                }
                            }
                        )
                        clauses.append({"nested": {"path": "kg", "query": {"bool": {"must": kw_class_clause}}}})
                        text_query = text_query | set(scoredQuery[1][sqi][2].split(" "))

            if scoredQuery[0] == TextQueryFormulator.SVO_QUERY:
                for sqi in range(len(scoredQuery[1])):
                    svo_clauses = []
                    for t_i in ["subject", "property", "value"]:
                        if scoredQuery[1][sqi][t_i]["lemma_content"]:
                            q = scoredQuery[1][sqi][t_i]["lemma_content"]
                            if isinstance(q, list):
                                q = " ".join(q)
                            svo_clauses.append(
                                {
                                    "nested": {
                                        "path": "kg." + t_i,
                                        "query": {
                                            "match_phrase": {
                                                "kg."
                                                + t_i
                                                + ".lemma_content": {
                                                    "query": q,
                                                    "slop": advanced_querying["querying"]["match-phrase-slop"],
                                                }
                                            }
                                        },
                                    }
                                }
                            )
                            text_query = text_query | set(q.split(" "))
                    if svo_clauses:
                        clauses.append({"nested": {"path": "kg", "query": {"bool": {"must": svo_clauses}}}})
            if scoredQuery[0] == TextQueryFormulator.SEMANTIC_KEYWORDS_QUERY:
                for sqi in range(len(scoredQuery[1])):
                    if scoredQuery[1][sqi][0]:
                        kw_class_clause = []
                        kw_class_clause.append(
                            {"nested": {"path": "kg.value", "query": {"match": {"kg.value.lemma_content": "keyword"}}}}
                        )
                        kw_class_clause.append(
                            {
                                "nested": {
                                    "path": "kg.subject",
                                    "query": {
                                        "match_phrase": {
                                            "kg.subject.class": {
                                                "query": scoredQuery[1][sqi][0],
                                                "boost": scoredQuery[1][sqi][1],
                                            }
                                        }
                                    },
                                }
                            }
                        )
                        clauses.append({"nested": {"path": "kg", "query": {"bool": {"must": kw_class_clause}}}})
            if scoredQuery[0] == TextQueryFormulator.CONCEPT_QUERY:

                max_clause = advanced_querying["querying"]["match-concept"]["concept-pruning"]
                count_clause = 0
                for sqi in range(len(scoredQuery[1])):
                    if scoredQuery[1][sqi][0]:
                        if count_clause > max_clause:
                            break
                        count_clause = count_clause + 1
                        concept_clause = []
                        concept_clause.append(
                            {"nested": {"path": "kg.property", "query": {"match": {"kg.property.content": "rel:has-concept"}}}}
                        )
                        concept_clause.append(
                            {
                                "nested": {
                                    "path": "kg.subject",
                                    "query": {
                                        "match_phrase": {
                                            "kg.subject.content": {
                                                "query": scoredQuery[1][sqi][0],
                                                "boost": scoredQuery[1][sqi][1],
                                            }
                                        }
                                    },
                                }
                            }
                        )
                        text_query = text_query | set(scoredQuery[1][sqi][0].split(" "))
                        clauses.append({"nested": {"path": "kg", "query": {"bool": {"must": concept_clause}}}})

            if scoredQuery[0] == TextQueryFormulator.SEMANTIC_SVO_QUERY:
                if advanced_querying["querying"]["match-svo"]["semantic-use-class-triple"]:
                    for item_i in scoredQuery[1]["semantic-use-class-triple"]:
                        item = item_i[1]
                        clauses.append(
                            {
                                "nested": {
                                    "path": "kg",
                                    "query": {
                                        "bool": {
                                            "must": [
                                                {
                                                    "nested": {
                                                        "path": "kg.subject",
                                                        "query": {
                                                            "match": {"kg.subject.class": item["item"]["subject"]["class"]}
                                                        },
                                                    }
                                                },
                                                {
                                                    "nested": {
                                                        "path": "kg.property",
                                                        "query": {
                                                            "match": {"kg.property.class": item["item"]["property"]["class"]}
                                                        },
                                                    }
                                                },
                                                {
                                                    "nested": {
                                                        "path": "kg.value",
                                                        "query": {"match": {"kg.value.class": item["item"]["value"]["class"]}},
                                                    }
                                                },
                                            ]
                                        }
                                    },
                                }
                            }
                        )
                if advanced_querying["querying"]["match-svo"]["semantic-use-lemma-property-object"]:
                    for item_i in scoredQuery[1]["semantic-use-lemma-property-object"]:
                        item = item_i[1]
                        clauses.append(
                            {
                                "nested": {
                                    "path": "kg",
                                    "query": {
                                        "bool": {
                                            "must": [
                                                {
                                                    "nested": {
                                                        "path": "kg.subject",
                                                        "query": {
                                                            "match_phrase": {
                                                                "kg.subject.lemma_content": {
                                                                    "query": item["item"]["subject"]["lemma_content"],
                                                                    "boost": advanced_querying["querying"][
                                                                        "match-phrase-boosting"
                                                                    ],
                                                                    "slop": advanced_querying["querying"]["match-phrase-slop"],
                                                                }
                                                            }
                                                        },
                                                    }
                                                },
                                                {
                                                    "nested": {
                                                        "path": "kg.property",
                                                        "query": {
                                                            "match": {"kg.property.class": item["item"]["property"]["class"]}
                                                        },
                                                    }
                                                },
                                                {
                                                    "nested": {
                                                        "path": "kg.value",
                                                        "query": {"match": {"kg.value.class": item["item"]["value"]["class"]}},
                                                    }
                                                },
                                            ]
                                        }
                                    },
                                }
                            }
                        )
                        s_lemma_content = item["item"]["subject"]["lemma_content"]
                        if not isinstance(s_lemma_content, list):
                            s_lemma_content = item["item"]["subject"]["lemma_content"].split(" ")
                        text_query = text_query | set(s_lemma_content)
                if advanced_querying["querying"]["match-svo"]["semantic-use-subject-lemma-object"]:
                    for item_i in scoredQuery[1]["semantic-use-subject-lemma-object"]:
                        item = item_i[1]
                        clauses.append(
                            {
                                "nested": {
                                    "path": "kg",
                                    "query": {
                                        "bool": {
                                            "must": [
                                                {
                                                    "nested": {
                                                        "path": "kg.subject",
                                                        "query": {
                                                            "match": {"kg.subject.class": item["item"]["subject"]["class"]}
                                                        },
                                                    }
                                                },
                                                {
                                                    "nested": {
                                                        "path": "kg.property",
                                                        "query": {
                                                            "match_phrase": {
                                                                "kg.property.lemma_content": {
                                                                    "query": item["item"]["property"]["lemma_content"],
                                                                    "boost": advanced_querying["querying"][
                                                                        "match-phrase-boosting"
                                                                    ],
                                                                    "slop": advanced_querying["querying"]["match-phrase-slop"],
                                                                }
                                                            }
                                                        },
                                                    }
                                                },
                                                {
                                                    "nested": {
                                                        "path": "kg.value",
                                                        "query": {"match": {"kg.value.class": item["item"]["value"]["class"]}},
                                                    }
                                                },
                                            ]
                                        }
                                    },
                                }
                            }
                        )
                        p_lemma_content = item["item"]["property"]["lemma_content"]
                        if not isinstance(p_lemma_content, list):
                            p_lemma_content = item["item"]["property"]["lemma_content"].split(" ")
                        text_query = text_query | set(p_lemma_content)
                if advanced_querying["querying"]["match-svo"]["semantic-use-subject-property-lemma"]:
                    for item_i in scoredQuery[1]["semantic-use-subject-property-lemma"]:
                        item = item_i[1]
                        clauses.append(
                            {
                                "nested": {
                                    "path": "kg",
                                    "query": {
                                        "bool": {
                                            "must": [
                                                {
                                                    "nested": {
                                                        "path": "kg.subject",
                                                        "query": {
                                                            "match": {"kg.subject.class": item["item"]["subject"]["class"]}
                                                        },
                                                    }
                                                },
                                                {
                                                    "nested": {
                                                        "path": "kg.property",
                                                        "query": {
                                                            "match": {"kg.property.class": item["item"]["property"]["class"]}
                                                        },
                                                    }
                                                },
                                                {
                                                    "nested": {
                                                        "path": "kg.value",
                                                        "query": {
                                                            "match_phrase": {
                                                                "match": {
                                                                    "kg.value.lemma_content": {
                                                                        "query": item["item"]["value"]["lemma_content"],
                                                                        "boost": advanced_querying["querying"][
                                                                            "match-phrase-boosting"
                                                                        ],
                                                                        "slop": advanced_querying["querying"][
                                                                            "match-phrase-slop"
                                                                        ],
                                                                    }
                                                                }
                                                            }
                                                        },
                                                    }
                                                },
                                            ]
                                        }
                                    },
                                }
                            }
                        )
                        v_lemma_content = item["item"]["value"]["lemma_content"]
                        if not isinstance(v_lemma_content, list):
                            v_lemma_content = item["item"]["value"]["lemma_content"].split(" ")
                        text_query = text_query | set(v_lemma_content)
                if advanced_querying["querying"]["match-svo"]["semantic-use-lemma-lemma-object"]:
                    for item_i in scoredQuery[1]["semantic-use-lemma-lemma-object"]:
                        item = item_i[1]
                        clauses.append(
                            {
                                "nested": {
                                    "path": "kg",
                                    "query": {
                                        "bool": {
                                            "must": [
                                                {
                                                    "nested": {
                                                        "path": "kg.subject",
                                                        "query": {
                                                            "match_phrase": {
                                                                "kg.subject.lemma_content": {
                                                                    "query": item["item"]["subject"]["lemma_content"],
                                                                    "boost": advanced_querying["querying"][
                                                                        "match-phrase-boosting"
                                                                    ],
                                                                    "slop": advanced_querying["querying"]["match-phrase-slop"],
                                                                }
                                                            }
                                                        },
                                                    }
                                                },
                                                {
                                                    "nested": {
                                                        "path": "kg.property",
                                                        "query": {
                                                            "match_phrase": {
                                                                "kg.property.lemma_content": {
                                                                    "query": item["item"]["property"]["lemma_content"],
                                                                    "boost": advanced_querying["querying"][
                                                                        "match-phrase-boosting"
                                                                    ],
                                                                    "slop": advanced_querying["querying"]["match-phrase-slop"],
                                                                }
                                                            }
                                                        },
                                                    }
                                                },
                                                {
                                                    "nested": {
                                                        "path": "kg.value",
                                                        "query": {"match": {"kg.value.class": item["item"]["value"]["class"]}},
                                                    }
                                                },
                                            ]
                                        }
                                    },
                                }
                            }
                        )
                        s_lemma_content = item["item"]["subject"]["lemma_content"]
                        if not isinstance(s_lemma_content, list):
                            s_lemma_content = item["item"]["subject"]["lemma_content"].split(" ")
                        p_lemma_content = item["item"]["property"]["lemma_content"]
                        if not isinstance(p_lemma_content, list):
                            p_lemma_content = item["item"]["property"]["lemma_content"].split(" ")
                        text_query = text_query | set(s_lemma_content)
                        text_query = text_query | set(p_lemma_content)
                if advanced_querying["querying"]["match-svo"]["semantic-use-lemma-property-lemma"]:
                    for item_i in scoredQuery[1]["semantic-use-lemma-property-lemma"]:
                        item = item_i[1]
                        clauses.append(
                            {
                                "nested": {
                                    "path": "kg",
                                    "query": {
                                        "bool": {
                                            "must": [
                                                {
                                                    "nested": {
                                                        "path": "kg.subject",
                                                        "query": {
                                                            "match_phrase": {
                                                                "kg.subject.lemma_content": {
                                                                    "query": item["item"]["subject"]["lemma_content"],
                                                                    "boost": advanced_querying["querying"][
                                                                        "match-phrase-boosting"
                                                                    ],
                                                                    "slop": advanced_querying["querying"]["match-phrase-slop"],
                                                                }
                                                            }
                                                        },
                                                    }
                                                },
                                                {
                                                    "nested": {
                                                        "path": "kg.property",
                                                        "query": {
                                                            "match": {"kg.property.class": item["item"]["property"]["class"]}
                                                        },
                                                    }
                                                },
                                                {
                                                    "nested": {
                                                        "path": "kg.value",
                                                        "query": {
                                                            "match_phrase": {
                                                                "kg.value.lemma_content": {
                                                                    "query": item["item"]["value"]["lemma_content"],
                                                                    "boost": advanced_querying["querying"][
                                                                        "match-phrase-boosting"
                                                                    ],
                                                                    "slop": advanced_querying["querying"]["match-phrase-slop"],
                                                                }
                                                            }
                                                        },
                                                    }
                                                },
                                            ]
                                        }
                                    },
                                }
                            }
                        )
                        s_lemma_content = item["item"]["subject"]["lemma_content"]
                        if not isinstance(s_lemma_content, list):
                            s_lemma_content = item["item"]["subject"]["lemma_content"].split(" ")
                        v_lemma_content = item["item"]["value"]["lemma_content"]
                        if not isinstance(v_lemma_content, list):
                            v_lemma_content = item["item"]["value"]["lemma_content"].split(" ")
                        text_query = text_query | set(s_lemma_content)
                        text_query = text_query | set(v_lemma_content)
                if advanced_querying["querying"]["match-svo"]["semantic-use-subject-lemma-lemma"]:
                    for item_i in scoredQuery[1]["semantic-use-subject-lemma-lemma"]:
                        item = item_i[1]
                        clauses.append(
                            {
                                "nested": {
                                    "path": "kg",
                                    "query": {
                                        "bool": {
                                            "must": [
                                                {
                                                    "nested": {
                                                        "path": "kg.subject",
                                                        "query": {
                                                            "match": {"kg.subject.class": item["item"]["subject"]["class"]}
                                                        },
                                                    }
                                                },
                                                {
                                                    "nested": {
                                                        "path": "kg.property",
                                                        "query": {
                                                            "match_phrase": {
                                                                "kg.property.lemma_content": {
                                                                    "query": item["item"]["property"]["lemma_content"],
                                                                    "boost": advanced_querying["querying"][
                                                                        "match-phrase-boosting"
                                                                    ],
                                                                    "slop": advanced_querying["querying"]["match-phrase-slop"],
                                                                }
                                                            }
                                                        },
                                                    }
                                                },
                                                {
                                                    "nested": {
                                                        "path": "kg.value",
                                                        "query": {
                                                            "match_phrase": {
                                                                "kg.value.lemma_content": {
                                                                    "query": item["item"]["value"]["lemma_content"],
                                                                    "boost": advanced_querying["querying"][
                                                                        "match-phrase-boosting"
                                                                    ],
                                                                    "slop": advanced_querying["querying"]["match-phrase-slop"],
                                                                }
                                                            }
                                                        },
                                                    }
                                                },
                                            ]
                                        }
                                    },
                                }
                            }
                        )
                        v_lemma_content = item["item"]["value"]["lemma_content"]
                        if not isinstance(v_lemma_content, list):
                            v_lemma_content = item["item"]["value"]["lemma_content"].split(" ")
                        p_lemma_content = item["item"]["property"]["lemma_content"]
                        if not isinstance(p_lemma_content, list):
                            p_lemma_content = item["item"]["property"]["lemma_content"].split(" ")
                        text_query = text_query | set(p_lemma_content)
                        text_query = text_query | set(v_lemma_content)

        # import json
        # print(json.dumps(clauses,indent=1))
        return (clauses, text_query)
