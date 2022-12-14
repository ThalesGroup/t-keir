# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
from sanic import Sanic
from sanic.exceptions import ServerError
import sanic.response
from sanic.exceptions import NotFound

import os
import sys
import argparse
import traceback
from uuid import uuid4


dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))

from thot import __author__, __copyright__, __credits__, __maintainer__, __email__, __status__
import thot.core.Constants as Constants
from thot.core.ThotLogger import ThotLogger, LogUserContext
from thot.core.ThotMetrics import ThotMetrics
from thot.core.Utils import generate_id, type_to_bool
from thot.tasks.document_classification import __version_document_classification__, __date_document_classification__
from thot.tasks.document_classification.ZeroShotClassificationConfiguration import ZeroShotClassificationConfiguration
from thot.tasks.document_classification.ZeroShotClassification import ZeroShotClassification


# Global variables
app = Sanic("zeroshotclassifier-service")
app.config["API_VERSION"] = __version_document_classification__
app.config["API_TITLE"] = "ZeroShot Document classifier Service"
app.config["API_DESCRIPTION"] = "Unsupervised document classification"
app.config["API_CONTACT_EMAIL"] = __email__


class ZeroshotclassifierEngine:
    """Store classifier as singleton
    Warning args should be set before calls
    """

    classifier = None
    classifierConfiguration = None
    args = None

    @staticmethod
    def get_config():
        """create an return configuration as singleton

        Returns:
            ZeroShotClassificationConfiguration: return the document classifier configuration load through args
        """
        if not ZeroshotclassifierEngine.classifierConfiguration:
            ZeroshotclassifierEngine.classifierConfiguration = ZeroShotClassificationConfiguration()
            with open(ZeroshotclassifierEngine.args.config) as fh:
                ZeroshotclassifierEngine.classifierConfiguration.load(fh)
                fh.close()
        return ZeroshotclassifierEngine.classifierConfiguration

    @staticmethod
    def getzeroshotclassifier():
        """create and return zeroshotclassifier as singleton

        Returns:
            Tokenizer:  return the zeroshotclassifier
        """
        if not ZeroshotclassifierEngine.classifier:
            ZeroshotclassifierEngine.classifier = ZeroShotClassification(config=ZeroshotclassifierEngine.get_config())
        return ZeroshotclassifierEngine.classifier


zeroshotclassifier_engine = None


def service_config():
    app.config.update(
        {
            "CONFIGURATION_FILE": ZeroshotclassifierEngine.args.config,
        }
    )
    app.config["FALLBACK_ERROR_FORMAT"] = "json"


def service_not_loaded(call_context):
    call_context["status"] = 500
    ThotLogger.error("Service is not loaded", context=call_context)
    return sanic.response.json(
        {
            "error": "service does not loaded",
            "version": __version_document_classification__,
            "date": __date_document_classification__,
        },
        headers={"X-Served-By": "tkeir/zeroshotclassifier"},
        status=500,
    )


@app.listener("before_server_start")
async def setup_config(app, loop):
    service_config()


@app.listener("after_server_start")
def init(sanic, loop):
    global zeroshotclassifier_engine
    zeroshotclassifier_engine = {
        "id": generate_id(prefix="zeroshotclassifier"),
        "ppid": os.getppid(),
        "pid": os.getpid(),
        "run": ZeroshotclassifierEngine.getzeroshotclassifier(),
    }
    ThotLogger.info("Service loaded")


def sanic_bad_parameter_response(error_description):
    return sanic.response.json(
        {
            "error": error_description,
            "info": zeroshotclassifier_engine["id"],
            "config": app.config["CONFIGURATION_FILE"],
            "version": __version_document_classification__,
            "date": __date_document_classification__,
        },
        headers={"X-Served-By": "tkeir/zeroshotclassifier"},
        status=422,
    )


