"""Summarizer
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

from transformers import pipeline
import traceback

from thot.core.Utils import ThotTokenizerToSpacy
from thot.core.ThotLogger import ThotLogger, LogUserContext
from thot.tasks.TaskInfo import TaskInfo
from thot.tasks.summarizer import __version_summarizer__, __date_summarizer__

from thot.tasks.summarizer.SummarizerConfiguration import SummarizerConfiguration


class Summarizer:
    def loadModelWithLanguage(self, call_context=None):

        if ("use-cuda" in self.config.configuration["settings"]) and self.config.configuration["settings"]["use-cuda"]:
            cuda_device = 0
            if "cuda-device" in self.config.configuration["settings"]:
                cuda_device = self.config.configuration["settings"]["cuda-device"]
            ThotLogger.info("Try to use cuda", context=call_context)
            try:
                self._summarizermodel = pipeline("summarization", device=cuda_device)
            except Exception as e:
                ThotLogger.warning("Use cuda failed, default load", context=call_context)
                self._summarizermodel = pipeline("summarization")
        else:
            self._summarizermodel = pipeline("summarization")

    def __init__(self, config: SummarizerConfiguration = None, call_context=None):

        if "settings" not in config.configuration:
            config.configuration["settings"] = {"min-percent": 10, "max-percent": 20}
        if ("min-percent" not in config.configuration["settings"]) or ("max-percent" not in config.configuration["settings"]):
            config.configuration["settings"].update({"min-percent": 10, "max-percent": 20})
        if "use-cuda" not in config.configuration["settings"]:
            config.configuration["settings"].update({"use-cuda": False})
        if "language" not in config.configuration["settings"]:
            config.configuration["settings"].update({"language": "en"})
        if config.configuration["settings"]["language"] not in ["en", "fr"]:
            ThotLogger.warning("Bad language, default set to en", context=call_context)
            config.configuration["settings"]["language"] = "en"
        self.config = config
        self.loadModelWithLanguage()

    def _getSentences(self, msTokens):
        sentences = []
        current_sentence = ""
        for tok in msTokens:
            if tok["is_sent_start"]:
                if current_sentence:
                    sentences.append(current_sentence)
                current_sentence = ""
            # if tok["pos"] != "PUNCT":
            current_sentence = current_sentence + " " + tok["text"]
        if current_sentence:
            sentences.append(current_sentence.strip())
        return sentences

    def _getSentenceBlock(self, texts):
        current_count_word = 0
        current_text = ""
        textblocks = []
        for text in texts:
            toks = text.split(" ")
            current_count_word = current_count_word + len(toks)
            if current_count_word > 400 and current_text:
                textblocks.append(current_text.strip())
                current_text = ""
                current_count_word = 0
            current_text = current_text + " " + text
        if current_text:
            textblocks.append(current_text.strip())
        return textblocks

    def summarizationByTextBlocks(self, stkeir_doc, call_context=None):
        tkeir_doc = stkeir_doc["doc"]
        min_length = 0
        max_length = 0
        min_percent = 0
        max_percent = 0

        if "min-length" in stkeir_doc:
            min_length = stkeir_doc["min-length"]
        if "max-length" in stkeir_doc:
            max_length = stkeir_doc["max-length"]
        if "min-percent" in stkeir_doc:
            min_percent = stkeir_doc["min-percent"]
        if "max-percent" in stkeir_doc:
            max_percent = stkeir_doc["max-percent"]

        summaries = []

        if ("title_morphosyntax" not in tkeir_doc) and ("content_morphosyntax" not in tkeir_doc):
            raise ValueError("title_morphosyntax and/or content_morphosyntax should be defined")
        if self._summarizermodel:
            texts = []
            texts = texts + self._getSentences(tkeir_doc["content_morphosyntax"])
            textblock = self._getSentenceBlock(texts)

            try:
                title_array = tkeir_doc["title_morphosyntax"]
                str_title = title_array
                if isinstance(title_array, list):
                    str_title = ""
                    for title_i in title_array:
                        str_title = str_title + " " + title_i["text"]

                textblock = [str_title] + textblock

                for text_i in range(len(textblock)):
                    text = textblock[text_i]
                    text_type = "content"
                    if text_i == 0:
                        text_type = "title"
                    text_min_length = 0
                    text_max_length = 0
                    text_len = len(text.split(" "))
                    if min_length:
                        text_min_length = min_length
                    # percent is prefered
                    if min_percent:
                        text_min_length = int(text_len * min_percent / 100)
                    if max_length:
                        text_max_length = max_length
                    # percent is prefered
                    if max_percent:
                        text_max_length = int(text_len * max_percent / 100)
                    if text_max_length <= text_min_length:
                        text_max_length = text_max_length + 10
                    ThotLogger.info(
                        "Summarize with length between ["
                        + str(text_min_length)
                        + ","
                        + str(text_max_length)
                        + "] for total length of ["
                        + str(text_len)
                        + "]",
                        context=call_context,
                    )
                    try:
                        summary_data = self._summarizermodel(
                            text, min_length=text_min_length, max_length=text_max_length, do_sample=False
                        )
                        summaries.append({"block": text, "type": text_type, "summary": summary_data[0]["summary_text"].strip()})
                    except Exception as es:
                        ThotLogger.error("Error:" + str(es) + " Trace:" + str(traceback.format_exc()), context=call_context)
                        summaries.append({"block": text, "type": text_type, "summary": text[0:256]})
            except Exception as e:
                ThotLogger.error("Error:" + str(e) + " Trace:" + str(traceback.format_exc()), context=call_context)
            tkeir_doc["summaries"] = summaries
            taskInfo = TaskInfo(task_name="summarizer", task_version=__version_summarizer__, task_date=__date_summarizer__)
            tkeir_doc = taskInfo.addInfo(tkeir_doc)
        return tkeir_doc

    def run(self, tkeir_doc, call_context=None):
        stkeir_doc = {
            "doc": tkeir_doc,
            "min-percent": self.config.configuration["settings"]["min-percent"],
            "max-percent": self.config.configuration["settings"]["max-percent"],
        }
        return self.summarizationByTextBlocks(stkeir_doc, call_context=call_context)
