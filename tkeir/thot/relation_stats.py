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
import json
from tqdm import tqdm

dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", default=None, type=str, help="syntax directory")
    parser.add_argument("-o", "--output", default=None, type=str, help="output stats")
    args = parser.parse_args()
    try:
        file_list = []
        for (dirpath, dirnames, filenames) in os.walk(args.input):
            for filename in filenames:
                if filename.endswith(".json"):
                    fname = os.path.join(dirpath, filename)
                    file_list.append(fname)
        input_files = tqdm(file_list)
        relations = dict()
        s_stat = dict()
        r_stat = dict()
        o_stat = dict()
        stat_oov = dict()
        for input_file in input_files:
            with open(input_file) as input_f:
                syntax_file = json.load(input_f)
                input_f.close()
                if "content_morphosyntax" in syntax_file:
                    for tok in syntax_file["content_morphosyntax"]:
                        if tok["is_oov"]:
                            if tok["lemma"] not in stat_oov:
                                stat_oov[tok["lemma"]] = 0
                            stat_oov[tok["lemma"]] = stat_oov[tok["lemma"]] + 1
                if "kg" in syntax_file:
                    for kg_item in syntax_file["kg"]:
                        if kg_item["property"]["class"] != -1:
                            if kg_item["property"]["class"] not in relations:
                                relations[kg_item["property"]["class"]] = {"count": 0, "ctx": dict()}
                            lemma = " ".join(kg_item["property"]["lemma_content"])
                            class_r = kg_item["property"]["class"]
                            lemma_s = " ".join(kg_item["subject"]["lemma_content"])
                            class_s = kg_item["subject"]["class"]
                            lemma_o = " ".join(kg_item["value"]["lemma_content"])
                            class_o = kg_item["value"]["class"]
                            if class_s not in s_stat:
                                s_stat[class_s] = dict()
                            if class_r not in r_stat:
                                r_stat[class_r] = dict()
                            if class_o not in o_stat:
                                o_stat[class_o] = dict()
                            if lemma_s not in s_stat[class_s]:
                                s_stat[class_s][lemma_s] = 0
                            if lemma not in r_stat[class_r]:
                                r_stat[class_r][lemma] = 0
                            if lemma_o not in o_stat[class_o]:
                                o_stat[class_o][lemma_o] = 0
                            s_stat[class_s][lemma_s] = s_stat[class_s][lemma_s] + 1
                            r_stat[class_r][lemma] = r_stat[class_r][lemma] + 1
                            o_stat[class_o][lemma_o] = o_stat[class_o][lemma_o] + 1

                            if lemma not in relations[class_r]["ctx"]:
                                relations[class_r]["ctx"][lemma] = {"count": 0, "subject": dict(), "object": dict()}
                            relations[class_r]["count"] = relations[class_r]["count"] + 1
                            relations[class_r]["ctx"][lemma]["count"] = relations[class_r]["ctx"][lemma]["count"] + 1
                            if class_s not in relations[class_r]["ctx"][lemma]["subject"]:
                                relations[class_r]["ctx"][lemma]["subject"][class_s] = {"count": 0, "ctx": dict()}
                            if class_o not in relations[class_r]["ctx"][lemma]["object"]:
                                relations[class_r]["ctx"][lemma]["object"][class_o] = {"count": 0, "ctx": dict()}
                            if lemma_o not in relations[class_r]["ctx"][lemma]["object"][class_o]["ctx"]:
                                relations[class_r]["ctx"][lemma]["object"][class_o]["ctx"][lemma_o] = 0
                            if lemma_s not in relations[class_r]["ctx"][lemma]["subject"][class_s]["ctx"]:
                                relations[class_r]["ctx"][lemma]["subject"][class_s]["ctx"][lemma_s] = 0
                            relations[class_r]["ctx"][lemma]["subject"][class_s]["count"] = (
                                relations[class_r]["ctx"][lemma]["subject"][class_s]["count"] + 1
                            )
                            relations[class_r]["ctx"][lemma]["object"][class_o]["count"] = (
                                relations[class_r]["ctx"][lemma]["object"][class_o]["count"] + 1
                            )
                            relations[class_r]["ctx"][lemma]["subject"][class_s]["ctx"][lemma_s] = (
                                relations[class_r]["ctx"][lemma]["subject"][class_s]["ctx"][lemma_s] + 1
                            )
                            relations[class_r]["ctx"][lemma]["object"][class_o]["ctx"][lemma_o] = (
                                relations[class_r]["ctx"][lemma]["object"][class_o]["ctx"][lemma_o] + 1
                            )

        best_relation = dict()
        stat_oov = list(
            map(
                lambda x: {"content": x[0], "count": stat_oov[x[0]]},
                sorted(stat_oov.items(), key=lambda x: stat_oov[x[0]], reverse=True),
            )
        )

        for class_i in relations:
            best_relation[class_i] = sorted(relations[class_i]["ctx"].items(), key=lambda x: x[1]["count"], reverse=True)
            if class_i in s_stat:
                s_stat[class_i] = list(
                    map(
                        lambda x, class_i=class_i: {"content": x[0], "count": s_stat[class_i][x[0]]},
                        sorted(s_stat[class_i].items(), key=lambda x: s_stat[class_i][x[0]], reverse=True),
                    )
                )
            if class_i in r_stat:
                r_stat[class_i] = list(
                    map(
                        lambda x, class_i=class_i: {"content": x[0], "count": r_stat[class_i][x[0]]},
                        sorted(r_stat[class_i].items(), key=lambda x: r_stat[class_i][x[0]], reverse=True),
                    )
                )
            if class_i in o_stat:
                o_stat[class_i] = list(
                    map(
                        lambda x, class_i=class_i: {"content": x[0], "count": o_stat[class_i][x[0]]},
                        sorted(o_stat[class_i].items(), key=lambda x: o_stat[class_i][x[0]], reverse=True),
                    )
                )

            best_relation[class_i] = best_relation[class_i][0:10]
            relations[class_i] = []
            for k in range(len(best_relation[class_i])):
                relations[class_i].append(best_relation[class_i][k][0])
                for class_si in best_relation[class_i][k][1]["subject"]:
                    best_relation[class_i][k][1]["subject"][class_si] = sorted(
                        best_relation[class_i][k][1]["subject"][class_si]["ctx"].items(), key=lambda x: x[1], reverse=True
                    )
                    best_relation[class_i][k][1]["subject"][class_si] = " ## ".join(
                        list(map(lambda y: y[0], best_relation[class_i][k][1]["subject"][class_si][0:10]))
                    )
                for class_oi in best_relation[class_i][k][1]["object"]:
                    best_relation[class_i][k][1]["object"][class_oi] = sorted(
                        best_relation[class_i][k][1]["object"][class_oi]["ctx"].items(), key=lambda x: x[1], reverse=True
                    )
                    best_relation[class_i][k][1]["object"][class_oi] = " ## ".join(
                        list(map(lambda y: y[0], best_relation[class_i][k][1]["object"][class_oi][0:10]))
                    )
        with open(args.output, "w") as out_f:
            json.dump(
                {
                    "oov": stat_oov,
                    "subject-classes": s_stat,
                    "property-classes": r_stat,
                    "object-classes": o_stat,
                    "in-context": best_relation,
                },
                out_f,
                indent=2,
            )
            out_f.close()

    except Exception as e:
        print("An error occured.Exception:" + str(e) + " - trace:" + str(traceback.format_exc()))
        sys.exit(-1)


if __name__ == "__main__":
    main()