@app.route("/api/zeroshotclassifier/run", methods=["POST", "OPTIONS"])
async def run_service(request):
    no_x_correlation = "autogenerated-" + str(uuid4())
    cid = request.headers.get("x-correlation-id") or no_x_correlation
    log_context = LogUserContext(cid)
    if not zeroshotclassifier_engine:
        ThotMetrics.increment_counter(
            short_name="zeroshotclassifier-run", path="/api/zeroshotclassifier/run", method="post", status=500
        )
        return service_not_loaded(log_context)
    try:
        data = zeroshotclassifier_engine["run"].classify(request.json, call_context=log_context)
        ThotMetrics.increment_counter(
            short_name="zeroshotclassifier-run", path="/api/zeroshotclassifier/run", method="post", status=200
        )
        return sanic.response.json(
            {
                "results": data,
                "info": zeroshotclassifier_engine["id"],
                "config": app.config["CONFIGURATION_FILE"],
                "version": __version_document_classification__,
                "date": __date_document_classification__,
            },
            headers={"X-Served-By": "tkeir/zeroshotclassifier"},
            status=200,
        )
    except Exception as e:
        ThotLogger.error(
            "Exception occured.",
            trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
            context=log_context,
        )
        ThotMetrics.increment_counter(
            short_name="zeroshotclassifier-run", path="/api/zeroshotclassifier/run", method="post", status=500
        )
        return sanic.response.json(
            {
                "error": Constants.SERVICE_INTERNAL_ERROR,
                "exception": str(e),
                "trace": str(traceback.format_exc()),
                "info": zeroshotclassifier_engine["id"],
                "config": app.config["CONFIGURATION_FILE"],
                "version": __version_document_classification__,
                "date": __date_document_classification__,
            },
            headers={"X-Served-By": "tkeir/zeroshotclassifier"},
            status=500,
        )


@app.route("/api/zeroshotclassifier/run_with_classes", methods=["POST", "OPTIONS"])
async def run_service(request):
    no_x_correlation = "autogenerated-" + str(uuid4())
    cid = request.headers.get("x-correlation-id") or no_x_correlation
    log_context = LogUserContext(cid)
    if not zeroshotclassifier_engine:
        ThotMetrics.increment_counter(
            short_name="zeroshotclassifier-run-with-classes",
            path="/api/zeroshotclassifier/run_with_classes",
            method="post",
            status=500,
        )
        return service_not_loaded(log_context)
    try:
        data = zeroshotclassifier_engine["run"].classify(
            request.json["doc"], request.json["classes"], request.json["map-classes"], log_context=call_context
        )
        ThotMetrics.increment_counter(
            short_name="zeroshotclassifier-run-with-classes",
            path="/api/zeroshotclassifier/run_with_classes",
            method="post",
            status=200,
        )
        return sanic.response.json(
            {
                "results": data,
                "info": zeroshotclassifier_engine["id"],
                "config": app.config["CONFIGURATION_FILE"],
                "version": __version_document_classification__,
                "date": __date_document_classification__,
            },
            headers={"X-Served-By": "tkeir/zeroshotclassifier"},
            status=200,
        )
    except Exception as e:
        ThotLogger.error(
            "Exception occured.",
            trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
            context=log_context,
        )
        ThotMetrics.increment_counter(
            short_name="zeroshotclassifier-run-with-classes",
            path="/api/zeroshotclassifier/run_with_classes",
            method="post",
            status=500,
        )
        return sanic.response.json(
            {
                "error": Constants.SERVICE_INTERNAL_ERROR,
                "exception": str(e),
                "trace": str(traceback.format_exc()),
                "info": zeroshotclassifier_engine["id"],
                "config": app.config["CONFIGURATION_FILE"],
                "version": __version_document_classification__,
                "date": __date_document_classification__,
            },
            headers={"X-Served-By": "tkeir/zeroshotclassifier"},
            status=500,
        )


