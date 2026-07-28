"""Tokenizer

Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
import traceback
import string
import pickle
import os
import re
import time
import spacy
import nltk
from thot.core.DictionaryTrie import make_trie, prefix_trie, end_trie

import json
import gc

from spacy.language import Language
from spacy.util import compile_infix_regex, compile_suffix_regex, compile_prefix_regex
from spacy.tokens import Doc, Token

from thot.core.DictionaryTrie import Trie
from thot.core.ThotLogger import ThotLogger
from thot.core.Constants import exception_error_and_trace
from thot.tasks.tokenizer.TokenizerConfiguration import TokenizerConfiguration

from thot.tasks.tokenizer import __version_tokenizer__, __date_tokenizer__
from thot.tasks.TaskInfo import TaskInfo


class SpacyTokenizerPipe:
    def __init__(self, nlp: Doc = None, config: dict = None, call_context=None):
        if not config:
            raise ValueError("Spacy Tokenizer module needs tokenizer configuration")
        self._mwes = None
        self._normalizer = dict()
        self._typos = dict()
        self._nlp = nlp
        try:
            mwefile = os.path.join(config["segmenters"][0]["resources-base-path"], config["segmenters"][0]["mwe"])
            ThotLogger.info("Load tokenizer:" + mwefile, context=call_context)
            with open(mwefile, "rb") as pattern_f:
                self._mwes = pickle.load(pattern_f)
                self._punctuation_words = make_trie(set(self._mwes["punctuated-words"]))
                self._mwes["punctuated-words"] = None
                gc.collect()
        except Exception as e:
            ThotLogger.warning(
                "Exception occured", trace=exception_error_and_trace(str(e), str(traceback.format_exc())), context=call_context
            )
        try:
            if "normalization-rules" in config["segmenters"][0]:
                nfile = os.path.join(
                    config["segmenters"][0]["resources-base-path"], config["segmenters"][0]["normalization-rules"]
                )
                with open(nfile) as norm_f:
                    norm_json = json.load(norm_f)
                    norm_f.close()
                    if "normalization" in norm_json:
                        if "word-mapping" in norm_json["normalization"]:
                            for norm_mapper_i in norm_json["normalization"]["word-mapping"]:
                                self._normalizer[norm_mapper_i["from"].lower()] = norm_mapper_i["to"].lower()
                        if "typos" in norm_json["normalization"]:
                            for typos_mapper_i in norm_json["normalization"]["typos"]:
                                self._typos[typos_mapper_i["misspelling"].lower()] = typos_mapper_i["correct"].lower()

                ThotLogger.info("Load normalization tokenizer:" + nfile, context=call_context)
        except Exception as e:
            ThotLogger.warning(
                "Exception occured.", trace=exception_error_and_trace(str(e), str(traceback.format_exc())), context=call_context
            )

    def _normalize_word(self, word):
        if word.lower() in self._typos:
            normalized_word = self._typos[word.lower()]
            if word.isupper():
                normalized_word = normalized_word.upper()
            elif word[0].isupper():
                normalized_word = normalized_word.title()
            word = normalized_word
            # normalize
        if word.lower() in self._normalizer:
            normalized_word = self._normalizer[word.lower()]
            if word.isupper():
                normalized_word = normalized_word.upper()
            elif word[0].isupper():
                normalized_word = normalized_word.title()
            word = normalized_word
        return word

    def __call__(self, doc: Doc):
        """Call tokenizer trought spacy pipeline

        Args:
            doc ([spacy.Doc]): The spacy doc analyzer

        Returns:
            [spacy.Doc]: The spacy doc tokenized
        """
        words = []
        doc_len = len(doc)
        token_i = 0
        if self._mwes:
            max_word_length = self._mwes["max-word-length"] + 1
            current_word = ""
            token_compounds = []
            trie = self._mwes["trie"]
        while token_i < doc_len:
            token = doc[token_i]
            # fix common typos and normalize
            word = self._normalize_word(token.text)
            if self._mwes:
                wtrie = prefix_trie(self._punctuation_words, word.lower())
                current_pos = token_i + 1
                current_word = word
                compound_table = []
                while wtrie and (len(current_word) < max_word_length) and (current_pos < doc_len):
                    if end_trie(wtrie):
                        compound_table.append(current_pos - 1)
                    current_word = doc[current_pos].text
                    wtrie = prefix_trie(wtrie, current_word.lower())
                    if wtrie and end_trie(wtrie):
                        compound_table.append(current_pos)
                    current_pos = current_pos + 1
                if compound_table:
                    compound_word = doc[token_i : compound_table[-1] + 1]
                    words.append(compound_word.text.replace(" ", ""))
                    token_i = compound_table[-1]
                    token_compounds.append({"data": trie[words[-1].lower()][Trie.LEAF]["label_info"], "is-compound": False})
                else:
                    words.append(word)
                    token_compounds.append(token._.compound_word)
            else:
                words.append(word)
            token_i = token_i + 1

        doc = Doc(doc.vocab, words=words)
        if self._mwes:
            doc_len = len(doc)
            for token_i in range(doc_len):
                doc[token_i]._.compound_word = token_compounds[token_i]
        if self._mwes:
            # compound words
            with doc.retokenize() as retokenizer:
                i = 0
                n = len(doc)
                trie = self._mwes["trie"]

                max_pattern_length = self._mwes["max-pattern-length"] + 1
                max_word_length = self._mwes["max-word-length"] + 1
                while i < n:
                    skip_i = 1
                    if doc[i].text.lower() in self._mwes["trie"]:
                        # possible MWE match
                        j = i
                        trie = self._mwes["trie"]
                        last_trie = None
                        leaf_at = []
                        last_is_hyphen = True
                        trie_tagged_word = False
                        to_pattern_i = i + max_pattern_length
                        if to_pattern_i > len(doc):
                            to_pattern_i = len(doc)

                        while j < to_pattern_i:
                            lower_text = doc[j].text.lower()
                            lower_text = lower_text.strip()
                            if lower_text:
                                if lower_text == "-":
                                    last_is_hyphen = True
                                    hyphen_toks = []
                                else:
                                    last_is_hyphen = False
                                    hyphen_toks = lower_text.split("-")
                                for doc_text in hyphen_toks:
                                    last_trie = trie
                                    if doc_text in trie:
                                        trie = trie[doc_text]
                                        if Trie.LEAF in trie:
                                            leaf_at.append({"data": trie[Trie.LEAF], "idx": j + 1})
                                    elif (i != j) and ("-" in trie):
                                        trie = trie["-"]
                                        if doc_text in trie:
                                            trie = trie[doc_text]
                                            if Trie.LEAF in trie:
                                                leaf_at.append({"data": trie[Trie.LEAF], "idx": j + 1})
                                        else:
                                            trie_tagged_word = True
                                            break
                                    else:
                                        trie_tagged_word = True
                                        break
                                if trie_tagged_word or ((last_trie == trie) and (len(hyphen_toks) > 0)):
                                    break
                            j = j + 1
                        if len(leaf_at) > 0:
                            # success!
                            j_idx = leaf_at[-1]["idx"]
                            if last_is_hyphen:
                                j_idx = j_idx - 1
                            if (j_idx - i) > 1:
                                attrs = {}
                                n = len(doc)
                                retokenizer.merge(doc[i:j_idx], attrs=attrs)
                                doc[i]._.compound_word = {"is-compound": True, "data": leaf_at[-1]["data"]["label_info"]}
                                n = len(doc)
                                skip_i = j_idx - i
                    elif len(set(doc[i].text) & set(string.punctuation + "\\_")) == len(set(doc[i].text)):
                        attrs = {"POS": "PUNCT"}
                        retokenizer.merge(doc[i : i + 1], attrs=attrs)
                    elif doc[i].like_url:
                        attrs = {"POS": "NOUN"}
                        retokenizer.merge(doc[i : i + 1], attrs=attrs)
                    elif doc[i].like_email:
                        attrs = {"POS": "ADJ"}
                        retokenizer.merge(doc[i : i + 1], attrs=attrs)
                    i += skip_i

            return doc


@Language.factory("spacy_thot_tokenizer", default_config={"config": None, "call_context": None})
def spacy_thot_tokenizer(nlp, name, config: dict = None, call_context=None):
    return SpacyTokenizerPipe(nlp=nlp, config=config, call_context=call_context)


class SpacyTokenizer:
    def __init__(self, config: TokenizerConfiguration = None, call_context=None):
        """Initialize spacy tokenizer

        Args:
            config (TokenizerConfiguration, optional): Tokenizer configuration. Defaults to None.

        Raises:
            ValueError: Exception raised when configuration is empty
            ValueError: Exception raised when language is not managed
        """
        nltk.download("punkt")
        if not config:
            raise ValueError("Custom Spacy tokenizer need configuration")
        language = config.configuration["segmenters"][0]["language"]  # TODO : management multiple language
        if language == "en":
            # Load sm model : do not use tagger models
            self._nlp = spacy.load("en_core_web_sm")
            self._sent_tokenizer = nltk.data.load("tokenizers/punkt/english.pickle")
        elif language == "fr":
            self._nlp = spacy.load("fr_core_news_sm")
            self._sent_tokenizer = nltk.data.load("tokenizers/punkt/french.pickle")
        else:
            raise ValueError("Language '" + language + "' not managed.")

        inf = list(self._nlp.Defaults.infixes)  # Default infixes
        inf.remove(r"(?<=[0-9])[+\-\*^](?=[0-9-])")  # Remove the generic op between numbers or between a number and a -
        inf = tuple(inf)  # Convert inf to tuple
        infixes = inf + tuple(
            [r"(?<=[0-9])[+*^](?=[0-9-])", r"(?<=[0-9])-(?=-)"]
        )  # Add the removed rule after subtracting (?<=[0-9])-(?=[0-9]) pattern
        infixes = inf + tuple([r"\.\.\.+", r"[!&,()/;]"])
        infixes = [x for x in infixes if "-|–|—|--|---|——|~" not in x]  # Remove - between letters rule
        infix_re = compile_infix_regex(infixes)

        suf = list(self._nlp.Defaults.suffixes)  # Default infixes
        suf = tuple(suf)
        suffixes = suf + tuple([r"--+", r"~~+", r",,+", r"__+" r"\\\\+", r";;+", r"\?\?+", r"!!+"])
        suffix_re = compile_suffix_regex(suffixes)

        pref = list(self._nlp.Defaults.prefixes)  # Default infixes
        pref = tuple(pref)
        prefixes = pref + tuple([r"[\\\-!?%~,;/_]+"])
        prefix_re = compile_prefix_regex(prefixes)

        self._nlp.tokenizer = spacy.tokenizer.Tokenizer(
            self._nlp.vocab,
            prefix_search=prefix_re.search,
            suffix_search=suffix_re.search,  # self._nlp.tokenizer.suffix_search, #
            infix_finditer=infix_re.finditer,
            token_match=self._nlp.tokenizer.token_match,
            rules=self._nlp.Defaults.tokenizer_exceptions,
        )

        Token.set_extension("compound_word", default={"is-compound": False, "data": {}}, force=True)
        self._nlp.add_pipe("spacy_thot_tokenizer", config={"config": config.configuration, "call_context": call_context})

    def _tokenize_sentence(self, text, call_context=None):
        block_tokens = []
        if isinstance(text, list):
            for text_i in text:
                toks = self._tokenize_sentence(text_i)
                if len(toks) > 0:
                    block_tokens.append(toks)
        else:
            sentences = self._sent_tokenizer.tokenize(text)
            for sent_i in sentences:
                sent = re.sub("\s+", " ", sent_i)
                spacy_doc = self._nlp(sent, disable=["tok2vec", "tagger", "parser", "ner", "attribute_ruler", "lemmatizer"])
                tokens = []
                token_id = 0
                for token in spacy_doc:
                    tokens.append({"token": token.text, "start_sentence": (token_id == 0), "mwe": token._.compound_word})
                    token_id = token_id + 1
                block_tokens.append(tokens)
        return block_tokens

    def tokenize(self, text: str = None, call_context=None):
        """Run spacy tokenization

        Args:
            text (str): text (or array of text) to tokenizer

        Returns:
            [list]: the list of token (structure is equivalent to text but plistted into token)
        """
        tokenized_text = []
        if isinstance(text, list):
            for text_i in text:
                tokenized_text.append(self.tokenize(text_i,call_context=call_context))
        else:
            text = text.strip()
            if text:
                tokenized_text = self._tokenize_sentence(text, call_context=call_context)
        return tokenized_text


class Tokenizer:
    """
    Tokenizer helper integrating MWE tokenizer
    """

    def __init__(self, config: TokenizerConfiguration = None, call_context=None):
        """
        Initialize tokenizer
        :param patterns_file : mwe trie structure (created with createAnnotationResources.py)
        """
        if not config:
            raise ValueError("Tokenizer configuration should be load")
        # Initializer Spacy Tokenizer:
        self._spacyTokenizer = SpacyTokenizer(config=config, call_context=call_context)
        self._count_run = 0

    def tokenize(self, tkeirDoc: dict, call_context=None):
        """Tokenize tkeir doc (generally coming from converter)
           * tokenize "content" into content_tokens
           * tokenize "title"   into title_tokens

        Args:
            tkeirDoc (dict): input tkeir doc to tokenize

        Returns:
            [dict]: tkeir doc with token field added
        """
        tkeirDoc["error"] = False
        es_time = time.time()

        try:
            if ("content" in tkeirDoc) and tkeirDoc["content"]:
                tkeirDoc["content_tokens"] = self._spacyTokenizer.tokenize(tkeirDoc["content"], call_context=call_context)
        except Exception as e:
            tkeirDoc["error"] = True
            ThotLogger.error(
                "Exception occured.", context=call_context, trace=exception_error_and_trace(str(e), str(traceback.format_exc()))
            )
        try:
            if ("title" in tkeirDoc) and tkeirDoc["title"]:
                tkeirDoc["title_tokens"] = self._spacyTokenizer.tokenize(tkeirDoc["title"], call_context=call_context)
        except Exception as e:
            tkeirDoc["error"] = True
            ThotLogger.error(
                "Exception occured.", context=call_context, trace=exception_error_and_trace(str(e), str(traceback.format_exc()))
            )
        if ("content" not in tkeirDoc) and ("title" not in tkeirDoc):
            raise ValueError("content and/or title have to be present in tkeir doc")
        # prevent memory leak
        self._count_run = self._count_run + 1
        if self._count_run > 100:
            gc.collect()
            self._count_run = 0
        taskInfo = TaskInfo(task_name="tokenizer", task_version=__version_tokenizer__, task_date=__date_tokenizer__)
        tkeirDoc = taskInfo.addInfo(tkeirDoc)
        es_time = time.time() - es_time
        ThotLogger.debug("Tokenized time:" + str(es_time), context=call_context)
        es_time = time.time()
        return tkeirDoc

    def run(self, tkeir_doc, call_context=None):
        return self.tokenize(tkeir_doc, call_context=call_context)
