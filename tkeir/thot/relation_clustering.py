# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
from fnmatch import fnmatch
import os
import sys
import argparse
import traceback
import json
import requests
import time
from tqdm import tqdm


dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))

from thot import __author__, __copyright__, __credits__, __maintainer__, __email__, __status__
from thot.core.ThotLogger import ThotLogger
from thot.core.Constants import exception_error_and_trace
from thot.tasks.relations.RelationClusterizerConfiguration import RelationClusterizerConfiguration
from thot.tasks.relations.RelationsClusterizer import RelationsClusterizer
from thot.tasks.embeddings.EmbeddingsConfiguration import EmbeddingsConfiguration
from thot.tasks.embeddings.Embeddings import Embeddings



def extract_svo_segment(hash_svo, input_file):
    try:
        with open(input_file) as input_f:
            syntax_file = json.load(input_f)
            input_f.close()
            for kw_item in syntax_file["keywords"]:
                kw_text = "####KW####" + kw_item["text"]
                if kw_text not in hash_svo:
                    hash_svo[kw_text] = {"count": 0, "contexts": set(), "triple_type": "keyword"}
                hash_svo[kw_text]["count"] = hash_svo[kw_text]["count"] + 1
                hash_svo[kw_text]["contexts"].add("O#O")
            for kg_item in syntax_file["kg"]:
                no_position = False
                for triple_item in ["subject", "property", "value"]:
                    if kg_item[triple_item]["positions"] == [-1]:
                        no_position = True
                if not no_position:
                    triple_texts = []
                    triple_label = []
                    for triple_item in ["subject", "property", "value"]:
                        if kg_item[triple_item]["lemma_content"]:
                            triple_texts.append(" ".join(kg_item[triple_item]["lemma_content"]))
                        else:
                            triple_texts.append(" ".join(kg_item[triple_item]["content"]))
                        triple_label.append(kg_item[triple_item]["label"])

                    cluster_subject = "####S####" + triple_texts[0]
                    cluster_relation = "####R####" + triple_texts[1]
                    cluster_object = "####O####" + triple_texts[2]

                    if cluster_relation not in hash_svo:
                        hash_svo[cluster_relation] = {"count": 0, "contexts": set(), "triple_type": "relation"}
                    if cluster_subject not in hash_svo:
                        hash_svo[cluster_subject] = {"count": 0, "contexts": set(), "triple_type": "subject"}
                    if cluster_object not in hash_svo:
                        hash_svo[cluster_object] = {"count": 0, "contexts": set(), "triple_type": "object"}

                    hash_svo[cluster_relation]["count"] = hash_svo[cluster_relation]["count"] + 1
                    hash_svo[cluster_relation]["contexts"].add(triple_label[0] + "#" + triple_label[2])
                    hash_svo[cluster_subject]["count"] = hash_svo[cluster_subject]["count"] + 1
                    hash_svo[cluster_subject]["contexts"].add(triple_label[1] + "#" + triple_label[2])
                    hash_svo[cluster_object]["count"] = hash_svo[cluster_object]["count"] + 1
                    hash_svo[cluster_object]["contexts"].add(triple_label[0] + "#" + triple_label[1])

    except Exception as e:
        print(exception_error_and_trace(str(e), str(traceback.format_exc())))


def add_class(hash_svo, input_file):
    try:
        with open(input_file, encoding="utf-8") as input_f:
            syntax_file = json.load(input_f)
            input_f.close()
            if "keywords" in syntax_file:
                for kw_item in syntax_file["keywords"]:
                    kw_text = "####KW####" + kw_item["text"]
                    kw_item["class"] = -1
                    if kw_text in hash_svo:
                        kw_item["class"] = hash_svo[kw_text]["class"]
            if "kg" in syntax_file:
                for kg_item in syntax_file["kg"]:
                    no_position = False
                    triple_texts = []
                    for triple_item in ["subject", "property", "value"]:
                        if kg_item[triple_item]["positions"] == [-1]:
                            no_position = True
                        if kg_item[triple_item]["lemma_content"]:
                            triple_texts.append(" ".join(kg_item[triple_item]["lemma_content"]))
                        else:
                            triple_texts.append(" ".join(kg_item[triple_item]["content"]))
                    if not no_position:
                        # cluster_relation = "##1## "+triple_texts[1]+" ##2##"
                        # cluster_subject = triple_texts[0]+" ##R## ##2##"
                        # cluster_object = "##1## ##R## "+triple_texts[2]
                        cluster_relation = "####R####" + triple_texts[1]
                        cluster_subject = "####S####" + triple_texts[0]
                        cluster_object = "####O####" + triple_texts[2]
                        if cluster_relation in hash_svo:
                            kg_item["property"]["class"] = hash_svo[cluster_relation]["class"]
                        else:
                            kg_item["property"]["class"] = -1
                        if cluster_subject in hash_svo:
                            kg_item["subject"]["class"] = hash_svo[cluster_subject]["class"]
                        else:
                            kg_item["subject"]["class"] = -1
                        if cluster_object in hash_svo:
                            kg_item["value"]["class"] = hash_svo[cluster_object]["class"]
                        else:
                            kg_item["value"]["class"] = -1
                    else:
                        kg_item["property"]["class"] = -1
                        kg_item["subject"]["class"] = -1
                        kg_item["value"]["class"] = -1
                with open(input_file, "w", encoding="utf-8") as output_f:
                    json.dump(syntax_file, output_f, indent=2, sort_keys=True, ensure_ascii=False)
                    output_f.close()
    except Exception as e:
        print(exception_error_and_trace(str(e), str(traceback.format_exc())))


