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
from joblib import Parallel, delayed
from tqdm import tqdm

dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))

from thot import __author__, __copyright__, __credits__, __maintainer__, __email__, __status__
import thot.core.Constants as Constants
from thot.tasks.sentiment import __version_sentiment__, __date_sentiment__
from thot.core.ThotLogger import ThotLogger
from thot.tasks.sentiment.SentimentAnalysisConfiguration import SentimentAnalysisConfiguration


def process_file(args, host, port, input_file):
    """process data to send it to the server
    Args:
        args ([object]): command arguments used
        host ([str]): hostname of the server
        port ([int]): port of the server
        input_file ([str]): filename of the input file
    Returns:
        [str]: "ok"
    """
    try:
        with open(input_file, encoding="utf-8") as input_f:
            json_request = json.load(input_f)
            input_f.close()
        r = requests.post(
            args.scheme + "://" + host + ":" + str(port) + "/api/sentimentclassifier/run",
            json=json_request,
            verify=args.no_ssl_verify,
        )
        if r.status_code == 200:
            filename = os.path.basename(input_file).replace(".json", ".sentiment.json")
            with open(os.path.join(args.output, filename), "w", encoding="utf-8") as output_f:
                json.dump(r.json()["results"], output_f, indent=2, sort_keys=True, ensure_ascii=False)
                output_f.close()
        else:
            print("Error :" + input_file + " results:" + str(r))
            return "Error :" + input_file + " results:" + str(r)
        return "ok"
    except Exception as e:
        print(Constants.exception_error_and_trace(str(e), str(traceback.format_exc())))
        return Constants.exception_error_and_trace(str(e), str(traceback.format_exc()))


def main(args):
    if not args.config:
        ThotLogger.loads()
        ThotLogger.error("Configuration file is mandatory")
        sys.exit(-1)
    try:
        # initialize logger
        sentimentConfiguration = SentimentAnalysisConfiguration()
        with open(args.config) as fh:
            sentimentConfiguration.load(fh)
            fh.close()
        ThotLogger.loads(sentimentConfiguration.logger_config.configuration)
        host = sentimentConfiguration.net_config.configuration["network"]["host"]
        port = sentimentConfiguration.net_config.configuration["network"]["port"]
        ThotLogger.info("Tokenize:" + args.input)
        file_list = []
        for (dirpath, dirnames, filenames) in os.walk(args.input):
            for filename in filenames:
                if filename.endswith(".json"):
                    file_list.append(os.path.join(dirpath, filename))
        input_files = tqdm(file_list)
        processed_list = Parallel(n_jobs=args.workers)(delayed(process_file)(args, host, port, i) for i in input_files)

    except Exception as e:
        ThotLogger.loads()
        ThotLogger.error(
            "An error occured.Exception:" + Constants.exception_error_and_trace(str(e), str(traceback.format_exc()))
        )
        sys.exit(-1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default=None, type=str, help="configuration file")
    parser.add_argument("-i", "--input", default=None, type=str, help="input directory")
    parser.add_argument("-o", "--output", default=None, type=str, help="output directory")
    parser.add_argument("-w", "--workers", default=1, type=int, help="number of workers")
    parser.add_argument("-s", "--scheme", default="http", type=str, help="connection scheme : http or https")
    parser.add_argument("-nsv", "--no-ssl-verify", action="store_false", help="Verify ssl certificate, default is true")
    main(parser.parse_args())
