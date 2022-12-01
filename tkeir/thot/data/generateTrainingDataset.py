
# -*- coding: utf-8 -*-
"""Data management and generation

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import os
import errno
import sys
import json
import argparse
import string
from tqdm import tqdm
from conllu import parse_incr
import pandas as pd


def main(args):
    config = None
    with open(args.config) as cfg_f:
        config = json.load(cfg_f)
        cfg_f.close()
    try:
        os.makedirs(args.output)
    except OSError as exc:
        if exc.errno != errno.EEXIST or (not os.path.isdir(args.output)):
            raise

    label_tasks = set(["relation", "event", "ner", "pos"])
    data_strat = {"relation": dict(), "event": dict(), "ner": dict(), "lemma": dict(), "svo": dict()}
    train_tab = []
    dev_tab = []
    test_tab = []
    for task in config["tasks"]:
        print("* load data from:", task)
        train_tab.append(
            pd.read_csv(
                os.path.join(args.input, config["tasks"][task]["datasets"]["train"]), sep="\t", encoding="utf-8", dtype=str
            )
            .dropna()
            .astype(str)
        )
        dev_tab.append(
            pd.read_csv(
                os.path.join(args.input, config["tasks"][task]["datasets"]["dev"]), sep="\t", encoding="utf-8", dtype=str
            )
            .dropna()
            .astype(str)
        )
        test_tab.append(
            pd.read_csv(
                os.path.join(args.input, config["tasks"][task]["datasets"]["test"]), sep="\t", encoding="utf-8", dtype=str
            )
            .dropna()
            .astype(str)
        )
    train_df = pd.concat(train_tab).sample(frac=1).reset_index()
    del train_tab
    dev_df = pd.concat(dev_tab).sample(frac=1).reset_index()
    del dev_tab
    test_df = pd.concat(test_tab).sample(frac=1).reset_index()
    del test_tab
    train_df.to_csv(
        os.path.join(args.output, "train.tsv"),
        index=False,
        sep="\t",
        encoding="utf-8",
        columns=["prefix", "input_text", "target_text"],
    )
    dev_df.to_csv(
        os.path.join(args.output, "dev.tsv"),
        index=False,
        sep="\t",
        encoding="utf-8",
        columns=["prefix", "input_text", "target_text"],
    )
    test_df.to_csv(
        os.path.join(args.output, "test.tsv"),
        index=False,
        sep="\t",
        encoding="utf-8",
        columns=["prefix", "input_text", "target_text"],
    )
    # stratify task according to language / labels
    for sample_i in range(len(train_df.values)):
        sample = train_df.values[sample_i]
        if sample[1] in data_strat:
            lang = sample[2]
            if sample[1] in label_tasks:
                if lang not in data_strat[sample[1]]:
                    data_strat[sample[1]][lang] = dict()
                sample_classes = set(sample[4].split(" "))
                for c in sample_classes:
                    try:
                        if c not in data_strat[sample[1]][lang]:
                            data_strat[sample[1]][lang][c] = []
                        data_strat[sample[1]][lang][c].append(sample_i)
                    except Exception as e:
                        import traceback

                        print(e, c, lang, sample[1], sample_i, type(data_strat[sample[1]][lang]), traceback.format_exc())
            else:
                if lang not in data_strat[sample[1]]:
                    data_strat[sample[1]][lang] = []
                data_strat[sample[1]][lang].append(sample_i)

    for sample_number in config["train-sample-per-task"]:
        try:
            os.makedirs(os.path.join(args.output, "xp-" + str(sample_number)))
        except OSError as exc:
            if exc.errno != errno.EEXIST or (not os.path.isdir(args.output)):
                raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default=None, type=str, help="model evaluation and generation file")
    parser.add_argument(
        "-i", "--input", default=None, type=str, help="input directory containing training/evaluation file in tsv format"
    )
    parser.add_argument("-o", "--output", default="./out", type=str, help="output directory")
    main(parser.parse_args())
