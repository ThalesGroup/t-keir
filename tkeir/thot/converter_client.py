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
import base64
import json
import hashlib
import csv
from joblib import Parallel, delayed
from tqdm import tqdm


dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))

from thot import __author__, __copyright__, __credits__, __maintainer__, __email__, __status__
import thot.core.Constants as Constants
from thot.tasks.converters import __version_converter__, __date_converter__
from thot.core.ThotLogger import ThotLogger
from thot.tasks.converters.ConverterConfiguration import ConverterConfiguration


def process_data(json_request, args, host, port, do_zip, input_file, additional_id=""):
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
        args.scheme + "://" + host + ":" + str(port) + "/api/converter/run", json=json_request, verify=args.no_ssl_verify
    )
    if r.status_code == 200:
        if additional_id:
            additional_id = "." + additional_id
        input_file = (
            input_file.replace("/", "_")
            .replace(":", "_")
            .replace("&", "_")
            .replace("=", "_")
            .replace("?", "_")
            .replace(" ", "_")
        )
        if len(input_file) > 255:
            input_file = input_file[0:32]
        filename = hash_id+"-"+os.path.basename(input_file) + additional_id + ".converted.json"
        ThotLogger.info("Save:"+filename)
        with open(os.path.join(args.output, filename), "w") as output_f:
            json.dump(r.json()["results"], output_f, indent=1, sort_keys=True, ensure_ascii=False)
            output_f.close()
        return "ok"
    else:
        print("Error :" + input_file + " results:" + str(r.text))
        return "Error :" + input_file + " results:" + str(r.text)


def process_file(args: object, host: str, port: int, do_zip: bool, input_file: str):
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
                patent_f.readline()
                line = patent_f.readline()
                while line:
                    items = list(csv.reader([line]))[0]
                    content = base64.b64encode(line.encode()).decode()
                    json_request = {"datatype": args.type, "source": "file://questel-" + items[3], "data": content}
                    line = patent_f.readline()
                    process_data(json_request, args, host, port, do_zip, input_file, additional_id=items[3])
                patent_f.close()
        elif args.type == "uri":
            with open(input_file, encoding="utf-8") as list_f:
                list_of_uri = list_f.read().split("\n")
                count_file = 0
                for uri in list_of_uri:
                    count_file = count_file + 1
                    if uri:
                        content = base64.b64encode(bytes(uri, "utf-8")).decode()
                        json_request = {"datatype": args.type, "source": uri, "data": content}
                        ThotLogger.info("Process URI:" + uri)
                        process_data(json_request, args, host, port, do_zip, uri)
        else:
            with open(input_file, "rb") as input_f:
                content = base64.b64encode(input_f.read()).decode()
                input_f.close()
            json_request = {"datatype": args.type, "source": "file://" + input_file, "data": content}
            process_data(json_request, args, host, port, do_zip, input_file)

        return "ok"
    except Exception as e:
        print(
            "Exception occured."
            + Constants.exception_error_and_trace(str(e), traceback.format_exc())
            + " On file:"
            + input_file
        )
        return "Error:" + Constants.exception_error_and_trace(str(e), traceback.format_exc())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default=None, type=str, help="configuration file")
    parser.add_argument("-t", "--type", default=None, type=str, help="configuration file")
    parser.add_argument("-i", "--input", default=None, type=str, help="input directory")
    parser.add_argument("-o", "--output", default=None, type=str, help="output directory")
    parser.add_argument("-w", "--workers", default=1, type=int, help="number of workers")
    parser.add_argument("-s", "--scheme", default="http", type=str, help="connection scheme : http or https")
    parser.add_argument("-nsv", "--no-ssl-verify", action="store_false", help="Verify ssl certificate, default is true")
    args = parser.parse_args()
    ThotLogger.loads()
    if not args.config:
        ThotLogger.error("Configuration file is mandatory")
        sys.exit(-1)
    if not args.type:       
        ThotLogger.error("Document type is mandatory")
        sys.exit(-1)
    if args.scheme not in ["http", "https"]:
        ThotLogger.warning("Bad Scheme")
    try:
        # initialize logger
        converter_configuration = ConverterConfiguration()
        with open(args.config) as fh:
            converter_configuration.load(fh)
            fh.close()
        ThotLogger.loads(converter_configuration.logger_config.configuration)
        host = converter_configuration.net_config.configuration["network"]["host"]
        port = converter_configuration.net_config.configuration["network"]["port"]
        do_zip = False
        if "zip" in converter_configuration.configuration["settings"]:
            do_zip = converter_configuration.configuration["settings"]["zip"]
        ThotLogger.info("Convert:" + args.input)
        file_list = []
        for (dirpath, dirnames, filenames) in os.walk(args.input):
            for filename in filenames:
                file_list.append(os.path.join(dirpath, filename))
        input_files = tqdm(file_list)
        Parallel(n_jobs=args.workers)(delayed(process_file)(args, host, port, do_zip, i) for i in input_files)

    except Exception as e:
        ThotLogger.loads()
        ThotLogger.error("An error occured." + Constants.exception_error_and_trace(str(e), str(traceback.format_exc())))
        sys.exit(-1)


if __name__ == "__main__":
    main()
