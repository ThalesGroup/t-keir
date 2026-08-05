"""Title: Keyword extractor based on RAKE algorithm

Keyword and keyphrase extraction.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import json
import os
from collections import Counter, defaultdict
from enum import Enum
from itertools import chain, groupby, product

from thot.core.KeywordRules import (
    DEFAULT_MIN_KEYWORD_LENGTH,
    is_valid_keyword_label,
)
from thot.core.ThotLogger import ThotLogger
from thot.tasks.keywords.KeywordsConfiguration import KeywordsConfiguration


class Metric(Enum):
    """Different metrics that can be used for ranking.

    Example:
        >>> from thot.tasks.keywords.KeywordsExtractor import Metric
        >>> callable(Metric)
        True
    """

    DEGREE_TO_FREQUENCY_RATIO = 0  # Uses d(w)/f(w) as the metric
    WORD_DEGREE = 1  # Uses d(w) alone as the metric
    WORD_FREQUENCY = 2  # Uses f(w) alone as the metric


class NLTKRake:
    """Rapid Automatic Keyword Extraction Algorithm.

    Example:
        >>> from thot.tasks.keywords.KeywordsExtractor import NLTKRake
        >>> callable(NLTKRake)
        True
    """

    def __init__(
        self,
        ranking_metric=Metric.DEGREE_TO_FREQUENCY_RATIO,
        max_length=5,
        min_length=1,
        validation=dict(),
        settings=dict(),
    ):
        """Constructor.

        :param stopwords: List of Words to be ignored for keyword extraction.
        :param punctuations: Punctuations to be ignored for keyword extraction.
        :param language: Language to be used for stopwords
        :param max_length: Maximum limit on the number of words in a phrase
                           (Inclusive. Defaults to 100000)
        :param min_length: Minimum limit on the number of words in a phrase
                           (Inclusive. Defaults to 1)

                Example:
                    >>> callable(NLTKRake)
                    True
        """
        # By default use degree to frequency ratio as the metric.
        if isinstance(ranking_metric, Metric):
            self.metric = ranking_metric
        else:
            self.metric = Metric.DEGREE_TO_FREQUENCY_RATIO

        self._validation = validation
        self._settings = settings

        # sw POS equivalent
        self._to_ignore = set(
            [
                "ADP",
                "ADV",
                "AUX",
                "CONJ",
                "CCONJ",
                "DET",
                "INTJ",
                "SCONJ",
                "PRON",
                "PUNCT",
                "SYM",
            ]
        )

        # Assign min or max length to the attributes
        self.min_length = min_length
        self.max_length = max_length

        # Stuff to be extracted from the provided text.
        self.frequency_dist = None
        self.degree = None
        self.rank_list = None
        self.ranked_phrases = None

    def flattern_token_list(self, doc_token):
        """flattern_token_list API.

        Example:
            >>> callable(NLTKRake.flattern_token_list)
            True
        """
        flat_tokens = []
        for item in doc_token:
            if isinstance(item, list):
                flat_tokens = flat_tokens + self.flattern_token_list(item)
            else:
                flat_tokens = flat_tokens + [item]
        return flat_tokens

    def extract_keywords_from_tkeir(self, tkeir_doc, section_name):
        """Method to extract keywords from the text provided.

        :param text: Text to extract keywords from, provided as a string.

                Example:
                    >>> callable(NLTKRake.extract_keywords_from_tkeir)
                    True
        """
        field_name_ms = section_name + "_morphosyntax"
        doc_ms = tkeir_doc[field_name_ms]
        sentences = []
        start_sentence = 0
        tok_i = 0
        for tok_i in range(len(doc_ms)):
            if doc_ms[tok_i]["is_sent_start"]:
                if tok_i > start_sentence:
                    sentences.append(doc_ms[start_sentence:tok_i])
                    tok_idx = start_sentence
                    for tok in sentences[-1]:
                        tok["position"] = tok_idx
                        tok_idx = tok_idx + 1
                    start_sentence = tok_i
        if tok_i > start_sentence:
            sentences.append(doc_ms[start_sentence : len(doc_ms)])
            tok_idx = start_sentence
            for tok in sentences[-1]:
                tok["position"] = tok_idx
                tok_idx = tok_idx + 1
        return self.extract_keywords_from_sentences(sentences)

    def extract_keywords_from_sentences(self, sentences):
        """Method to extract keywords from the list of sentences provided.

        :param sentences: Text to extraxt keywords from, provided as a list
                          of strings, where each string is a sentence.

                Example:
                    >>> callable(NLTKRake.extract_keywords_from_sentences)
                    True
        """
        phrase_list = self._generate_phrases(sentences)
        self._build_frequency_dist(phrase_list)
        self._build_word_co_occurance_graph(phrase_list)
        self._build_ranklist(phrase_list)
        return self.rank_list

    def get_ranked_phrases(self):
        """Method to fetch ranked keyword strings.

        :return: List of strings where each string represents an extracted
                 keyword string.

                Example:
                    >>> callable(NLTKRake.get_ranked_phrases)
                    True
        """
        return self.ranked_phrases

    def get_ranked_phrases_with_scores(self):
        """Method to fetch ranked keyword strings along with their scores.

        :return: List of tuples where each tuple is formed of an extracted
                 keyword string and its score. Ex: (5.68, 'Four Scoures')

                Example:
                    >>> callable(NLTKRake.get_ranked_phrases_with_scores)
                    True
        """
        return self.rank_list

    def get_word_frequency_distribution(self):
        """Method to fetch the word frequency distribution in the given text.

        :return: Dictionary (defaultdict) of the format `word -> frequency`.

                Example:
                    >>> callable(NLTKRake.get_word_frequency_distribution)
                    True
        """
        return self.frequency_dist

    def get_word_degrees(self):
        """Method to fetch the degree of words in the given text. Degree can be

        defined as sum of co-occurances of the word with other words in the
        given text.

        :return: Dictionary (defaultdict) of the format `word -> degree`.

                Example:
                    >>> callable(NLTKRake.get_word_degrees)
                    True
        """
        return self.degree

    def _build_frequency_dist(self, phrase_list):
        """Builds frequency distribution of the words in the given body of text.

        :param phrase_list: List of List of strings where each sublist is a
                            collection of words which form a contender phrase.

                Example:
                    >>> callable(NLTKRake._build_frequency_dist)
                    True
        """
        self.frequency_dist = Counter(chain.from_iterable(phrase_list))

    def _build_word_co_occurance_graph(self, phrase_list):
        """Builds the co-occurance graph of words in the given body of text to

        compute degree of each word.

        :param phrase_list: List of List of strings where each sublist is a
                            collection of words which form a contender phrase.

                Example:
                    >>> callable(NLTKRake._build_word_co_occurance_graph)
                    True
        """
        co_occurance_graph = defaultdict(lambda: defaultdict(lambda: 0))
        for phrase in phrase_list:
            # For each phrase in the phrase list, count co-occurances of the
            # word with other words in the phrase.
            #
            # Note: Keep the co-occurances graph as is, to help facilitate its
            # use in other creative ways if required later.
            for word, coword in product(phrase, phrase):
                co_occurance_graph[word][coword] += 1
        self.degree = defaultdict(lambda: 0)
        for key in co_occurance_graph:
            self.degree[key] = sum(co_occurance_graph[key].values())

    def _build_ranklist(self, phrase_list):
        """Method to rank each contender phrase using the formula

        phrase_score = sum of scores of words in the phrase.
              word_score = d(w)/f(w) where d is degree and f is frequency.

        :param phrase_list: List of List of strings where each sublist is a
                            collection of words which form a contender phrase.

                Example:
                    >>> callable(NLTKRake._build_ranklist)
                    True
        """
        self.rank_list = []
        for phrase in phrase_list:
            rank = 0.0
            for word in phrase:
                if self.metric == Metric.DEGREE_TO_FREQUENCY_RATIO:
                    rank += 1.0 * self.degree[word] / self.frequency_dist[word]
                elif self.metric == Metric.WORD_DEGREE:
                    rank += 1.0 * self.degree[word]
                else:
                    rank += 1.0 * self.frequency_dist[word]
            self.rank_list.append(
                (rank, " ".join(phrase), phrase_list[phrase])
            )
        self.rank_list.sort(reverse=True, key=lambda x: x[0])
        self.ranked_phrases = [ph[1] for ph in self.rank_list]

    def _generate_phrases(self, sentences):
        """Method to generate contender phrases given the sentences of the text

        document.

        :param sentences: List of strings where each string represents a
                          sentence which forms the text.
        :return: Set of string tuples where each tuple is a collection
                 of words forming a contender phrase.

                Example:
                    >>> callable(NLTKRake._generate_phrases)
                    True
        """
        phrase_list = dict()
        # Create contender phrases from sentences.
        for sentence in sentences:
            phrase_items = self._get_phrase_list_from_words(sentence)
            for phrase in phrase_items:
                dict_entry = []
                discard = False
                at_least_discard = False

                if self._validation:
                    at_least_discard = True
                    for tok in phrase:
                        if tok["pos"] not in self._validation["possible"]:
                            discard = True
                        if tok["lemma"] == "_":
                            discard = True
                        if tok["pos"] in self._validation["at-least"]:
                            at_least_discard = False
                if (not at_least_discard) and (not discard):
                    for tok in phrase:
                        dict_entry.append(tok["lemma"].lower())
                    phrase_list[tuple(dict_entry)] = phrase
        return phrase_list

    def _get_phrase_list_from_words(self, word_list):
        """Method to create contender phrases from the list of words that form

        a sentence by dropping stopwords and punctuations and grouping the left
        words into phrases. Only phrases in the given length range (both limits
        inclusive) would be considered to build co-occurrence matrix. Ex:

        Sentence: Red apples, are good in flavour.
        List of words: ['red', 'apples', ",", 'are', 'good', 'in', 'flavour']
        List after dropping punctuations and stopwords.
        List of words: ['red', 'apples', *, *, good, *, 'flavour']
        List of phrases: [('red', 'apples'), ('good',), ('flavour',)]

        List of phrases with a correct length:
        For the range [1, 2]: [('red', 'apples'), ('good',), ('flavour',)]
        For the range [1, 1]: [('good',), ('flavour',)]
        For the range [2, 2]: [('red', 'apples')]

        :param word_list: List of words which form a sentence when joined in
                          the same order.
        :return: List of contender phrases that are formed after dropping
                 stopwords and punctuations.

                Example:
                    >>> callable(NLTKRake._get_phrase_list_from_words)
                    True
        """
        groups = groupby(word_list, lambda x: x["pos"] not in self._to_ignore)
        phrases = [tuple(group[1]) for group in groups if group[0]]
        return list(
            filter(
                lambda x: self.min_length <= len(x) <= self.max_length, phrases
            )
        )


class KeywordsExtractor:
    """KeywordsExtractor container.

    Example:
        >>> from thot.tasks.keywords.KeywordsExtractor import KeywordsExtractor
        >>> callable(KeywordsExtractor)
        True
    """

    def __init__(
        self, config: KeywordsConfiguration = None, call_context=None
    ):
        """Initialize tagger

        Args:
            config (KeywordsConfiguration, optional): The tagger configuration. Defaults to None.

        Raises:
            ValueError: If configuration is not set
            ValueError: If language is not managed

                Example:
                    >>> callable(KeywordsExtractor)
                    True
        """
        self.kw_prunning = 5
        if "prunning" in config.configuration["extractors"][0]:
            self.kw_prunning = config.configuration["extractors"][0][
                "prunning"
            ]
        extractor_cfg = config.configuration["extractors"][0]
        self.min_keyword_length = int(
            extractor_cfg.get(
                "min-keyword-length",
                DEFAULT_MIN_KEYWORD_LENGTH,
            )
        )
        self.min_keyword_length = max(1, self.min_keyword_length)
        self._config = config
        self._kw_validation = dict()
        self._kw_settings = {
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
        if not config:
            raise ValueError("configuration is mandatory")
        if "keywords-rules" in self._config.configuration["extractors"][0]:
            ner_rules = os.path.join(
                self._config.configuration["extractors"][0][
                    "resources-base-path"
                ],
                self._config.configuration["extractors"][0]["keywords-rules"],
            )
            ThotLogger.info("Load rules:" + ner_rules, context=call_context)
            with open(ner_rules) as json_f:
                kw_rules_data = json.load(json_f)
                if "keywords-pos-validation" in kw_rules_data:
                    if (
                        "possible-pos-in-syntagm"
                        in kw_rules_data["keywords-pos-validation"]
                    ) and (
                        "at-least" in kw_rules_data["keywords-pos-validation"]
                    ):
                        self._kw_validation = {
                            "possible": set(
                                kw_rules_data["keywords-pos-validation"][
                                    "possible-pos-in-syntagm"
                                ]
                            ),
                            "at-least": set(
                                kw_rules_data["keywords-pos-validation"][
                                    "at-least"
                                ]
                            ),
                        }
                    ThotLogger.info(
                        "["
                        + str(len(self._kw_validation))
                        + "] Validation rules Loaded.",
                        context=call_context,
                    )
                if "settings" in kw_rules_data:
                    if "suppress-bounds-sw" in kw_rules_data["settings"]:
                        self._kw_settings["suppress-bounds-sw"] = (
                            kw_rules_data["settings"]["suppress-bounds-sw"]
                        )
                    if "pos-to-suppress" in kw_rules_data["settings"]:
                        self._kw_settings["pos-to-suppress"] = set(
                            kw_rules_data["settings"]["pos-to-suppress"]
                        )

    def getKeywords(self, tkeir_doc: dict):
        """Run the getKeywords task step on a T-KEIR document.

        Example:
            >>> callable(KeywordsExtractor.getKeywords)
            True
        """
        if ("title_morphosyntax" not in tkeir_doc) and (
            "content_morphosyntax" not in tkeir_doc
        ):
            raise ValueError("Morphosyntax analysis should be performed")

        keywords = []
        if "title_morphosyntax" in tkeir_doc:
            rake = NLTKRake(
                validation=self._kw_validation,
                settings=self._kw_settings,
                max_length=self.kw_prunning,
            )
            keywords = rake.extract_keywords_from_tkeir(tkeir_doc, "title")
        if "content_morphosyntax" in tkeir_doc:
            rake = NLTKRake(
                validation=self._kw_validation,
                settings=self._kw_settings,
                max_length=self.kw_prunning,
            )
            keywords = keywords + rake.extract_keywords_from_tkeir(
                tkeir_doc, "content"
            )
        kw_list = []
        for kw in keywords:
            text = str(kw[1]).strip()
            if not is_valid_keyword_label(
                text,
                min_length=self.min_keyword_length,
            ):
                continue
            kw_list.append(
                {
                    "score": int(kw[0]),
                    "text": text,
                    "span": {
                        "start": kw[2][0]["position"],
                        "end": kw[2][-1]["position"] + 1,
                    },
                }
            )
        tkeir_doc["keywords"] = kw_list
        return tkeir_doc

    def run(self, tkeir_doc):
        """Run the run task step on a T-KEIR document.

        Example:
            >>> callable(KeywordsExtractor.run)
            True
        """
        return self.getKeywords(tkeir_doc)
