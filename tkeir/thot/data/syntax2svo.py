# -*- coding: utf-8 -*-
"""Data management and generation

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import os
import sys
import json
import argparse
import string
from tqdm import tqdm
from conllu import parse_tree_incr
import pandas as pd

sw_tags = set(["ADP", "DET", "PART", "PRON", "PUNCT", "SYM", "INTJ"])

# relation,subject,object


def untree(child_tree, list_token):
    list_token.append({"upos": child_tree.token["upos"], "form": child_tree.token["form"], "id": child_tree.token["id"]})
    for c in child_tree.children:
        if c.token["upos"] != "VERB":
            untree(c, list_token)


def get_verbs(child_tree, list_verb, up_tree):

    if (child_tree.token["upos"] == "VERB") or (child_tree.token["upos"] == "AUX"):
        list_verb.append({"verb": child_tree, "subject": None})
        if "xcomp" in child_tree.token["deprel"]:
            list_verb[-1]["subject"] = up_tree
        if "acl" in child_tree.token["deprel"]:
            for c in child_tree.children:
                if "subj" in c.token["deprel"]:
                    list_verb[-1]["subject"] = c
            if up_tree and (not list_verb[-1]["subject"]) and ("subj" in up_tree.token["deprel"]):  # search subj in up tree
                list_verb[-1]["subject"] = up_tree
    for c in child_tree.children:
        get_verbs(c, list_verb, child_tree)


def merge_tokens(tokens):
    entry = []
    for tok in tokens:
        if (tok["upos"] not in sw_tags) and (len(set(tok["form"]) - set(string.punctuation + "/")) > 0):
            entry.append(tok["form"])
    return " ".join(entry)


def prune_relations(relations):
    pruned_relation = []
    for relation in relations:
        subjects = set()
        objects = set()
        count_s_tok = 0
        count_o_tok = 0
        for tokens in relation["s"]:
            if (len(tokens) != 1) or (tokens[0]["upos"] != "PRON"):
                m = merge_tokens(tokens)
                if m:
                    subjects.add(m)
            for tok in tokens:
                if tok["upos"] not in sw_tags:
                    count_s_tok = count_s_tok + 1
        for tokens in relation["o"]:
            m = merge_tokens(tokens)
            if m:
                objects.add(m)
            for tok in tokens:
                if tok["upos"] not in sw_tags:
                    count_o_tok = count_s_tok + 1
        if len(subjects) > 0 and (len(objects) > 0) and (count_s_tok > 0) and (count_o_tok > 0):
            pruned_relation.append({"h": list(subjects), "relation": relation["r"], "t": list(objects)})
    return pruned_relation


def get_relation(root_tree):
    relations = []
    verbs = []
    get_verbs(root_tree, verbs, None)
    for v in verbs:
        subjects = []
        objects = []
        if v["subject"]:
            s = []
            untree(v["subject"], s)
            s.sort(key=lambda x: x["id"])
            subjects.append(s)
        for child in v["verb"].children:
            if "subj" in child.token["deprel"]:
                s = []
                untree(child, s)
                s.sort(key=lambda x: x["id"])
                subjects.append(s)
            if ("obj" in child.token["deprel"]) or ("obl" in child.token["deprel"]) or ("comp" in child.token["deprel"]):
                o = []
                untree(child, o)
                o.sort(key=lambda x: x["id"])
                objects.append(o)
        relation = {"s": subjects, "r": v["verb"].token["form"], "o": objects}
        relations.append(relation)
    relations = prune_relations(relations)
    return relations


def get_language(filename):
    paths = filename.split("/")
    lang = paths[-1].split("_")
    return lang[0]


def write_in_file(conllu_f, output_df, lang):
    for s in parse_tree_incr(conllu_f):
        root_tree = s
        # s.print_tree()
        relations = get_relation(root_tree)
        text = s.metadata["text"]
        if "|" in text:
            text = text.replace("|", " ")
        if "+" in text:
            text = text.replace("+", " ")
        rels = []
        for r in relations:
            subjects = []
            objects = []
            for s in r["h"]:
                subjects.append(" ".join(s.replace(",", " ").replace("|", " ").replace("+", " ").replace(";", " ").split()))
            for o in r["t"]:
                objects.append(" ".join(o.replace(",", " ").replace("|", " ").replace("+", " ").replace(";", " ").split()))
            rel = " | ".join(subjects) + " + " + r["relation"] + " + " + "|".join(objects)
            rels.append(rel)
        target = ";".join(rels)
        if "_" in target:
            target = target.replace("_", "-").replace("\t", " ")
        if not target:
            target = "_"
        if set(text.split()) != set(["_"]):
            ndf = pd.DataFrame([["svo", lang, text, target]], columns=["prefix", "language", "input_text", "target_text"])
            output_df = pd.concat([output_df, ndf])
    return output_df


def main(args):
    train = []
    test = []
    dev = []
    for (dirpath, dirnames, filenames) in os.walk(args.input):
        for filename in filenames:
            if filename.endswith(".conllu") and ("train" in filename.lower()):
                train.append(os.path.join(dirpath, filename))
            elif filename.endswith(".conllu") and ("test" in filename.lower()):
                test.append(os.path.join(dirpath, filename))
            elif filename.endswith(".conllu") and ("dev" in filename.lower()):
                dev.append(os.path.join(dirpath, filename))
    train_files = tqdm(train)
    test_files = tqdm(test)
    dev_files = tqdm(dev)
    train_df = pd.DataFrame(columns=["prefix", "language", "input_text", "target_text"]).astype(str)
    dev_df = pd.DataFrame(columns=["prefix", "language", "input_text", "target_text"]).astype(str)
    test_df = pd.DataFrame(columns=["prefix", "language", "input_text", "target_text"]).astype(str)
    for file in train_files:
        lang = get_language(file)
        print("Train Language:", lang)
        with open(file, "r", encoding="utf-8") as conllu_f:
            train_df = write_in_file(conllu_f, train_df, lang)
            conllu_f.close()
    train_df.to_csv(
        args.output + "-train.tsv",
        index=False,
        sep="\t",
        encoding="utf-8",
        columns=["prefix", "language", "input_text", "target_text"],
    )
    for file in test_files:
        lang = get_language(file)
        print("Test Language:", lang)
        with open(file, "r", encoding="utf-8") as conllu_f:
            test_df = write_in_file(conllu_f, test_df, lang)
            conllu_f.close()
    test_df.reset_index().to_csv(
        args.output + "-test.tsv",
        index=False,
        sep="\t",
        encoding="utf-8",
        columns=["prefix", "language", "input_text", "target_text"],
    )
    for file in dev_files:
        lang = get_language(file)
        print("Dev Language:", lang)
        with open(file, "r", encoding="utf-8") as conllu_f:
            dev_df = write_in_file(conllu_f, dev_df, lang)
            conllu_f.close()
    dev_df.to_csv(
        args.output + "-dev.tsv",
        index=False,
        sep="\t",
        encoding="utf-8",
        columns=["prefix", "language", "input_text", "target_text"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", default=None, type=str, help="UD framework directory")
    parser.add_argument("-o", "--output", default="./out", type=str, help="UD framework directory")
    main(parser.parse_args())
