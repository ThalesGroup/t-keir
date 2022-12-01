# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
import os
import sys
import argparse
import traceback


dir_path = os.path.dirname(os.path.realpath(__file__))

sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))

import thot.core.Constants as Constants
from thot.tasks.evaluation.IREval import IREval


from thot import __author__, __copyright__, __credits__, __maintainer__, __email__, __status__


def main(args):

    ireval = IREval()

    if args.stats:
        ireval.doStat(args.output, args.stats.split(","))
    else:
        if not args.queries:
            raise ValueError("Query file is mandatory")
        if not args.output:
            raise ValueError("Output directory is mandatory")
        if not os.path.isdir(args.output):
            raise ValueError("Output directory MUST be a directory")
        try:

            ireval.evaluate(args.output, args.name, args.queries, args.prune, args.bypass)
        except Exception as e:
            print(Constants.exception_error_and_trace(str(e), str(traceback.format_exc())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-q", "--queries", default=None, type=str, help="queries to run")
    parser.add_argument("-o", "--output", default=None, type=str, help="output directory")
    parser.add_argument("-n", "--name", default="tkeireval", type=str, help="eval name")
    parser.add_argument("-p", "--prune", default=-1, type=int, help="mx number of requests")
    parser.add_argument("-b", "--bypass", default=-1, type=int, help="skip start query")
    parser.add_argument("-s", "--stats", default=None, type=str, help="comma sperated file list")
    main(parser.parse_args())
