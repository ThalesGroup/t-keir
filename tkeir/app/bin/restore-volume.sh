#!/bin/bash
##############################################
# Author : Eric Blaudez
# Copyright (c) 2021 by THALES
##############################################

if [ -d $1 ]; then
    data_path=$1
    docker volume rm volume_theresis_tkeir_converter
    docker volume rm volume_theresis_tkeir_tokenizer
    docker volume rm volume_theresis_tkeir_mstagger
    docker volume rm volume_theresis_tkeir_nertagger
    docker volume rm volume_theresis_tkeir_syntactictagger
    docker volume rm volume_theresis_tkeir_keywordextractor
    docker volume rm volume_theresis_tkeir_clustering
    docker volume rm volume_theresis_tkeir_qa
    docker volume rm volume_theresis_tkeir_zeroshotclassifier
    docker volume rm volume_theresis_tkeir_summarizer
    docker volume rm volume_theresis_tkeir_sentiment
    docker volume rm volume_theresis_tkeir_embeddings
    docker volume rm volume_theresis_tkeir_search
    docker volume rm volume_theresis_tkeir_tkeir2index
    docker volume rm volume_theresis_tkeir_full

    docker volume create volume_theresis_tkeir_converter
    docker volume create volume_theresis_tkeir_tokenizer
    docker volume create volume_theresis_tkeir_mstagger
    docker volume create volume_theresis_tkeir_nertagger
    docker volume create volume_theresis_tkeir_syntactictagger
    docker volume create volume_theresis_tkeir_keywordextractor
    docker volume create volume_theresis_tkeir_clustering
    docker volume create volume_theresis_tkeir_qa
    docker volume create volume_theresis_tkeir_zeroshotclassifier
    docker volume create volume_theresis_tkeir_summarizer
    docker volume create volume_theresis_tkeir_sentiment
    docker volume create volume_theresis_tkeir_embeddings
    docker volume create volume_theresis_tkeir_search
    docker volume create volume_theresis_tkeir_tkeir2index
    docker volume create volume_theresis_tkeir_full
    for volume_i in `docker volume ls --format "{{.Name}}"| grep theresis_tkeir`; do        
        docker run --rm -v $volume_i:/volume -v $data_path:/backup alpine sh -c "rm -rf /volume/* /volume/..?* /volume/.[!.]* ; tar -C /volume/ -xf /backup/$volume_i.tar"
    done

fi