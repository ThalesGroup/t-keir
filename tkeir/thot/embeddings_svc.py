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
from thot.tasks.embeddings import __version_embeddings__, __date_embeddings__
from thot.tasks.embeddings.EmbeddingsConfiguration import EmbeddingsConfiguration
from thot.tasks.embeddings.Embeddings import Embeddings


# Global variables
app = Sanic("embedding-extraction-service")
app.config["API_VERSION"] = __version_embeddings__
app.config["API_TITLE"] = "Sentence embeddings computaiton"
app.config[
    "API_DESCRIPTION"
] = "Extract embeddings from tokens a document in tkeir format (generally coming from tokenizer service)"
app.config["API_CONTACT_EMAIL"] = __email__

x_served_by = "tkeir/embeddings"


class EmbeddingsEngine:
    """Store embeddings as singleton
    Warning args should be set before calls
    """

    embeddings = None
    embeddings_configuration = None
    args = None

    @staticmethod
    def get_config():
        """create an return configuration as singleton

        Returns:
            EmbeddingsConfiguration: return the embedding extraction configuration load through args
        """
        if not EmbeddingsEngine.embeddings_configuration:
            EmbeddingsEngine.embeddings_configuration = EmbeddingsConfiguration()
            with open(EmbeddingsEngine.args.config) as fh:
                EmbeddingsEngine.embeddings_configuration.load(fh)
                fh.close()
        return EmbeddingsEngine.embeddings_configuration

    @staticmethod
    def get_embeddings():
        """create and return embeddings as singleton

        Returns:
            Tokenizer:  return the embeddings
        """
        if not EmbeddingsEngine.embeddings:
            EmbeddingsEngine.embeddings = Embeddings(config=EmbeddingsEngine.get_config())
        return EmbeddingsEngine.embeddings


embeddings_engine = None


def service_config():
    app.config.update(
        {
            "CONFIGURATION_FILE": EmbeddingsEngine.args.config,
        }
    )
    app.config["FALLBACK_ERROR_FORMAT"] = "json"


def service_not_loaded(call_context):
    call_context["status"] = 500
    ThotLogger.error("Service is not loaded", context=call_context)
    return sanic.response.json(
        {"error": Constants.SERVICE_NOT_LOADED, "version": __version_embeddings__, "date": __date_embeddings__},
        headers={"X-Served-By": x_served_by},
        status=500,
    )


@app.listener("before_server_start")
async def setup_config(app, loop):
    service_config()


@app.listener("after_server_start")
def init(sanic, loop):
    global embeddings_engine
    embeddings_engine = {
        "id": generate_id(prefix="embeddings"),
        "ppid": os.getppid(),
        "pid": os.getpid(),
        "run": EmbeddingsEngine.get_embeddings(),
    }
    ThotLogger.info(Constants.SERVICE_LOADED)


def sanic_bad_parameter_response(error_description):
    return sanic.response.json(
        {
            "error": error_description,
            "info": embeddings_engine["id"],
            "config": app.config["CONFIGURATION_FILE"],
            "version": __version_embeddings__,
            "date": __date_embeddings__,
        },
        headers={"X-Served-By": x_served_by},
        status=422,
    )


@app.route("/api/embeddings/run", methods=["POST", "OPTIONS"])
async def run_service(request):
    no_x_correlation = "autogenerated-" + str(uuid4())
    cid = request.headers.get("x-correlation-id") or no_x_correlation
    log_context = LogUserContext(cid)
    if not embeddings_engine:
        ThotMetrics.increment_counter(short_name="embeddings-run", path="/api/embeddings/run", method="post", status=500)
        ThotLogger.error("Embeding engine is empty.", context=log_context)
        return service_not_loaded(log_context)
    try:
        data = embeddings_engine["run"].compute(request.json, call_context=log_context)
        ThotMetrics.increment_counter(short_name="embeddings-run", path="/api/embeddings/run", method="post", status=200)
        return sanic.response.json(
            {
                "results": data,
                "info": embeddings_engine["id"],
                "config": app.config["CONFIGURATION_FILE"],
                "version": __version_embeddings__,
                "date": __date_embeddings__,
            },
            headers={"X-Served-By": x_served_by},
            status=200,
        )
    except Exception as e:
        ThotLogger.error(
            "Exception occured.",
            trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
            context=log_context,
        )
        ThotMetrics.increment_counter(short_name="embeddings-run", path="/api/embeddings/run", method="post", status=500)
        return sanic.response.json(
            {
                "error": Constants.SERVICE_INTERNAL_ERROR,
                "exception": str(e),
                "trace": str(traceback.format_exc()),
                "info": embeddings_engine["id"],
                "config": app.config["CONFIGURATION_FILE"],
                "version": __version_embeddings__,
                "date": __date_embeddings__,
            },
            headers={"X-Served-By": x_served_by},
            status=500,
        )


