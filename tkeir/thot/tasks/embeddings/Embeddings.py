# -*- coding: utf-8 -*-
"""Embeddings

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
from tkeir.thot.tasks import embeddings
import traceback
from spacy.tokens import Doc
from thot.core.ThotLogger import ThotLogger
import thot.core.Constants as Constants
from thot.tasks.embeddings.EmbeddingsConfiguration import EmbeddingsConfiguration
import torch
from transformers import pipeline, AutoTokenizer, AutoModel
import string


def mean_pooling(model_output, attention_mask):
    """Mean pooling for sentence embeding"""
    token_embeddings = model_output[0]  # First element of model_output contains all token embeddings
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
    sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
    return sum_embeddings / sum_mask


class Embeddings:
    def __init__(self, config: EmbeddingsConfiguration = None, call_context=None):
        """Initialize embeddings

        Args:
            config (EmbeddingsConfiguration, optional): The embeddings configuration. Defaults to None.

        Raises:
            ValueError: If configuration is not set
            ValueError: If language is not managed
        """
        if not config:
            raise ValueError("embeddings configuration is mandatory")
        self.language = config.configuration["models"][0]["language"]  # TODO : management multiple language
        self.use_cuda = True
        self.batch_size = 4
        if "use-cuda" in config.configuration["models"][0]:
            self.use_cuda = config.configuration["models"][0]["use-cuda"]
            ThotLogger.info("use cuda:" + str(self.use_cuda), context=call_context)
        if "batch-size" in config.configuration["models"][0]:
            self.batch_size = config.configuration["models"][0]["batch-size"]
            ThotLogger.info("batch size:" + str(self.batch_size), context=call_context)
        if self.language == "multi":
            if  "model-path-or-name" in config.configuration["models"][0]:
                try:
                    self._sentence_embeddings = {
                        "tokenizer": AutoTokenizer.from_pretrained(config.configuration["models"][0]["model-path-or-name"]),
                        "model": AutoModel.from_pretrained(config.configuration["models"][0]["model-path-or-name"]),
                    }
                except:
                    self._sentence_embeddings = {
                        "tokenizer": AutoTokenizer.from_pretrained("sentence-transformers/LaBSE"),
                        "model": AutoModel.from_pretrained("sentence-transformers/LaBSE"),
                }
            else:
                self._sentence_embeddings = {
                    "tokenizer": AutoTokenizer.from_pretrained("sentence-transformers/LaBSE"),
                    "model": AutoModel.from_pretrained("sentence-transformers/LaBSE"),
                }
            if self.use_cuda:
                try:
                    ThotLogger.info("put model on cuda device", context=call_context)
                    self._sentence_embeddings["model"].to("cuda:0")
                except Exception as e:
                    ThotLogger.warning(
                        "Failed, try without cuda. Exception:",
                        trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
                        context=call_context,
                    )
        else:
            raise ValueError("Language is not managed")

    def _generate_sentences_from_token(self, sent_table, sentence_list, max_length=64):
        """ Generate sentence from tokens list according to a max length sentence size
        Args:
        - sent_table table of sentence
        - sentence_list new list of sentence of size max max_length
        - max_length : max sentence size
        """
        if isinstance(sent_table, list):
            all_are_str = True
            for ti in sent_table:
                if not isinstance(ti, dict):
                    all_are_str = False
            if all_are_str:
                last_split_i = 0
                table = list(map(lambda x: x["token"], sent_table))
                table_size = len(table)

                # punctuation aware split if sentence length exceed "max_length"
                if table_size > max_length:
                    for token_i in range(len(table)):
                        if table[token_i] in string.punctuation:
                            if ((token_i - last_split_i) > 2) and ((token_i - last_split_i) < max_length):
                                sentence = " ".join(table[last_split_i:token_i])
                                last_split_i = token_i
                                sentence_list.append(sentence)
                    if (table_size - last_split_i) < max_length:
                        sentence = " ".join(table[last_split_i:])
                        sentence_list.append(sentence)
                    # hard cut : we tried all possibles "correct split"
                    else:
                        split_size = max_length
                        while split_size >= max_length:
                            sentence = " ".join(table[last_split_i : last_split_i + max_length])
                            sentence_list.append(sentence)
                            last_split_i = last_split_i + max_length
                            split_size = table_size - last_split_i
                        if (split_size > 0) and (last_split_i < table_size):
                            sentence = " ".join(table[last_split_i:])
                            sentence_list.append(sentence)
                else:
                    sentence = " ".join(table)
                    sentence_list.append(sentence)
            else:
                for ti in sent_table:
                    self._generate_sentences_from_token(ti, sentence_list, max_length=max_length)
        elif sent_table and (len(sent_table) > 0) and (isinstance(sent_table, dict)):
            sentence_list.append(sent_table["token"])

    def computeFromTable(self, texts, field=""):
        """ Compute emebeddinds from table
            Args : 
            - texts list of texts
            - field : optional field name
            Returns :
            - list of embeddings
        """
        start_pos = 0
        embedddings = []
        for batch_i in range(0, len(texts), self.batch_size):
            end_batch = batch_i + self.batch_size
            if end_batch > len(texts):
                end_batch = len(texts)
            if end_batch != batch_i:
                if texts:
                    if self.use_cuda:
                        encoded_input = self._sentence_embeddings["tokenizer"](
                            texts[batch_i:end_batch], padding=True, truncation=True, max_length=128, return_tensors="pt"
                        ).to("cuda:0")

                    else:
                        encoded_input = self._sentence_embeddings["tokenizer"](
                            texts[batch_i:end_batch], padding=True, truncation=True, max_length=128, return_tensors="pt"
                        )
                    with torch.no_grad():
                        model_output = self._sentence_embeddings["model"](**encoded_input)
                        sentence_embeddings = mean_pooling(model_output, encoded_input["attention_mask"])
                        for text_i in range(len(texts[batch_i:end_batch])):
                            text_len = len(texts[batch_i + text_i].split())
                            embedddings.append(
                                {
                                    "field": field,
                                    "content": texts[batch_i + text_i],
                                    "embedding": sentence_embeddings[text_i].tolist(),
                                    "position": {"start": start_pos, "length": text_len},
                                }
                            )
                            start_pos = start_pos + text_len
        torch.cuda.empty_cache()
        return embedddings

    def _compute(self, tkeir_doc: dict, field="content_tokens", max_length=64, call_context=None):
        """Compute embeddings on a given field

        Args:
            tkeir_doc (dict): the input document in tkeir format
            field (str, optional): the field on which the mebeddings are computed. Defaults to "content_tokens".

        Raises:
            ValueError: exception raised when the field is not in ["content_tokens","title_contents","noun_chunks","svo", "keywords"]

        Returns:
            [dict]: return the document with embeddings
        """
        if field not in ["content_tokens", "title_tokens", "noun_chunks", "svo", "keywords"]:
            raise ValueError(
                "field should be in " + str(["content_tokens", "title_contents", "noun_chunks", "svo", "keywords"]) + " ."
            )
        if field not in tkeir_doc:
            raise ValueError("Field does not exist in tkeir document")

        try:
            texts = []
            if field in ["content_tokens", "title_tokens"]:
                self._generate_sentences_from_token(tkeir_doc[field], texts, max_length=max_length)
            if "embeddings" not in tkeir_doc:
                ThotLogger.info("Initialize embedding for document", context=call_context)
                tkeir_doc["embeddings"] = []
            embeddings = self.computeFromTable(texts, field)
            if embeddings:
                tkeir_doc["embeddings"] = tkeir_doc["embeddings"] + embeddings
        except Exception as e:
            ThotLogger.error(
                "Exception occured.",
                trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
                context=call_context,
            )

        return tkeir_doc

    def compute(self, tkeir_doc: dict, call_context=None):
        """Compute embeddings on a given field

        Args:
            tkeir_doc (dict): the input document in tkeir format

        Raises:
            ValueError: exception raised when the field is not in ["content_tokens","title_contents","noun_chunks","svo", "keywords"]
            ValueError: exception raised when no computation has been performed

        Returns:
            [dict]: return the document with embeddings
        """
        something_computed = False
        for field_i in ["content_tokens", "title_tokens", "noun_chunks", "svo", "keywords"]:
            if field_i in tkeir_doc:
                tkeir_doc = self._compute(tkeir_doc, field=field_i, call_context=call_context)
                something_computed = True
        if not something_computed:
            raise ValueError("Nothing has been computed, check fields.")
        return tkeir_doc

    def run(self, tkeir_doc, call_context=None):
        return self.compute(tkeir_doc, call_context=call_context)
