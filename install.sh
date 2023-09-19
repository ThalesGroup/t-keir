#!/bin/bash


##########################################################
# Author : Eric Blaudez
# Copyright (c) 2023 by THALES
# All right reserved.
# Description : install t-keir after pre-requisite filled
# parameter: 
# - project path : path to project installation 
# - model path
##########################################################
script_path=`dirname $0`
source_path=`realpath $script_path/tkeir`
pushd $source_path
workspace=$1

# test argument
if [ -z $workspace ]; then
    echo -ne "You you provice path where configuration and model will be installed"
    exit 1
fi

# create output directory 
# this directory will contains configuration files and resources (like models, lexical entries ...)
mkdir -p $workspace
if [ $? -ne 0 ]; then
    echo -ne "Cannot create directory '$workspace'"
    exit 1
fi

# prepare and install wheel
# suppress old package before
cd $source_path
rm -rf dist
echo -ne "Create python environment ...\n" 
python3 -m venv $workspace/tkeirenv

echo -ne "Build wheel ...\n"
poetry build
cd dist
whl=`ls *.whl` 

echo -ne "Install wheel ...\n"
source $workspace/tkeirenv/bin/activate
pip3 install $whl

tkeir-init-project -t $source_path/app/projects/template/ -o $workspace/
cd $source_path/app/bin
./init-models.sh $workspace/project/configs $workspace/project/model

echo "Download and install opensearch ..."
mkdir -p $workspace/thirdparty
cd $workspace/thirdparty
wget https://artifacts.opensearch.org/releases/bundle/opensearch/2.9.0/opensearch-2.9.0-linux-x64.tar.gz
tar xfz opensearch-2.9.0-linux-x64.tar.gz
cp $source_path/app/projects/template/resources/indices/opensearch.yml opensearch-2.9.0/config
cp $source_path/app/projects/template/resources/indices/jvm.options opensearch-2.9.0/config
cp $source_path/app/projects/template/resources/indices/run-opensearch.sh opensearch-2.9.0
