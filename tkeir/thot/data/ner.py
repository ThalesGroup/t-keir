
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
from sklearn.model_selection import train_test_split


def write_in_file(data, output_f, lang):
    for d in data:
        toks = d.split()
        sent = []
        ner_sent = []
        for tok in toks:
            item = tok.split("|")
            ner = "_"
            if len(item) == 3:
                iner = item[2]
                if iner.lower() != "o" and ("misc" not in iner.lower()):
                    bpe = iner.split("-")
                    if len(bpe) == 2:
                        ner = bpe[1]
                    else:
                        ner = iner
                    ner = ner+":"+item[0]
                sent.append(item[0])
                
        output_f.write("ner\t" + lang + "\t[0,"+ str(len(sent))+"]\t" + " ".join(sent) + "\t" + " ".join(ner_sent) + "\n")


def main(args):
    ner_files = []
    for (dirpath, dirnames, filenames) in os.walk(args.input):
        for filename in filenames:
            ner_files.append(os.path.join(dirpath, filename))

    t5_train_f = open(args.output + "-train.tsv", "w", encoding="utf-8")
    t5_train_f.write("prefix\tlanguage\tposition\tinput_text\ttarget_text\n")
    t5_test_f = open(args.output + "-test.tsv", "w", encoding="utf-8")
    t5_test_f.write("prefix\tlanguage\tposition\tinput_text\ttarget_text\n")
    t5_dev_f = open(args.output + "-dev.tsv", "w", encoding="utf-8")
    t5_dev_f.write("prefix\tlanguage\tposition\tinput_text\ttarget_text\n")

    for file in ner_files:
        lang = file.split("/")[-1].split("-")[2]
        with open(file, "r", encoding="utf-8") as aij_f:
            data = aij_f.read().split("\n")
            aij_f.close()
            dataset = []
            for sentence in data:
                s = sentence.strip()
                if s:
                    toks = s.split()
                    if len(toks) > 0:
                        dataset.append(sentence)

            train, test = train_test_split(dataset, test_size=0.33, random_state=42)
            test, dev = train_test_split(test, test_size=0.33, random_state=42)
            train_data = tqdm(train)
            test_data = tqdm(test)
            dev_data = tqdm(dev)
            write_in_file(train_data, t5_train_f, lang)
            write_in_file(test_data, t5_test_f, lang)
            write_in_file(dev_data, t5_dev_f, lang)
    t5_train_f.close()
    t5_test_f.close()
    t5_dev_f.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", default=None, type=str, help="UD framework directory")
    parser.add_argument("-o", "--output", default="./out", type=str, help="UD framework directory")
    main(parser.parse_args())
