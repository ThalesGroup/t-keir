# -*- coding: utf-8 -*-
"""Create model of annotation 

Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import argparse
import os
import sys
import logging
import traceback
import json

dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))

from thot import __version__, __date__, __author__
from thot.core.ThotLogger import ThotLogger
from thot.tasks.tokenizer.AnnotationConfiguration import AnnotationConfiguration
from thot.tasks.tokenizer.AnnotationResources import AnnotationResources
from thot.tasks.tokenizer import __version_tokenizer__, __date_tokenizer__


if __name__ == "__main__":
    print("Resource Annotation")
    print("===================")
    print("Version: " + __version_tokenizer__)
    print("Author:  " + __author__)
    print("Date:    " + __date_tokenizer__)
    parser = argparse.ArgumentParser()
    parser.add_argument("--entries-file", type=str, default=None, help="file containing dataset")
    parser.add_argument("--output", type=str, default="tkeir_mwe.pkl", help="tokenizer multi word expresion")
    patterns = []
    try:
        args = parser.parse_args()
    except Exception as e:
        logging.error("Exception raised:" + str(e))
        sys.exit(-1)
    try:
        with open(args.entries_file) as config_f:
            a_config = json.load(config_f)
            config_f.close()
            annot_config = AnnotationConfiguration()
            annotte_modeling = AnnotationResources()
            ThotLogger.loads(a_config, logger_name="annotation")
            annot_config.loads(a_config)
            annotte_modeling.createModel(annot_config.configuration, args.output)
    except Exception as e:
        print("An error occured. Exception" + str(e) + ", trace:" + str(traceback.format_exc()))
        sys.exit(-1)
