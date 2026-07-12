#!/bin/bash

opendistro_host=$OPENDISTRO_DNS_HOST
current_dir=`dirname $0`
export PATH=$PATH:/home/tkeir_svc/.nvm/versions/node/v14.17.5/bin
echo "Run destroy"
curl -k -XDELETE https://admin:admin@$opendistro_host:9200/text-index-test

