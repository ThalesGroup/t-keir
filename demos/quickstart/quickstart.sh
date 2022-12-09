#!/bin/bash
######################################################
# Author : Eric Blaudez
# Copyright (c) 2022 by THALES
# All right reserved.
# Description : create a demonstrator
#######################################################

script_path=`dirname $0`
script_path=`realpath $script_path`
bin_path=`realpath $script_path/../../tkeir/app/bin`
service_path=`realpath $script_path/../../tkeir/`

usage() {
    echo -ne "quickstart.sh <configuration path>\n";
    exit 1;
}

if [ $# -ne 1 ]; then
    usage;
fi

config_path=$1


echo "* download data and do CSV"
pushd $script_path
mkdir -p data/raw
mkdir -p data/tkeir
pushd data
pushd raw

wget https://archive.ics.uci.edu/ml/machine-learning-databases/00461/drugLib_raw.zip
unzip drugLib_raw.zip
python3 $script_path/generateCSV.py

popd
echo "* Generate T-Keir file"
python3 $bin_path/csv2tkeir.py --input=$script_path/data/raw/data.csv \
                         --title=urlDrugName \
                         --content=benefitsReview,sideEffectsReview,commentsReview \
                         --kg=effectiveness,sideEffects,condition,rating \
                         --output=$script_path/data/tkeir

popd
popd
popd
pushd $service_path
tkeir-batch-ingester -c $config_path/pipeline.json -i $script_path/data/tkeir -o $script_path/data/tkeir-out 