def clusteringVectorBlock(embeddings, rcluster, config, vector_block, vector_weight, vector_type):
    start_time = time.time()
    for vi in embeddings:
        vector_block.append(vi["embedding"])
        vector_weight.append(vi["count"])
        vector_type.append(vi["triple_type"])
        if len(vector_block) >= 4096:
            et = time.time() - start_time
            (norm, cnt) = rcluster.add(vector_block, vector_weight, vector_type)
            vector_block = []
            vector_weight = []
            vector_type = []
            ThotLogger.info("Batch kmeans in '" + str(et) + "s' with error:" + str(norm) + ", on " + str(cnt) + " vectors")
    if len(vector_block):
        et = time.time() - start_time
        if len(vector_block) > config.configuration["cluster"]["number-of-classes"]:
            (norm, cnt) = rcluster.add(vector_block, vector_weight, vector_type)
            vector_block = []
            vector_weight = []
            vector_type = []
            ThotLogger.info("Batch kmeans in '" + str(et) + "s' with error:" + str(norm) + ", on " + str(cnt) + " vectors")


def cluster_train(config,input,output,exclude):
    if not config:
        ThotLogger.loads()
        ThotLogger.error("Configuration file is mandatory")
        sys.exit(-1)
    try:
        # initialize logger
        relationConfiguration = RelationClusterizerConfiguration()
        with open(config) as fh:
            relationConfiguration.load(fh)
            fh.close()
        ThotLogger.loads(relationConfiguration.logger_config.configuration)
        host = relationConfiguration.configuration["cluster"]["embeddings"]["server"]["host"]
        port = relationConfiguration.configuration["cluster"]["embeddings"]["server"]["port"]
        scheme = "http"
        if relationConfiguration.configuration["cluster"]["embeddings"]["server"]["use-ssl"]:
            scheme = "https"
        verify_ssl = not relationConfiguration.configuration["cluster"]["embeddings"]["server"]["no-verify-ssl"]

        if "aggregate" in relationConfiguration.configuration["cluster"]["embeddings"]:
            embeddings_config = EmbeddingsConfiguration()
            with open(relationConfiguration.configuration["cluster"]["embeddings"]["aggregate"]["configuration"]) as fh:
                embeddings_config.load(fh)
                fh.close()
            embeddings = Embeddings(config=embeddings_config)

        relation_file = os.path.join(output, "relation_names.json")
        ThotLogger.info("Syntax directory:" + input)
        file_list = []
        hash_svo = dict()
        exclude_list = set()
        if exclude:
            with open(exclude) as e_f:
                exclude_list = set(e_f.read().split("\n"))
                e_f.close()
        ThotLogger.info("Loaded Exclude list:" + str(len(exclude_list)) + " documents.")
        for (dirpath, dirnames, filenames) in os.walk(input):
            for filename in filenames:
                if filename.endswith(".json"):
                    fname = os.path.join(dirpath, filename)
                    if fname in exclude_list:
                        ThotLogger.info("Exclude:" + fname)
                    else:
                        file_list.append(fname)

        input_files = tqdm(file_list)

        for file_i in input_files:
            extract_svo_segment(hash_svo, file_i)
        ThotLogger.info("Semantic size:" + str(len(hash_svo)))
        rcluster = RelationsClusterizer(config=relationConfiguration)

        with open(relation_file, "w") as relation_f:
            for sent in hash_svo:
                json.dump(
                    {
                        "sentence": sent,
                        "count": hash_svo[sent]["count"],
                        "contexts": list(hash_svo[sent]["contexts"]),
                        "triple_type": hash_svo[sent]["triple_type"],
                    },
                    relation_f,
                )
                relation_f.write("\n")
            relation_f.close()

        texts = []
        counts = []
        contexts = []
        triple_types = []
        vector_block = 0
        vectors_cache = []
        vectors_cache_w = []
        vector_type = []
        vector_files = []
        with open(relation_file) as json_in_f:
            json_string = json_in_f.readline()
            while json_string:
                data = json.loads(json_string)
                json_string = json_in_f.readline()
                text_phrase = data["sentence"]
                texts.append(
                    text_phrase.replace("####R####", "")
                    .replace("####S####", "")
                    .replace("####O####", "")
                    .replace("####KW####", "")
                )
                counts.append(data["count"])
                contexts.append(data["contexts"])
                triple_types.append(data["triple_type"])
                if (len(texts) == 65536) or (not json_string):
                    ThotLogger.info("Run embeddings")
                    json_request = {"sentences": texts}
                    if not embeddings:
                        r = requests.post(
                            scheme + "://" + host + ":" + str(port) + "/api/embeddings/run_from_table",
                            json=json_request,
                            verify=verify_ssl,
                        )
                        results = r.json()["results"]
                    else:
                        results = embeddings.computeFromTable(json_request["sentences"])
                    try:
                        dump_f = open(relation_file.replace("json", str(vector_block) + ".json"), "w")
                        vector_files.append(relation_file.replace("json", str(vector_block) + ".json"))                        
                        for embi in range(len(results)):
                            results[embi]["count"] = counts[embi]
                            results[embi]["contexts"] = contexts[embi]
                            results[embi]["triple_type"] = triple_types[embi]
                            json.dump(results[embi], dump_f)
                            dump_f.write("\n")
                        dump_f.close()
                        clusteringVectorBlock(
                            results, rcluster, relationConfiguration, vectors_cache, vectors_cache_w, vector_type
                        )

                    except Exception as e:
                        print(exception_error_and_trace(str(e), str(traceback.format_exc())))
                    vector_block = vector_block + 1
                    texts = []
                    counts = []
                    contexts = []
                    triple_types = []

        for vfile_i in vector_files:
            with open(vfile_i) as vector_f:
                json_string = vector_f.readline()
                vector_loop = []
                while json_string:
                    data = json.loads(json_string)
                    vector_loop.append(data)
                    json_string = vector_f.readline()
                clusteringVectorBlock(vector_loop, rcluster, relationConfiguration, vectors_cache, vectors_cache_w, vector_type)
            vector_f.close()

        model_relation_file = relation_file.replace("json", "model.pkl")
        with open(model_relation_file, "wb") as out_f:
            rcluster.save(out_f)

        if ("clustering-model" in relationConfiguration.configuration) and (
            "semantic-quantizer-model" in relationConfiguration.configuration["clustering-model"]
        ):
            model_relation_file = relationConfiguration.configuration["clustering-model"]["semantic-quantizer-model"]
            with open(model_relation_file, "wb") as out_f:
                rcluster.save(out_f)
                out_f.close()

        with open(relation_file.replace("json", "predict.json"), "w") as pred_f:
            for vfile_i in vector_files:
                with open(vfile_i) as vector_f:
                    json_string = vector_f.readline()
                    while json_string:
                        data = json.loads(json_string)
                        json_string = vector_f.readline()
                        v = [data["embedding"]]
                        data["class"] = rcluster.predict(v, index=RelationsClusterizer.name2index[data["triple_type"]])[0]
                        prefix = "####R####"
                        if data["triple_type"] == "subject":
                            prefix = "####S####"
                        if data["triple_type"] == "object":
                            prefix = "####O####"
                        if data["triple_type"] == "keyword":
                            prefix = "####KW####"
                        typed_svo = prefix + data["content"]
                        if typed_svo in hash_svo:
                            hash_svo[typed_svo]["class"] = data["class"]
                            del data["position"]
                            del data["field"]
                            json.dump(data, pred_f)
                            pred_f.write("\n")
                        else:
                            ThotLogger.warning("Discard '" + typed_svo + "'")
                vector_f.close()
            pred_f.close()

        input_files = tqdm(file_list)
        for file_i in input_files:
            add_class(hash_svo, file_i)
    except Exception as e:
        ThotLogger.error("An error occured." + exception_error_and_trace(str(e), str(traceback.format_exc())))
        sys.exit(-1)

def main(args):
    cluster_train(args.config,args.input,args.output,args.exclude)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default=None, type=str, help="configuration file")
    parser.add_argument("-i", "--input", default=None, type=str, help="directory with syntactic analysis")
    parser.add_argument("-e", "--exclude", default=None, type=str, help="exclude file list")
    parser.add_argument("-o", "--output", default=None, type=str, help="output model directory")
    parser.add_argument("-w", "--worker", default=1, type=int, help="number of workers")
    main(parser.parse_args())