@app.route("/api/zeroshotclassifier/health", methods=["GET", "POST", "OPTIONS"])
async def health(request):
    no_x_correlation = "autogenerated-" + str(uuid4())
    cid = request.headers.get("x-correlation-id") or no_x_correlation
    log_context = LogUserContext(cid)
    if not zeroshotclassifier_engine:
        ThotMetrics.increment_counter(
            short_name="zeroshotclassifier-health", path="/api/zeroshotclassifier/health", method="get", status=500
        )
        return service_not_loaded(log_context)
    ThotMetrics.increment_counter(
        short_name="zeroshotclassifier-health", path="/api/zeroshotclassifier/health", method="get", status=200
    )
    return sanic.response.json(
        {
            "health": Constants.SERVICE_HEALTH_OK,
            "info": zeroshotclassifier_engine["id"],
            "config": app.config["CONFIGURATION_FILE"],
            "version": __version_document_classification__,
            "date": __date_document_classification__,
        },
        headers={"X-Served-By": "tkeir/zeroshotclassifier"},
        status=200,
    )


@app.exception(NotFound)
async def function_not_found(request, exception):
    no_x_correlation = "autogenerated-" + str(uuid4())
    cid = request.headers.get("x-correlation-id") or no_x_correlation
    log_context = LogUserContext(cid)
    if not zeroshotclassifier_engine:
        return service_not_loaded(log_context)
    return sanic.response.json(
        {
            "error": Constants.SERVICE_PAGE_NOT_FOUND,
            "info": zeroshotclassifier_engine["id"],
            "config": app.config["CONFIGURATION_FILE"],
            "version": __version_document_classification__,
            "date": __date_document_classification__,
        },
        headers={"X-Served-By": "tkeir/zeroshotclassifier"},
        status=400,
    )


@app.route("/metrics", methods=["GET", "POST", "OPTIONS"])
async def metrics(request):
    output = ThotMetrics.generateMetricsResponse().decode("utf-8")
    content_type = ThotMetrics.METRIC_MIME_TYPE
    return sanic.response.text(body=output, content_type=content_type)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default=None, type=str, help="configuration file")
    parser.add_argument("-i", "--init", default=False, action="store_true")
    args=parser.parse_args()
    ZeroshotclassifierEngine.args = args
    if not ZeroshotclassifierEngine.args.config:
        ThotLogger.loads()
        ThotLogger.error("Configuration file is mandatory")
        sys.exit(-1)

    try:
        ThotLogger.loads(ZeroshotclassifierEngine.get_config().logger_config.configuration, logger_name="ZSC")
        ThotMetrics.APP_NAME = "T-KEIR : zeroshotclassifier"
        ThotMetrics.create_counter(
            short_name="zeroshotclassifier-health", function_name="health", counter_description="Health function count"
        )
        ThotMetrics.create_counter(
            short_name="zeroshotclassifier-run", function_name="run", counter_description="run_service function count"
        )
        ThotMetrics.create_counter(
            short_name="zeroshotclassifier-run-with-classes",
            function_name="run_with_classes",
            counter_description="run_service with classes function count",
        )
        host = ZeroshotclassifierEngine.get_config().net_config.configuration["network"]["host"]
        port = int(ZeroshotclassifierEngine.get_config().net_config.configuration["network"]["port"])
        workers = ZeroshotclassifierEngine.get_config().runtime_config.configuration["runtime"]["workers"]
        ZeroshotclassifierEngine.getzeroshotclassifier()
        if not args.init:
            use_ssl = os.getenv("TKEIR_USE_SSL", "True")
            if ("ssl" in ZeroshotclassifierEngine.get_config().net_config.configuration["network"]) and type_to_bool(use_ssl):
                ThotLogger.info("Run service with SSL")
                app.run(
                    host=host,
                    port=port,
                    workers=workers,
                    ssl=ZeroshotclassifierEngine.get_config().net_config.configuration["network"]["ssl"],
                )
            else:
                app.run(host=host, port=port, workers=workers)
    except Exception as e:
        ThotLogger.error("An error occured." + Constants.exception_error_and_trace(str(e), str(traceback.format_exc())))
        sys.exit(-1)


if __name__ == "__main__":
    main()
