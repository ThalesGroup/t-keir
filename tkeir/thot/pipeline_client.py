# -*- coding: utf-8 -*-
"""Run pipeline on source document to tkeir document
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
import os
import sys
import argparse
import requests
import traceback
import base64
import json
import hashlib
import csv
from joblib import Parallel, delayed
from tqdm import tqdm
import time


dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))

from thot import __author__, __copyright__, __credits__, __maintainer__, __email__, __status__
import thot.core.Constants as Constants
from thot.tasks.converters import __version_converter__, __date_converter__
from thot.core.ThotLogger import ThotLogger
from thot.tasks.taggers_pipeline.TaggersPipelineConfiguration import TaggersPipelineConfiguration


def process_data(json_request, args, host, port, input_file, additional_id=""):
    """process data to send it to the server

    Args:
        json_request ([dict]): data send to the servicer
        args ([object]): command arguments used
        host ([str]): hostname of the server
        port ([int]): port of the server
        input_file ([str]): filename of the input file
        additional_id (str, optional): Addition id in filename to serialize. Defaults to "".

    Returns:
        nothing
    """
    m = hashlib.md5()
    m.update(input_file.encode())
    hash_id = m.hexdigest()
    r = requests.post(
        args.scheme + "://" + host + ":" + str(port) + "/api/pipeline/run", json=json_request, verify=args.no_ssl_verify
    )
    if r.status_code == 200:
        ThotLogger.info(str(input_file) + " submited.")
        tokenid = r.json()["token-id"]
        filename = hash_id + "-" + tokenid + ".token.json"
        with open(os.path.join(args.output, filename), "w") as output_f:
            json.dump({"token-id": tokenid, "filename": input_file}, output_f, indent=2, sort_keys=True, ensure_ascii=False)
            output_f.close()
    else:
        ThotLogger.error(str(input_file) + " request failed.")
        print("Error :" + input_file + " results:" + str(r.content))
        return "Error :" + input_file + " results:" + str(r.content)


def process_file(args: object, host: str, port: int, input_file: str):
    """
    Open file and send it to the converter service
    :param args(object) : program argument
    :param host(str) : hostname of the service of conversion
    :param port(int) : port of the service of conversion
    :param input_file(str) : file path of the file to convert
    :return "ok" : return OK or raise exception
    """
    try:
        if args.type == "orbit-csv":
            csv.field_size_limit(sys.maxsize)
            with open(input_file, encoding="utf-8") as patent_f:
                header = patent_f.readline()
                line = patent_f.readline()
                count_entry = 0
                while line:
                    items = list(csv.reader([line]))[0]
                    content = base64.b64encode(line.encode()).decode()
                    json_request = {"datatype": args.type, "source": "file://questel-" + items[3], "data": content}
                    line = patent_f.readline()
                    process_data(json_request, args, host, port, input_file, additional_id=items[3])
                patent_f.close()
        elif args.type == "uri":
            with open(input_file, encoding="utf-8") as list_f:
                list_of_uri = list_f.read().split("\n")
                for uri in list_of_uri:
                    content = base64.b64encode(bytes(uri, "utf-8")).decode()
                    json_request = {"datatype": args.type, "source": uri, "data": content}
                    process_data(json_request, args, host, port, uri)
        else:
            with open(input_file, "rb") as input_f:
                content = base64.b64encode(input_f.read()).decode()
                input_f.close()
            json_request = {"datatype": args.type, "source": "file://" + input_file, "data": content}
            process_data(json_request, args, host, port, input_file)
        return "ok"
    except Exception as e:
        print("Error:" + Constants.exception_error_and_trace(str(e), str(traceback.format_exc())) + "On file:" + input_file)
        return "Error:" + str(e)


def main(args):
    if not args.config:
        ThotLogger.loads()
        ThotLogger.error("Configuration file is mandatory")
        sys.exit(-1)
    if not args.type:
        ThotLogger.loads()
        ThotLogger.error("Document type is mandatory")
        sys.exit(-1)
    try:
        # initialize logger
        pipelineConfiguration = TaggersPipelineConfiguration()
        with open(args.config) as fh:
            pipelineConfiguration.load(fh)
            fh.close()
        ThotLogger.loads(pipelineConfiguration.logger_config.configuration)
        host = pipelineConfiguration.net_config.configuration["network"]["host"]
        port = pipelineConfiguration.net_config.configuration["network"]["port"]
        ThotLogger.info("Convert:" + args.input)
        file_list = []
        for (dirpath, dirnames, filenames) in os.walk(args.input):
            for filename in filenames:
                file_list.append(os.path.join(dirpath, filename))
        input_files = tqdm(file_list)
        json_request = {"action": "start"}
        r = requests.post(
            args.scheme + "://" + host + ":" + str(port) + "/api/pipeline/run", json=json_request, verify=args.no_ssl_verify
        )
        processed_list = Parallel(n_jobs=args.workers)(delayed(process_file)(args, host, port, i) for i in input_files)
        json_request["action"] = "finish"
        r = requests.post(
            args.scheme + "://" + host + ":" + str(port) + "/api/pipeline/run", json=json_request, verify=args.no_ssl_verify
        )
        file_list = []
        for (dirpath, dirnames, filenames) in os.walk(args.output):
            for filename in filenames:
                if filename.endswith(".token.json"):
                    file_list.append(os.path.join(dirpath, filename))
        already_analyzed = set()
        while len(already_analyzed) != len(input_files):
            input_files = tqdm(file_list)
            for file_to_get in input_files:
                try:
                    with open(file_to_get) as tok_f:
                        token_data = json.load(tok_f)
                        tok_f.close()
                        token_data["token-id"]
                        if file_to_get not in already_analyzed:
                            r = requests.post(
                                args.scheme + "://" + host + ":" + str(port) + "/api/pipeline/get",
                                json=token_data,
                                verify=args.no_ssl_verify,
                            )
                            if (
                                (r.status_code == 200)
                                and (r.json()["token-status"] == "ready")
                                and (file_to_get not in already_analyzed)
                            ):
                                with open(file_to_get.replace("token.json", "analyzed.json"), "w") as output_f:
                                    json.dump(r.json()["results"], output_f, indent=2, sort_keys=True, ensure_ascii=False)
                                    output_f.close()
                                    already_analyzed.add(file_to_get)
                            if r.status_code == 500:
                                ThotLogger.error("Token " + json.dumps(token_data) + " ### " + json.dumps(r.json()) + " failed")
                                already_analyzed.add(file_to_get)
                except Exception as oe:
                    ThotLogger.error(
                        "Cannot open file '"
                        + file_to_get
                        + "', "
                        + Constants.exception_error_and_trace(str(oe), str(traceback.format_exc()))
                    )
                    already_analyzed.add(file_to_get)
            # check possible lack:
            remaning_files = set(input_files) - already_analyzed
            if len(remaning_files) < 2:
                ThotLogger.info("Remaining files:" + str(remaning_files))
            for file_to_get in input_files:
                if file_to_get not in already_analyzed:
                    check_file = file_to_get.replace("token.json", "analyzed.json")
                    if os.path.isfile(check_file):
                        already_analyzed.add(file_to_get)
                        ThotLogger.error("File '" + file_to_get + " Already analyzed.")
            ThotLogger.info("Remaining files:" + str(len(already_analyzed)) + "/" + str(len(input_files)))
            time.sleep(args.loop_time)

    except Exception as e:
        ThotLogger.loads()
        ThotLogger.error(
            "An error occured.Exception:" + Constants.exception_error_and_trace(str(e), str(traceback.format_exc()))
        )
        sys.exit(-1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default=None, type=str, help="configuration file")
    parser.add_argument("-t", "--type", default=None, type=str, help="configuration file")
    parser.add_argument("-i", "--input", default=None, type=str, help="input directory")
    parser.add_argument("-o", "--output", default=None, type=str, help="output directory")
    parser.add_argument("-w", "--workers", default=1, type=int, help="number of workers")
    parser.add_argument("-s", "--scheme", default="http", type=str, help="connection scheme : http or https")
    parser.add_argument("-nsv", "--no-ssl-verify", action="store_false", help="Verify ssl certificate, default is true")
    parser.add_argument("-l", "--loop-time", default=300, type=int, help="time between two get loop")
    main(parser.parse_args())
