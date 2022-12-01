"""Sentiment Analysis
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

from transformers import pipeline
import traceback

from thot.core.Utils import ThotTokenizerToSpacy
from thot.core.ThotLogger import ThotLogger
from thot.core.Constants import exception_error_and_trace
from thot.tasks.TaskInfo import TaskInfo
from thot.tasks.sentiment import __version_sentiment__, __date_sentiment__
from thot.tasks.sentiment.SentimentAnalysisConfiguration import SentimentAnalysisConfiguration


class SentimentAnalysis:
    def loadModelWithLanguage(self, call_context=None):

        if ("use-cuda" in self.config.configuration["settings"]) and self.config.configuration["settings"]["use-cuda"]:
            cuda_device = 0
            if "cuda-device" in self.config.configuration["settings"]:
                cuda_device = self.config.configuration["settings"]["cuda-device"]
            ThotLogger.info("Try to use cuda", context=call_context)
            try:
                self._sentementmodel = pipeline("sentiment-analysis", device=cuda_device)
            except Exception as e:
                ThotLogger.warning("Use cuda failed, default load", context=call_context)
                self._sentementmodel = pipeline("sentiment-analysis")
        else:
            self._sentementmodel = pipeline("sentiment-analysis")

    def __init__(self, config: SentimentAnalysisConfiguration = None, call_context=None):
        self.config = config
        self.loadModelWithLanguage(call_context=call_context)

    def _getSentences(self, msTokens):
        sentences = []
        current_sentence = ""
        count_tokens = 0
        for tok in msTokens:
            if tok["is_sent_start"]:
                if (current_sentence) and (count_tokens > 400):
                    sentences.append(current_sentence.strip())
                    count_tokens = 0
                current_sentence = ""
            # if tok["pos"] != "PUNCT":
            current_sentence = current_sentence + " " + tok["text"]
            count_tokens = count_tokens + 1
        if current_sentence:
            sentences.append(current_sentence.strip())
        return sentences

    def sentimentAnalysisByTextBlocks(self, tkeir_doc, call_context=None):
        sentiments = []
        if ("title_morphosyntax" not in tkeir_doc) and ("content_morphosyntax" not in tkeir_doc):
            raise ValueError("Dependency analysis should be performed")
        if self._sentementmodel:
            texts = []
            texts = texts + self._getSentences(tkeir_doc["title_morphosyntax"])
            texts = texts + self._getSentences(tkeir_doc["content_morphosyntax"])
            doc_sentiment = {"POSITIVE": 0.0, "NEGATIVE": 0.0}
            try:
                for text in texts:
                    try:
                        sentiment_analysis = self._sentementmodel(text)
                        sentiments.append(
                            {"score": sentiment_analysis[0]["score"], "label": sentiment_analysis[0]["label"], "sentence": text}
                        )
                        selected_label = sentiment_analysis[0]["label"]
                        if selected_label == "POSITIVE":
                            unselected_label = "NEGATIVE"
                        else:
                            unselected_label = "POSITIVE"
                        doc_sentiment[selected_label] = doc_sentiment[selected_label] + sentiment_analysis[0]["score"]
                        doc_sentiment[unselected_label] = doc_sentiment[unselected_label] + 1.0 - sentiment_analysis[0]["score"]
                    except Exception as se:
                        ThotLogger.error(
                            "Exception occured.",
                            trace=exception_error_and_trace(str(se), str(traceback.format_exc())),
                            context=call_context,
                        )
                for label in doc_sentiment:
                    doc_sentiment[label] = doc_sentiment[label] / len(texts)
            except Exception as e:
                ThotLogger.error(
                    "Exception occured.",
                    trace=exception_error_and_trace(str(e), str(traceback.format_exc())),
                    context=call_context,
                )
            tkeir_doc["sentiment"] = {"sentences": sentiments, "doc": doc_sentiment}
            taskInfo = TaskInfo(task_name="sentiment", task_version=__version_sentiment__, task_date=__date_sentiment__)
            tkeir_doc = taskInfo.addInfo(tkeir_doc)
        return tkeir_doc

    def run(self, tkeir_doc, call_context=None):
        return self.sentimentAnalysisByTextBlocks(tkeir_doc, call_context=call_context)
