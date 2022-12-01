#!/bin/bash
##############################################
# Author : Eric Blaudez
# Copyright (c) 2021 by THALES
# Description dump es host
# parameter: hostname of E.S.
##############################################

es_host=localhost

if [ $1 ]; 
then
 es_host=$1
fi

echo "Dump $es_host"

NODE_TLS_REJECT_UNAUTHORIZED=0 elasticdump --input=https://$es_host:9200/default-text-index --type=settings --output=default-text-index.settings.json
NODE_TLS_REJECT_UNAUTHORIZED=0 elasticdump --input=https://$es_host:9200/default-text-index --type=mapping --output=default-text-index.mapping.json
NODE_TLS_REJECT_UNAUTHORIZED=0 elasticdump --input=https://$es_host:9200/default-text-index --type=data --output=default-text-index.data.json
