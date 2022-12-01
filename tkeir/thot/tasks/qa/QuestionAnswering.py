"""Question answering 
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

from transformers import pipeline
import traceback
import os
import nltk
from nltk.corpus import stopwords
import re
from thot.core.Utils import ThotTokenizerToSpacy
from thot.core.ThotLogger import ThotLogger, LogUserContext
import thot.core.Constants as Constants
from thot.tasks.qa.QuestionAnsweringConfiguration import QuestionAnsweringConfiguration


class QuestionAnswering:
    def __init__(self, config: QuestionAnsweringConfiguration = None, call_context=None):
        nltk.download("stopwords")
        
        
        self.config = config
        self._qamodel = None
        if "settings" not in config.configuration:
            config.configuration["settings"] = {"max-document-words": 450, "language": "en"}
        if "max-document-words" not in config.configuration["settings"]:
            config.configuration["settings"]["max-document-words"] = 450
        if "model-path-or-name" in config.configuration["settings"]:
            os.environ['TRANSFORMERS_CACHE'] = config.configuration["settings"]["model-path-or-name"]
            os.environ['HF_HOME'] = config.configuration["settings"]["model-path-or-name"]
            os.environ['XDG_CACHE_HOME'] = config.configuration["settings"]["model-path-or-name"]
            ThotLogger.info("Put model in directory:"+os.environ['TRANSFORMERS_CACHE'], context=call_context)
        if "language" not in config.configuration["settings"]:
            config.configuration["settings"]["language"] = "en"
        if config.configuration["settings"]["language"] == "en":
            ThotLogger.info("Load [en] Q/A model", context=call_context)
            dev=0
            if "device" in  config.configuration["settings"]:
                dev=config.configuration["settings"]["device"]
                self._qamodel = pipeline("question-answering",device=dev)
            else:
                self._qamodel = pipeline("question-answering")
            ThotLogger.info("Run on device "+str(dev))
            self.stop_words = set(stopwords.words("english"))
        elif config.configuration["settings"]["language"] == "fr":
            ThotLogger.info("Load [fr] Q/A model", context=call_context)
            self._qamodel = pipeline(
                "question-answering",
                model="etalab-ia/camembert-base-squadFR-fquad-piaf",
                tokenizer="etalab-ia/camembert-base-squadFR-fquad-piaf"
            )
            self.stop_words = set(stopwords.words("french"))
        if self._qamodel == None:
            raise ValueError("Model Not loaded")

    def _getSentences(self, msTokens):
        sentences = []
        current_sentence = ""
        for tok in msTokens:
            if tok["is_sent_start"]:
                if current_sentence:
                    sentences.append(current_sentence)
                current_sentence = ""
            if tok["pos"] != "PUNCT":
                current_sentence = current_sentence + " " + tok["text"]
        if current_sentence:
            sentences.append(current_sentence.strip())
        return sentences

    def questionAnsweringByTKeirDoc(self, qtkeir_doc, call_context=None):
        qas = []
        query = qtkeir_doc["query"]
        tkeir_doc = qtkeir_doc["doc"]
        if ("title_morphosyntax" not in tkeir_doc) and ("content_morphosyntax" not in tkeir_doc):
            raise ValueError("title_morphosyntax and/or content_morphosyntax should be defined")
        if self._qamodel:
            texts = []
            texts = texts + self._getSentences(tkeir_doc["title_morphosyntax"])
            texts = texts + self._getSentences(tkeir_doc["content_morphosyntax"])
            try:
                for text in texts:
                    answer = self._qamodel(question=query, context=text)
                    if len(answer["answer"]) > 0:
                        qas.append(answer)
            except Exception as e:
                ThotLogger.error(
                    "Exception occured.",
                    trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
                    context=call_context,
                )
        if "qa" not in tkeir_doc:
            tkeir_doc["qa"] = []

        if qas:
            qas = sorted(qas, key=lambda x: x["score"], reverse=True)
            dqas = []
            if len(qas):
                dqas = qas[0]
            tkeir_doc["qa"].append({"query": query, "sentences": qas, "doc": dqas})
        return tkeir_doc

    def check_query_word_existance(self, qtoks, lc_text):
        score = 0.0
        count = 0.0
        for qw_tok in qtoks:
            qw = qw_tok.lower()
            if qw not in self.stop_words:
                count = count + 1
                if qw in lc_text:
                    score = score + 1.0
        if count > 0.0:
            score = score / count
        return score

    def questionAnsweringBySentenceBlocks(self, query, texts, call_context=None):
        qas = []
        s = re.sub("([.;,!?()])", r" \1 ", query.lower())
        s = re.sub("\s{2,}", " ", s)
        qtoks = s.lower().split(" ")
        if self._qamodel:
            try:
                # group texts
                qa_texts = []
                q_scores = []
                current_text = ""
                for text in texts:
                    if len(current_text.split(" ")) < self.config.configuration["settings"]["max-document-words"]:
                        current_text = current_text + " " + text
                    else:
                        lc_text = current_text.lower()
                        score = self.check_query_word_existance(qtoks, lc_text)
                        if score > 0.0:
                            qa_texts.append(current_text)
                            q_scores.append(score)
                        current_text = ""
                if current_text:
                    lc_text = current_text.lower()
                    score = self.check_query_word_existance(qtoks, lc_text)
                    if score > 0.0:
                        qa_texts.append(current_text)
                        q_scores.append(score)
                for text_i in range(len(qa_texts)):
                    text = qa_texts[text_i]
                    answer = self._qamodel(question=query, context=text)
                    answer["sentence"] = text
                    if len(answer["answer"]) > 0:
                        answer["score"] = answer["score"] * q_scores[text_i]
                        qas.append(answer)
            except Exception as e:
                ThotLogger.error(
                    "Exception occured.",
                    trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
                    context=call_context,
                )
        if qas:
            uniq_answer = dict()
            for answer in qas:
                if answer["answer"] not in uniq_answer:
                    uniq_answer[answer["answer"]] = {"count": 0, "score": 0.0, "positions": [], "answer": answer["answer"]}
                uniq_answer[answer["answer"]]["count"] = uniq_answer[answer["answer"]]["count"] + 1
                uniq_answer[answer["answer"]]["score"] = uniq_answer[answer["answer"]]["score"] + answer["score"]
                uniq_answer[answer["answer"]]["positions"].append({"start": answer["start"], "end": answer["end"]})
                uniq_answer[answer["answer"]]["sentence"] = answer["sentence"]
            qas = []
            for a in uniq_answer:
                uniq_answer[a]["score"] = uniq_answer[a]["score"] / uniq_answer[a]["count"]
                qas.append(uniq_answer[a])
            qas = sorted(qas, key=lambda x: x["score"], reverse=True)

        dqas = []
        if len(qas):
            dqas = qas[0]
        return {"query": query, "sentences": qas, "doc": dqas}
