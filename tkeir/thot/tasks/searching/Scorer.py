# -*- coding: utf-8 -*-
"""Scorer
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""


class Scorer:

    NO_NORMALIZATION = -1
    NORMALIZE_BY_QUERY_SIZE = 0
    NORMALIZE_BY_DOCUMENT_SIZE = 1
    NORMALIZE_BY_UNION_SIZE = 2
    NORMALIZE_BY_INTERSECTION_SIZE = 3
    INTERSECTION_SIZE = 4

    SCORE_MAPPING = {
        "no-normalization": -1,
        "by-query-size": 0,
        "by-document-size": 1,
        "by-union-size": 2,
        "by-intersection-size": 3,
        "intersection-size": 4,
    }

    @staticmethod
    def documentQueryIntersectionScore(query=None, document=None, normalize=0):
        doc_set = set()
        q_set = set()
        if ((query is None) and (document is None)) or (normalize == -1):
            return 1.0
        if (query is None) or (document is None):
            return 0.0
        for field in document["term_vectors"]:
            if field in query["term_vectors"]:
                doc_set = doc_set | set(document["term_vectors"][field]["terms"].keys())
                q_set = q_set | set(query["term_vectors"][field]["terms"].keys())
        common_terms = doc_set & q_set
        if normalize == Scorer.INTERSECTION_SIZE:
            if len(common_terms):
                return 1 / float(len(common_terms))
            return 0.0
        if normalize == Scorer.NORMALIZE_BY_UNION_SIZE:
            norm = float(len(doc_set | q_set))
        elif normalize == Scorer.NORMALIZE_BY_DOCUMENT_SIZE:
            norm = float(len(doc_set))
        elif normalize == Scorer.NORMALIZE_BY_QUERY_SIZE:
            norm = float(len(q_set))
        else:
            norm = float(len(doc_set & q_set))
        if norm > 0.0:
            return float(len(common_terms)) / norm
        return 0.0
