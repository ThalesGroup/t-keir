# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

# OS import
import logging
import os
import sys
import json
import argparse
import fnmatch
import traceback
import hashlib
import re
import time
from copy import deepcopy
from tqdm import tqdm

dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))

# Import Theresis plugins
from thot import __author__, __copyright__, __credits__, __maintainer__, __email__, __status__
import thot.core.Constants as Constants
from thot.core.ThotLogger import ThotLogger
from thot.tasks.indexing import __version_indexing__, __date_indexing__
from thot.tasks.indexing.IndexingConfiguration import IndexingConfiguration
from thot.tasks.indexing.Indexing import Indexing
from thot.tasks.indexing.IndicesManager import IndicesManager
from thot.tasks.indexing.ESDocumentIndexer import ESDocumentIndexer
from thot.tasks.indexing.NmsDocumentIndexer import NmsDocumentIndexer
from thot.tasks.indexing.RelationDocumentIndexer import RelationDocumentIndexer


def format2text_index(document, indexing):
    json_doc = None
    with open(document) as json_f:
        json_doc = json.load(json_f)
        json_f.close()
        return indexing.doc2index(json_doc)
    return None


def doc2index(file_list, indexing):
    files2analyze = tqdm(file_list)
    for file in files2analyze:
        try:
            (hash_id, tkeir_doc) = format2text_index(file, indexing)
            with open(file + "." + args.type + ".indexed", "w") as mark_f:
                mark_info = {
                    "time": time.time(),
                    "type": args.type,
                }
                json.dump(mark_info, mark_f)
                mark_f.close()
            yield {
                "_index": ESDocumentIndexer.config["elasticsearch"]["text-index"]["name"],
                "_id": hash_id,
                "_source": tkeir_doc,
            }
        except Exception as e:
            ThotLogger.error(
                "Indexation failed on file '"
                + file
                + "': error:"
                + Constants.exception_error_and_trace(str(e), str(traceback.format_exc()))
            )


def doc2embeddings_index(document):
    with open(document) as json_f:
        json_doc = json.load(json_f)
        json_f.close()
        if ("data_source" in json_doc) and ("source_doc_id" in json_doc):
            m = hashlib.md5()
            m.update(str(json_doc["data_source"] + json_doc["source_doc_id"]).encode())
            hash_id = "cacheid_" + m.hexdigest()
            sentence_embeddings_data = json_doc["embedddings"]  # TODO fix typo
            for by_field_i in range(len(sentence_embeddings_data)):
                for sent_i in range(len(sentence_embeddings_data[by_field_i])):
                    del sentence_embeddings_data[by_field_i][sent_i]["field"]
                    sentence_embeddings_data[by_field_i][sent_i]["cache_doc_id"] = hash_id
                    sentence_embeddings_data[by_field_i][sent_i]["title"] = json_doc["title"]
                    sentence_embeddings_data[by_field_i][sent_i]["source_doc_id"] = json_doc["source_doc_id"]
                    yield {
                        "_index": NmsDocumentIndexer.config["elasticsearch"]["nms-index"]["name"],
                        "_id": str(sent_i) + "/" + hash_id,
                        "_source": sentence_embeddings_data[by_field_i][sent_i],
                    }


def relation2index(document):
    with open(document) as jsl_f:
        json_string = jsl_f.readline()
        while json_string:
            relation_data = json.loads(json_string)
            json_string = jsl_f.readline()
            yield {"_index": NmsDocumentIndexer.config["elasticsearch"]["relation-index"]["name"], "_source": relation_data}
        jsl_f.close()


def main(args):
    """Run Conversion

    :param args (nested structure) : contain the argument of the program
    :return according to the argument write a file or display on standard output
    """
    if not args.config:
        raise ValueError("Configuration file argument is mandatory")
    configuration = IndexingConfiguration()
    try:
        with open(args.config) as cfg_f:
            configuration.load(cfg_f)
    except Exception as e:
        ThotLogger.loads()
        ThotLogger.error("Configuration file is mandatory" + str(e))
        sys.exit(-1)
    ThotLogger.loads(configuration.logger_config.configuration)
    config = configuration.configuration
    indexing = Indexing(config=configuration)

    if not config:
        logging.error("Configuration file is mandatory, load is empty")
        sys.exit(0)

    ThotLogger.info("Document Indexer")
    ThotLogger.info("===================")
    ThotLogger.info("Version: " + __version_indexing__)
    ThotLogger.info("Author:  " + __author__)
    ThotLogger.info("Date:    " + __date_indexing__)

    try:
        IndicesManager.createIndices(config=config)
    except Exception as e:
        tracebck = traceback.format_exc()
        ThotLogger.error(Constants.exception_error_and_trace(str(e), str(tracebck)))
    ESDocumentIndexer.configure(config)
    NmsDocumentIndexer.configure(config)
    RelationDocumentIndexer.configure(config)
    file_list = []
    exclude_list = set()
    if os.path.isfile(args.document) and (args.type == "relation"):
        RelationDocumentIndexer.bulk(relation2index(args.document))
    elif os.path.isdir(args.document):
        if args.exclude:
            with open(args.exclude) as e_f:
                exclude_list = set(e_f.read().split("\n"))
                e_f.close()
        for root, dir, files in os.walk(args.document):
            for item in fnmatch.filter(files, "*.json"):
                document2index = os.path.join(root, item)
                if document2index in exclude_list:
                    ThotLogger.info("Exclude :" + document2index)
                else:
                    file_list.append(document2index)
        if args.type == "document":
            rm_duplicate = False
            if ("document" in config) and ("remove-knowledge-graph-duplicates" in config["document"]):
                rm_duplicate = config["document"]["remove-knowledge-graph-duplicates"]
            ThotLogger.info("Remove duplication :" + str(rm_duplicate))
            ESDocumentIndexer.bulk(doc2index(file_list, indexing))
        else:
            files2analyze = tqdm(file_list)
            for analyzed_document in files2analyze:
                try:
                    test_is_indexed = analyzed_document + "." + args.type + ".indexed"
                    if not os.path.isfile(test_is_indexed):
                        NmsDocumentIndexer.bulk(analyzed_document, doc2embeddings_index(analyzed_document))
                        with open(analyzed_document + "." + args.type + ".indexed", "w") as mark_f:
                            mark_info = {
                                "time": time.time(),
                                "type": args.type,
                            }
                            json.dump(mark_info, mark_f)
                            mark_f.close()
                    else:
                        ThotLogger.info("Skip:" + analyzed_document)
                except Exception as e:
                    ThotLogger.warning(
                        "Error in '"
                        + analyzed_document
                        + "' "
                        + Constants.exception_error_and_trace(str(e), str(traceback.format_exc()))
                    )
    else:
        raise ValueError("If 'document' argument must be a dicrectory")


"""
    MAIN Program : run instruction a program start
"""
dname = os.path.dirname(__file__)

if dname:
    os.chdir(dname)

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--document", default=None, type=str, help="directory to index (or file in case of relation)")
parser.add_argument("-t", "--type", default="document", type=str, help="[embeddings | document | relation]")
parser.add_argument("-c", "--config", default=None, type=str, help="configuration file")
parser.add_argument("-e", "--exclude", default=None, type=str, help="exclude files")
args = parser.parse_args()

main(args)
