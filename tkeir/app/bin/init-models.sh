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

resources_en=$source_path/resources/modeling/tokenizer/en
uv run --python 3.11 tkeir-create-annotation-resource \
    --entries-file $resources_en/annotation-resources.json \
    --output $resources_en/tkeir_mwe.pkl
