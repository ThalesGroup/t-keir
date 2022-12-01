# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
import os
import sys
import argparse
import requests
import traceback
import json


dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))

import thot.core.Constants as Constants
from thot import __author__, __copyright__, __credits__, __maintainer__, __email__, __status__
from thot.core.ThotLogger import ThotLogger
from thot.tasks.embeddings import __version_embeddings__, __date_embeddings__
from thot.tasks.embeddings.EmbeddingsConfiguration import EmbeddingsConfiguration


def main(args):
    if not args.config:
        ThotLogger.loads()
        ThotLogger.error("Configuration file is mandatory")
        sys.exit(-1)
    try:
        # initialize logger
        embeddingsConfiguration = EmbeddingsConfiguration()
        with open(args.config) as fh:
            embeddingsConfiguration.load(fh)
            fh.close()
        ThotLogger.loads(embeddingsConfiguration.logger_config.configuration)
        host = embeddingsConfiguration.net_config.configuration["network"]["host"]
        port = embeddingsConfiguration.net_config.configuration["network"]["port"]
        ThotLogger.info("Embbed:" + args.input)
        for (dirpath, dirnames, filenames) in os.walk(args.input):
            for filename in filenames:
                if filename.endswith(".json"):
                    ThotLogger.info("Analyze :" + os.path.join(dirpath, filename))
                    with open(os.path.join(dirpath, filename)) as input_f:
                        json_request = json.load(input_f)
                        input_f.close()
                    r = requests.post(
                        args.scheme + "://" + host + ":" + str(port) + "/api/embeddings/run",
                        json=json_request,
                        verify=args.no_ssl_verify,
                    )
                    if r.status_code == 200:
                        filename = filename.replace(".json", ".embbedings.json")
                        with open(os.path.join(args.output, filename), "w") as output_f:
                            json.dump(r.json()["results"], output_f, indent=4, sort_keys=True)
                            output_f.close()
                    else:
                        ThotLogger.error("Error :" + os.path.join(dirpath, filename) + str(r))

    except Exception as e:
        ThotLogger.loads()
        ThotLogger.error("An error occured." + Constants.exception_error_and_trace(str(e), str(traceback.format_exc())))
        sys.exit(-1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default=None, type=str, help="configuration file")
    parser.add_argument("-i", "--input", default=None, type=str, help="input directory")
    parser.add_argument("-o", "--output", default=None, type=str, help="output directory")
    parser.add_argument("-s", "--scheme", default="http", type=str, help="connection scheme : http or https")
    parser.add_argument("-nsv", "--no-ssl-verify", action="store_false", help="Verify ssl certificate, default is true")
    main(parser.parse_args())
