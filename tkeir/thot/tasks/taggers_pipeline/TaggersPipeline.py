# -*- coding: utf-8 -*-
"""Tagger pipeline
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
import hashlib
import json
import os
from subprocess import call
from joblib import Parallel, delayed
import queue
import time
import traceback
from nltk.util import transitive_closure
import requests
from sanic.response import file
from filelock import FileLock
from thot.core.Utils import check_pid
from joblib import Parallel, delayed

from thot.core.ThotLogger import ThotLogger
from thot.core.Utils import timelimit
import thot.core.Constants as Constants
from thot.tasks.converters.ConverterConfiguration import ConverterConfiguration
from thot.tasks.converters.Converter import Converter
from thot.tasks.tokenizer.TokenizerConfiguration import TokenizerConfiguration
from thot.tasks.tokenizer.Tokenizer import Tokenizer
from thot.tasks.morphosyntax.MorphoSyntacticTaggerConfiguration import MorphoSyntacticTaggerConfiguration
from thot.tasks.morphosyntax.MorphoSyntacticTagger import MorphoSyntacticTagger
from thot.tasks.ner.NERTaggerConfiguration import NERTaggerConfiguration
from thot.tasks.ner.NERTagger import NERTagger
from thot.tasks.syntax.SyntacticTaggerConfiguration import SyntacticTaggerConfiguration
from thot.tasks.syntax.SyntacticTagger import SyntacticTagger
from thot.tasks.keywords.KeywordsConfiguration import KeywordsConfiguration
from thot.tasks.keywords.KeywordsExtractor import KeywordsExtractor
from thot.tasks.relations.RelationClusterizerConfiguration import RelationClusterizerConfiguration
from thot.tasks.relations.ClusterInference import ClusteringInference
from thot.tasks.document_classification.ZeroShotClassificationConfiguration import ZeroShotClassificationConfiguration
from thot.tasks.document_classification.ZeroShotClassification import ZeroShotClassification
from thot.tasks.sentiment.SentimentAnalysisConfiguration import SentimentAnalysisConfiguration
from thot.tasks.sentiment.SentimentAnalysis import SentimentAnalysis
from thot.tasks.summarizer.SummarizerConfiguration import SummarizerConfiguration
from thot.tasks.summarizer.Summarizer import Summarizer
from thot.tasks.indexing.IndexingConfiguration import IndexingConfiguration
from thot.tasks.indexing.Indexing import Indexing
from thot.tasks.indexing.IndicesManager import IndicesManager
from thot.tasks.taggers_pipeline.TaggersPipelineConfiguration import TaggersPipelineConfiguration

ssl_verify = False


def process_file(task, svcConfig, settingsConfig, files, call_context):
    if len(files) == 0:
        return "nok"
    if task["task"] == "index":
        try:
            IndicesManager.createIndices(config=svcConfig.configuration)
        except Exception as e:
            tracebck = traceback.format_exc()
            ThotLogger.error(
                "Exception:" + str(e) + " | trace:",
                trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
                context=call_context,
            )

    os.environ["TOKENIZERS_PARALLELISM"] = "true"
    if task["task"] == "clusterinfer":
        serviceInstance = TaggersPipeline.task_auto_model[task["task"]]["service"](svcConfig, embeddings_server=False)
    else:
        serviceInstance = TaggersPipeline.task_auto_model[task["task"]]["service"](svcConfig)
    for filename in files:
        status_file = filename.replace(".json", ".status.json")
        ThotLogger.info("Analyze:" + status_file, context=call_context)
        with open(status_file) as status_f:
            status_loaded = True
            try:
                status = json.load(status_f)
                status_f.close()
            except Exception as json_e:
                status_loaded = False
                ThotLogger.error(
                    "Load file '" + status_file + "' failed",
                    trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
                    context=call_context,
                )
            if (
                status_loaded
                and (status["task"] == task["previous-task"])
                and (status["status"] == "finished")
                and (not status["error"])
            ):
                ThotLogger.info("Status [" + status_file + "] process for task '" + task["task"] + "'", context=call_context)
                status["task"] = task["task"]
                status["error"] = False
                status["status"] = "started"
                status["date"] = time.time()
                with open(status_file, "w", encoding="utf-8") as json_f:
                    json.dump(status, json_f, ensure_ascii=False)
                    json_f.close()
                with open(filename, encoding="utf-8") as json_f:
                    file_loaded = True
                    error_str = ""
                    try:
                        json_request = json.load(json_f)
                    except Exception as e:
                        ThotLogger.error(
                            "Cannot load " + filename,
                            trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
                            context=call_context,
                        )
                        file_loaded = False
                        error_str = filename + ":" + str(e)
                    json_f.close()
                    result = None

                    try:
                        if file_loaded:
                            if settingsConfig["max-time-per-task"] > 0:
                                result = timelimit(settingsConfig["max-time-per-task"], serviceInstance.run, (json_request,))
                            else:
                                result = serviceInstance.run(json_request)
                    except Exception as e:
                        ThotLogger.error(
                            "Error occured on task:" + task["task"],
                            trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
                            context=call_context,
                        )
                        error_str = str(e)
                    if result:
                        with open(filename, "w", encoding="utf-8") as output_f:
                            json.dump(result, output_f, indent=2, ensure_ascii=False)
                            output_f.close()
                        if task["save-output"]:
                            bname = os.path.join(task["output-dir"], os.path.basename(filename))
                            ThotLogger.info("Save:" + bname, context=call_context)
                            with open(bname, "w", encoding="utf-8") as output_f:
                                json.dump(result, output_f, indent=2, ensure_ascii=False)
                                output_f.close()
                    else:
                        status["error"] = True
                        status["error-string"] = error_str
                    if "is-last-task" in task:
                        status["is-last-task"] = True
                    status["status"] = "finished"
                    status["date"] = time.time()
                    with FileLock(status_file + ".lock"):
                        with open(status_file, "w", encoding="utf-8") as json_f:
                            json.dump(status, json_f, ensure_ascii=False)
                            json_f.close()
    return "ok"


class TaggersPipeline:
    map_tasks_service_name = {
        "converter": "converter",
        "tokenizer": "tokenizer",
        "morphosyntax": "mstagger",
        "ner": "nertagger",
        "syntax": "syntactictagger",
        "keywords": "keywordsextractor",
        "clusterinfer": "clusterinfer",
        "zeroshotclassifier": "zeroshotclassifier",
        "summarizer": "summarizer",
        "sentiment": "sentimentclassifier",
        "index": "indexing",
    }
    task_auto_model = {
        "converter": {"svcConfig": ConverterConfiguration, "service": Converter},
        "tokenizer": {"svcConfig": TokenizerConfiguration, "service": Tokenizer},
        "morphosyntax": {"svcConfig": MorphoSyntacticTaggerConfiguration, "service": MorphoSyntacticTagger},
        "ner": {"svcConfig": NERTaggerConfiguration, "service": NERTagger},
        "syntax": {"svcConfig": SyntacticTaggerConfiguration, "service": SyntacticTagger},
        "keywords": {"svcConfig": KeywordsConfiguration, "service": KeywordsExtractor},
        "clusterinfer": {"svcConfig": RelationClusterizerConfiguration, "service": ClusteringInference},
        "zeroshotclassifier": {"svcConfig": ZeroShotClassificationConfiguration, "service": ZeroShotClassification},
        "sentiment": {"svcConfig": SentimentAnalysisConfiguration, "service": SentimentAnalysis},
        "summarizer": {"svcConfig": SummarizerConfiguration, "service": Summarizer},
        "index": {"svcConfig": IndexingConfiguration, "service": Indexing},
    }

    def _load_config(self, task):
        if task["task"] == "converter":
            self.input_directory = task["input-dir"]
        if "previous-task" not in task:
            ThotLogger.error("Previous task of'" + task["task"] + "' should be set.")
            raise ValueError("Previous task not define")
        svcConfig = TaggersPipeline.task_auto_model[task["task"]]["svcConfig"]()
        if svcConfig:
            with open(os.path.join(task["resources-base-path"], task["configuration"])) as fh:
                svcConfig.load(fh)
                fh.close()
        return svcConfig

    def serialized_run(self, call_context=None):
        settingsConfig = self.config.configuration["settings"]
        for task in self.config.configuration["tasks"]:
            svcConfig = self._load_config(task)
            files = [
                os.path.join(task["input-dir"], filename)
                for filename in os.listdir(task["input-dir"])
                if filename.endswith(".status.json")
            ]
            workers = svcConfig.runtime_config.configuration["runtime"]["workers"]
            fileTables = [[]] * workers
            offset = 0
            for file in files:
                with FileLock(file + ".lock"):
                    with open(file, encoding="utf-8") as status_f:
                        status_loaded = True
                        try:
                            status = json.load(status_f)
                        except Exception as e:
                            ThotLogger.error(
                                "Cannot load '" + file + "' from serialized_run",
                                trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
                                context=call_context,
                            )
                            status_loaded = False
                        status_f.close()
                        if (
                            status_loaded
                            and (not status["error"])
                            and (status["task"] == task["previous-task"])
                            and (status["status"] == "finished")
                        ):
                            fileTables[offset].append(file.replace(".status.json", ".json"))
                            offset = offset + 1
                            if offset == workers:
                                offset = 0
            if len(fileTables):
                processed_list = Parallel(n_jobs=workers)(
                    delayed(process_file)(task, svcConfig, settingsConfig, i, call_context) for i in fileTables
                )
        return processed_list

    def __init__(self, config: TaggersPipelineConfiguration = None):
        self.stopPipeline = False
        self.uploadStarted = False
        if config is None:
            raise ValueError("Configuration should be given.")
        self.config = config
        self.config.configuration["tasks"][-1]["is-last-task"] = True
        self.serialized_run()

    def start_upload(self):
        self.uploadStarted = True

    def finish_upload(self):
        self.uploadStarted = False

    def upload(self, data_type: str = "raw", data: str = None, source: str = "empty", call_context=None):
        if not self.uploadStarted:
            return None
        m = hashlib.md5()
        m.update(data.encode())
        hash_id = m.hexdigest()
        pfile = os.path.join(self.input_directory, hash_id + ".json")
        if not os.path.isfile(pfile):
            ThotLogger.info("Upload '" + source + "' with hash '" + hash_id + ",", context=call_context)
            status_file = pfile.replace(".json", ".status.json")
            with FileLock(status_file + ".lock"):
                with open(pfile, "w", encoding="utf-8") as json_f:
                    json.dump({"data": data, "datatype": data_type, "source": source}, json_f, ensure_ascii=False)
                    json_f.close()
                with open(status_file, "w", encoding="utf-8") as json_f:
                    json.dump(
                        {"task": "input", "status": "finished", "error": False, "date": time.time()}, json_f, ensure_ascii=False
                    )
                    json_f.close()
        return hash_id

    def stop(self):
        self.stopPipeline = True

    def status(self, tokenid=None, call_context=None):
        if not tokenid:
            raise ValueError("Tokenid should be set")
        filename = os.path.join(self.input_directory, tokenid + ".status.json")
        json_data = {"error": True}
        if os.path.isfile(filename):
            with open(filename, encoding="utf-8") as json_f:
                status_loaded = True
                error_str = "unk"
                try:
                    json_data = json.load(json_f)
                except Exception as e:
                    ThotLogger.error(
                        "Cannot get status error:",
                        trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
                        context=call_context,
                    )
                    status_loaded = False
                    error_str = str(e)
                json_f.close()
            if not status_loaded:
                json_data["status"] = error_str
        else:
            json_data["status"] = "file not found"
        return json_data

    def get(self, tokenid=None, call_context=None):
        data = None
        if not tokenid:
            raise ValueError("Tokenid should be set")
        filename = os.path.join(self.input_directory, tokenid + ".status.json")
        if os.path.isfile(filename):
            try:
                with open(filename, encoding="utf-8") as json_f:
                    status_loaded = True
                    try:
                        json_data = json.load(json_f)
                    except Exception as e:
                        status_loaded = False
                    json_f.close()
                    if status_loaded and ("is-last-task" in json_data) and (json_data["status"] == "finished"):
                        doc_filename = filename.replace(".status.json", ".json")
                        with open(doc_filename, encoding="utf-8") as tkeir_doc_f:
                            data = json.load(tkeir_doc_f)
                            tkeir_doc_f.close()
                            if "clean-input-folder-after-analysis" in json_data:
                                try:
                                    os.remove(doc_filename)
                                except:
                                    ThotLogger.warning("[get] Cannot remove:" + doc_filename, context=call_context)
                                try:
                                    os.remove(filename)
                                except:
                                    ThotLogger.warning("[get] Cannot remove:" + filename, context=call_context)
            except Exception as open_e:
                ThotLogger.warning(
                    "File " + filename + " does not exist.",
                    trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
                    context=call_context,
                )
        return data


def pipelineLoop(taggerPipeline: TaggersPipeline, call_context):
    ThotLogger.info("Start Pipeline Loop.", context=call_context)
    max_time_loop = taggerPipeline.config.configuration["settings"]["max-time-loop"]
    start_time = time.time()
    et_time = time.time() - start_time
    while ((max_time_loop == -1) or (max_time_loop > et_time)) and (not taggerPipeline.stopPipeline):
        time.sleep(5)
        et_time = time.time() - start_time
        ThotLogger.info("Active waiting for new task", context=call_context)
        if not taggerPipeline.uploadStarted:
            ThotLogger.info("Start new serialize run", context=call_context)
            taggerPipeline.serialized_run(call_context=call_context)
