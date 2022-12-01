#!/bin/bash

opendistro_host=$OPENDISTRO_DNS_HOST
current_dir=`dirname $0`
export PATH=$PATH:/home/tkeir_svc/.nvm/versions/node/v14.17.5/bin
echo "Run elasticdump settings"
NODE_TLS_REJECT_UNAUTHORIZED=0 elasticdump --input=$current_dir/settings4test.json --output=https://admin:admin@$opendistro_host:9200/text-index-test --type=settings
echo "Run elasticdump mapping"
NODE_TLS_REJECT_UNAUTHORIZED=0 elasticdump --input=$current_dir/mapping4test.json --output=https://admin:admin@$opendistro_host:9200/text-index-test --type=mapping
echo "Run elasticdump data"
NODE_TLS_REJECT_UNAUTHORIZED=0 elasticdump --input=$current_dir/index4test.json --output=https://admin:admin@$opendistro_host:9200/text-index-test --type=data