@app.route("/api/embeddings/run_from_table", methods=["POST", "OPTIONS"])
async def run_service_from_table(request):
    no_x_correlation = "autogenerated-" + str(uuid4())
    cid = request.headers.get("x-correlation-id") or no_x_correlation
    log_context = LogUserContext(cid)
    if not embeddings_engine:
        ThotMetrics.increment_counter(
            short_name="embeddings-run-from-table", path="/api/embeddings/run_from_table", method="post", status=500
        )
        return service_not_loaded(log_context)
    try:
        data = embeddings_engine["run"].computeFromTable(request.json["sentences"])
        ThotMetrics.increment_counter(
            short_name="embeddings-run-from-table", path="/api/embeddings/run_from_table", method="post", status=200
        )
        return sanic.response.json(
            {
                "results": data,
                "info": embeddings_engine["id"],
                "config": app.config["CONFIGURATION_FILE"],
                "version": __version_embeddings__,
                "date": __date_embeddings__,
            },
            headers={"X-Served-By": x_served_by},
            status=200,
        )
    except Exception as e:
        ThotMetrics.increment_counter(
            short_name="embeddings-run-from-table", path="/api/embeddings/run_from_table", method="post", status=500
        )
        ThotLogger.error(
            "Exception occured.",
            trace=Constants.exception_error_and_trace(str(e), str(traceback.format_exc())),
            context=log_context,
        )
        return sanic.response.json(
            {
                "error": Constants.SERVICE_INTERNAL_ERROR,
                "exception": str(e),
                "trace": str(traceback.format_exc()),
                "info": embeddings_engine["id"],
                "config": app.config["CONFIGURATION_FILE"],
                "version": __version_embeddings__,
                "date": __date_embeddings__,
            },
            headers={"X-Served-By": x_served_by},
            status=500,
        )


@app.route("/api/embeddings/health", methods=["GET", "POST", "OPTIONS"])
async def health(request):
    no_x_correlation = "autogenerated-" + str(uuid4())
    cid = request.headers.get("x-correlation-id") or no_x_correlation
    log_context = LogUserContext(cid)
    if not embeddings_engine:
        ThotMetrics.increment_counter(short_name="embeddings-health", path="/api/embeddings/health", method="get", status=500)
        return service_not_loaded(log_context)
    ThotMetrics.increment_counter(short_name="embeddings-health", path="/api/embeddings/health", method="get", status=200)
    return sanic.response.json(
        {
            "health": Constants.SERVICE_HEALTH_OK,
            "info": embeddings_engine["id"],
            "config": app.config["CONFIGURATION_FILE"],
            "version": __version_embeddings__,
            "date": __date_embeddings__,
        },
        headers={"X-Served-By": x_served_by},
        status=200,
    )


@app.route("/metrics", methods=["GET", "POST", "OPTIONS"])
async def metrics(request):
    output = ThotMetrics.generateMetricsResponse().decode("utf-8")
    content_type = ThotMetrics.METRIC_MIME_TYPE
    return sanic.response.text(body=output, content_type=content_type)


@app.exception(NotFound)
async def function_not_found(request, exception):
    no_x_correlation = "autogenerated-" + str(uuid4())
    cid = request.headers.get("x-correlation-id") or no_x_correlation
    log_context = LogUserContext(cid)
    if not embeddings_engine:
        return service_not_loaded(log_context)
    return sanic.response.json(
        {
            "error": Constants.SERVICE_PAGE_NOT_FOUND,
            "info": embeddings_engine["id"],
            "config": app.config["CONFIGURATION_FILE"],
            "version": __version_embeddings__,
            "date": __date_embeddings__,
        },
        headers={"X-Served-By": x_served_by},
        status=400,
    )


def main(args):
    EmbeddingsEngine.args = args
    if not EmbeddingsEngine.args.config:
        ThotLogger.loads()
        ThotLogger.error("Configuration file is mandatory")
        sys.exit(-1)

    try:
        # initialize logger
        ThotLogger.loads(EmbeddingsEngine.get_config().logger_config.configuration, logger_name="Embeddings")
        ThotMetrics.APP_NAME = "T-KEIR : embbedings"
        ThotMetrics.create_counter(
            short_name="embeddings-health", function_name="health", counter_description="health function count"
        )
        ThotMetrics.create_counter(
            short_name="embeddings-run-from-table",
            function_name="run_from_table",
            counter_description="run_from_table function count",
        )
        ThotMetrics.create_counter(
            short_name="embeddings-run", function_name="run", counter_description="run_service function count"
        )
        host = EmbeddingsEngine.get_config().net_config.configuration["network"]["host"]
        port = int(EmbeddingsEngine.get_config().net_config.configuration["network"]["port"])
        workers = EmbeddingsEngine.get_config().runtime_config.configuration["runtime"]["workers"]
        EmbeddingsEngine.get_embeddings()
        if not args.init:
            use_ssl = os.getenv("TKEIR_USE_SSL", "True")
            if ("ssl" in EmbeddingsEngine.get_config().net_config.configuration["network"]) and type_to_bool(use_ssl):
                ThotLogger.info("Run service with SSL")
                app.run(
                    host=host,
                    port=port,
                    workers=workers,
                    ssl=EmbeddingsEngine.get_config().net_config.configuration["network"]["ssl"],
                )
            else:
                app.run(host=host, port=port, workers=workers)
    except Exception as e:
        ThotLogger.error("An error occured." + Constants.exception_error_and_trace(str(e), str(traceback.format_exc())))
        sys.exit(-1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default=None, type=str, help="configuration file")
    parser.add_argument("-i", "--init", default=False, action="store_true")
    main(parser.parse_args())
