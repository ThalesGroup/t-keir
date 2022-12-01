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
from conllu import parse_incr
import pandas as pd

sw_tags = set(["ADP", "AUX", "CCONJ", "DET", "NUM", "PART", "SCONJ", "PRON", "PUNCT", "SYM", "INTJ"])


def get_language(filename):
    paths = filename.split("/")
    lang = paths[-1].split("_")
    return lang[0]


def write_in_file(conllu_f, output_df, lang):
    for s in parse_incr(conllu_f):
        form_sent = []
        lemma_sent = []
        for tok in s:
            form_sent.append(tok["form"])
            if (tok["upos"] not in sw_tags) and (len(set(tok["lemma"]) - set(string.punctuation + "/")) > 0):
                lemma_sent.append(tok["lemma"])
            else:
                lemma_sent.append("_")
        # TODO __ also in sentence
        if (len(lemma_sent) > 0) and (len(form_sent) == len(lemma_sent)) and (set(form_sent) != set(["_"])):
            ndf = pd.DataFrame(
                [
                    [
                        "lemma",
                        lang,
                        " ".join(form_sent).replace("\t", " ").strip(),
                        " ".join(lemma_sent).replace("\t", " ").strip(),
                    ]
                ],
                columns=["prefix", "language", "input_text", "target_text"],
            )
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
