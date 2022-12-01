#!/bin/bash
##############################################
# Author : Eric Blaudez
# Copyright (c) 2021 by THALES
# Description:
# Generate tarball of all tkeir volume
# to store model & project specific data
##############################################


for volume_i in `docker volume ls --format "{{.Name}}"| grep theresis_tkeir`; do
    echo "Dump Volume $volume_i"
    docker run --rm -v $volume_i:/volume -v /tmp:/backup alpine tar -cf /backup/$volume_i.tar -C /volume ./
done