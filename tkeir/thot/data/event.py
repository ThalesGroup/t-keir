
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


def write_in_file(jsonl_f, output_f):
    json_lines = jsonl_f.read().split("\n")
    prepared_data = []
    for json_str in json_lines:
        try:
            json_data = json.loads(json_str)
            for evt in json_data["events"]:
                trigger_type = evt["type"]
                for mention in evt["mention"]:
                    sent_id = mention["sent_id"]
                    trigger = mention["trigger_word"]
                    offset = mention["offset"]
                    json_data["content"][sent_id]["triggers"] = ["_"] * len(json_data["content"][sent_id]["tokens"])
                    for i in range(offset[0], offset[1]):
                        json_data["content"][sent_id]["triggers"][i] = trigger_type
            prepared_data.append(json_data)
        except Exception as e:
            print(e)
    for json_data in prepared_data:
        for sent in json_data["content"]:
            if "triggers" in sent:
                output_f.write("event" + "\ten\t" + " ".join(sent["tokens"]) + "\t" + " ".join(sent["triggers"]) + "\n")


def main(args):
    train = []
    test = []
    dev = []
    for (dirpath, dirnames, filenames) in os.walk(args.input):
        for filename in filenames:
            if filename.endswith(".jsonl") and ("train" in filename.lower()):
                train.append(os.path.join(dirpath, filename))
            elif filename.endswith(".jsonl") and ("test" in filename.lower()):
                test.append(os.path.join(dirpath, filename))
            elif filename.endswith(".jsonl") and ("valid" in filename.lower()):
                dev.append(os.path.join(dirpath, filename))
    t5_train_f = open(args.output + "-train.tsv", "w", encoding="utf8")
    t5_train_f.write("prefix\tlanguage\tinput_text\ttarget_text\n")
    t5_test_f = open(args.output + "-test.tsv", "w", encoding="utf8")
    t5_test_f.write("prefix\tlanguage\tinput_text\ttarget_text\n")
    t5_dev_f = open(args.output + "-dev.tsv", "w", encoding="utf8")
    t5_dev_f.write("prefix\tlanguage\tinput_text\ttarget_text\n")
    train_files = tqdm(train)
    test_files = tqdm(test)
    dev_files = tqdm(dev)
    for file in train_files:
        with open(file, "r", encoding="utf-8") as jsonl_f:
            write_in_file(jsonl_f, t5_train_f)
            jsonl_f.close()
    t5_train_f.close()
    for file in test_files:
        with open(file, "r", encoding="utf-8") as jsonl_f:
            write_in_file(jsonl_f, t5_test_f)
            jsonl_f.close()
    t5_test_f.close()
    for file in dev_files:
        with open(file, "r", encoding="utf-8") as jsonl_f:
            write_in_file(jsonl_f, t5_dev_f)
            jsonl_f.close()
    t5_dev_f.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", default=None, type=str, help="Event directory")
    parser.add_argument("-o", "--output", default="./out", type=str, help="Event out prefix")
    main(parser.parse_args())
