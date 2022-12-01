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
from thot.core.ThotLogger import ThotLogger
from thot.core.ThotMetrics import ThotMetrics
from thot.core.Utils import generate_id, type_to_bool
from thot.tasks.sentiment import __version_sentiment__, __date_sentiment__
from thot.tasks.sentiment.SentimentAnalysisConfiguration import SentimentAnalysisConfiguration
from thot.tasks.sentiment.SentimentAnalysis import SentimentAnalysis

# Global variables
app = Sanic("sentimentclassifier-service")
app.config["API_VERSION"] = __version_sentiment__
app.config["API_TITLE"] = "Sentiment classifier Service"
app.config["API_DESCRIPTION"] = "Sentiment classification"
app.config["API_CONTACT_EMAIL"] = __email__


class SentimentAnalysisEngine:
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
            SentimentAnalysisConfiguration: return the document classifier configuration load through args
        """
        if not SentimentAnalysisEngine.classifierConfiguration:
            SentimentAnalysisEngine.classifierConfiguration = SentimentAnalysisConfiguration()
            with open(SentimentAnalysisEngine.args.config) as fh:
                SentimentAnalysisEngine.classifierConfiguration.load(fh)
                fh.close()
        return SentimentAnalysisEngine.classifierConfiguration

    @staticmethod
    def getsentimentclassifier():
        """create and return sentimentclassifier as singleton

        Returns:
            Sentiment:  return the sentimentclassifier
        """
        if not SentimentAnalysisEngine.classifier:
            SentimentAnalysisEngine.classifier = SentimentAnalysis(config=SentimentAnalysisEngine.get_config())
        return SentimentAnalysisEngine.classifier


sentimentclassifier_engine = None


def service_config():
    app.config.update(
        {
            "CONFIGURATION_FILE": SentimentAnalysisEngine.args.config,
        }
    )
    app.config["FALLBACK_ERROR_FORMAT"] = "json"


def service_not_loaded():
    return sanic.response.json(
        {"error": Constants.SERVICE_NOT_LOADED, "version": __version_sentiment__, "date": __date_sentiment__},
        headers={"X-Served-By": "tkeir/sentimentclassifier"},
        status=500,
    )


@app.listener("before_server_start")
async def setup_config(app, loop):
    service_config()


@app.listener("after_server_start")
def init(sanic, loop):
    global sentimentclassifier_engine
    sentimentclassifier_engine = {
        "id": generate_id(prefix="sentimentclassifier"),
        "ppid": os.getppid(),
        "pid": os.getpid(),
        "run": SentimentAnalysisEngine.getsentimentclassifier(),
    }
    ThotLogger.info(Constants.SERVICE_LOADED)


def sanic_bad_parameter_response(error_description):
    return sanic.response.json(
        {
            "error": error_description,
            "info": sentimentclassifier_engine["id"],
            "config": app.config["CONFIGURATION_FILE"],
            "version": __version_sentiment__,
            "date": __date_sentiment__,
        },
        headers={"X-Served-By": "tkeir/sentimentclassifier"},
        status=422,
    )


@app.route("/api/sentimentclassifier/run", methods=["POST", "OPTIONS"])
async def run_service(request):
    if not sentimentclassifier_engine:
        return service_not_loaded()
    try:
        data = sentimentclassifier_engine["run"].sentimentAnalysisByTextBlocks(request.json)
        return sanic.response.json(
            {
                "results": data,
                "info": sentimentclassifier_engine["id"],
                "config": app.config["CONFIGURATION_FILE"],
                "version": __version_sentiment__,
                "date": __date_sentiment__,
            },
            headers={"X-Served-By": "tkeir/sentimentclassifier"},
            status=200,
        )
    except Exception as e:
        ThotLogger.error(Constants.exception_error_and_trace(str(e), str(traceback.format_exc())))
        return sanic.response.json(
            {
                "error": Constants.SERVICE_INTERNAL_ERROR,
                "exception": str(e),
                "trace": str(traceback.format_exc()),
                "info": sentimentclassifier_engine["id"],
                "config": app.config["CONFIGURATION_FILE"],
                "version": __version_sentiment__,
                "date": __date_sentiment__,
            },
            headers={"X-Served-By": "tkeir/sentimentclassifier"},
            status=500,
        )


@app.route("/api/sentimentclassifier/health", methods=["GET", "POST", "OPTIONS"])
async def health(request):
    if not sentimentclassifier_engine:
        return service_not_loaded()
    return sanic.response.json(
        {
            "health": Constants.SERVICE_HEALTH_OK,
            "info": sentimentclassifier_engine["id"],
            "config": app.config["CONFIGURATION_FILE"],
            "version": __version_sentiment__,
            "date": __date_sentiment__,
        },
        headers={"X-Served-By": "tkeir/sentimentclassifier"},
        status=200,
    )


@app.route("/metrics", methods=["GET", "POST", "OPTIONS"])
async def metrics(request):
    output = ThotMetrics.generateMetricsResponse().decode("utf-8")
    content_type = ThotMetrics.METRIC_MIME_TYPE
    return sanic.response.text(body=output, content_type=content_type)


@app.exception(NotFound)
async def function_not_found(request, exception):
    if not sentimentclassifier_engine:
        return service_not_loaded()
    return sanic.response.json(
        {
            "error": "page not found",
            "info": sentimentclassifier_engine["id"],
            "config": app.config["CONFIGURATION_FILE"],
            "version": __version_sentiment__,
            "date": __date_sentiment__,
        },
        headers={"X-Served-By": "tkeir/sentimentclassifier"},
        status=400,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default=None, type=str, help="configuration file")
    parser.add_argument("-i", "--init", default=False, action="store_true")
    args = parser.parse_args()
    SentimentAnalysisEngine.args = args
    if not SentimentAnalysisEngine.args.config:
        ThotLogger.loads()
        ThotLogger.error("Configuration file is mandatory")
        sys.exit(-1)

    try:
        # initialize logger
        ThotLogger.loads(SentimentAnalysisEngine.get_config().logger_config.configuration, logger_name="Sentiment")
        host = SentimentAnalysisEngine.get_config().net_config.configuration["network"]["host"]
        port = int(SentimentAnalysisEngine.get_config().net_config.configuration["network"]["port"])
        workers = SentimentAnalysisEngine.get_config().runtime_config.configuration["runtime"]["workers"]
        SentimentAnalysisEngine.getsentimentclassifier()
        if not args.init:
            use_ssl = os.getenv("TKEIR_USE_SSL", "True")
            if ("ssl" in SentimentAnalysisEngine.get_config().net_config.configuration["network"]) and type_to_bool(use_ssl):
                ThotLogger.info("Run service with SSL")
                app.run(
                    host=host,
                    port=port,
                    workers=workers,
                    ssl=SentimentAnalysisEngine.get_config().net_config.configuration["network"]["ssl"],
                )
            else:
                app.run(host=host, port=port, workers=workers)
    except Exception as e:
        ThotLogger.error(
            "An error occured.Exception:" + Constants.exception_error_and_trace(str(e), str(traceback.format_exc()))
        )
        sys.exit(-1)


if __name__ == "__main__":
    main()
