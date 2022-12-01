# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
from lib2to3.pgen2.tokenize import generate_tokens
import os
import sys
import argparse
import json
from tqdm import tqdm
import shutil 

dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "../")))
sys.path.insert(0, os.path.abspath(os.path.join(dir_path, "./")))
from jinja2 import Environment, FileSystemLoader

from thot import __author__, __copyright__, __credits__, __maintainer__, __email__, __status__
from thot.core.ThotLogger import ThotLogger



project={
    "path":os.path.abspath("./tkeir/project"),
    "data":os.path.abspath("./tkeir/data"),
    "loglevel":"info"
}

class Project:

    def __init__(self, path="./tkeir/project", data="./tkeir/data",loglevel="info"):

        self.path = path
        self.data = data
        self.loglevel = loglevel

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--template", default=None, type=str, help="template directory")
    parser.add_argument("-o", "--output", default=None, type=str, help="output project directory")
    args = parser.parse_args()
    ThotLogger.loads()
    project=Project()
    if not args.template:
        ThotLogger.error("template directory is mandatory.")
        sys.exit(-1)
    if args.output:
        project.path = os.path.abspath(os.path.join(args.output,"project"))
        project.data = os.path.abspath(os.path.join(args.output,"data"))
    jinja2_env = Environment(loader=FileSystemLoader(os.path.join(project.path,"configs")))
    shutil.copytree(args.template,project.path)
    file_list = []
    for (dirpath, dirnames, filenames) in os.walk(os.path.join(project.path,"configs")):
        for filename in filenames:
            if filename.endswith(".json"):
                file_list.append(filename)
    input_files = tqdm(file_list)
    for f in input_files:
        template = jinja2_env.get_template(f)
        generated_file = template.render(project=project)
        with open(os.path.join(os.path.join(project.path,"configs"), f), "w", encoding="utf-8") as output_f:
            output_f.write(generated_file)
            output_f.close()
    file_list=[]
    for (dirpath, dirnames, filenames) in os.walk(os.path.join(project.path,"resources/modeling/tokenizer/en")):
        for filename in filenames:
            if filename.endswith(".json"):
                file_list.append(filename)
    input_files = tqdm(file_list)
    for f in input_files:
        try:
            template = jinja2_env.get_template(f)
            generated_file = template.render(project=project)
        except:
            with open(os.path.join(os.path.join(project.path,"resources/modeling/tokenizer/en"), f)) as cf:
                print("Read "+f)
                generated_file=cf.read()
                cf.close()
        with open(os.path.join(os.path.join(project.path,"resources/modeling/tokenizer/en"), f), "w", encoding="utf-8") as output_f:
            output_f.write(generated_file)
            output_f.close()
        

if __name__ == "__main__":
    main()
