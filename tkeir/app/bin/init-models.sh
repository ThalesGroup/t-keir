#!/bin/bash
######################################################
# Author : Eric Blaudez
# Copyright (c) 2022 by THALES
# All right reserved.
# Description : download/install models
# parameter: 
# - configuration path : path of confiugration path 
# - model path
#######################################################
script_path=`dirname $0`
source_path=`realpath $script_path/../../`
pushd $source_path

usage() {
    echo -ne "init-models.sh <configuration path> <model path>\n";
    exit 1;
}

if [ $# -ne 2 ]; then
    usage;
fi

export config_path=$1
export MODEL_PATH=$2
export TRANSFORMERS_CACHE=$2

python3 thot/tokenizer_svc.py -c $config_path/tokenizer.json --init
python3 thot/embeddings_svc.py -c $config_path/embeddings.json --init                    
python3 thot/zeroshotclassifier_svc.py -c $config_path/zeroshotclassifier.json --init
python3 thot/sentiment_svc.py -c $config_path/sentiment.json --init
python3 thot/qa_svc.py -c $config_path/qa.json --init
python3 thot/summarizer_svc.py -c $config_path/summarizer.json --init