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

elasticdump --input=http://$es_host:9200/text-index --type=settings --output=text-index.settings.json
elasticdump --input=http://$es_host:9200/text-index --type=mapping --output=text-index.mapping.json
elasticdump --input=http://$es_host:9200/text-index --type=data --output=text-index.data.json
