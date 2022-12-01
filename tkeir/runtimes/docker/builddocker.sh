#!/bin/bash
##################################
# Author : Eric Blaudez
# Copyright (c) 2022 by THALES SIX
# All right reserved.
# Description:
# build search ai docker container
##################################

no_vol=$1
script_path=`dirname $0`
script_path=`realpath $script_path`
echo $script_path
cd $script_path
cd ../../../

poetry build
cp -r dist tkeir
cd tkeir
docker build -f runtimes/docker/tkeir/Dockerfile.tkeir-base.prod . -t theresis/tkeir
