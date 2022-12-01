#!/bin/bash
######################################################
# Author : Eric Blaudez
# Copyright (c) 2021 by THALES
# Description : manae volume and project
# parameter: 
# - init-project[-no-cuda] : initialize data of project
#   project [ai4eu|axeleria|default|enronmail|stairwai]
#   contains specific data
#######################################################
script_path=`dirname $0`



usage() {
    echo -ne "manager.sh [init-project|overload]\n";
    exit 1;
}

if [ $# -le 1 ]; then
    usage;
fi

if [ $1 == "init-project" ]; then
    if [ $# -ne 2 ]; then
        usage;
    fi    
    project_path=`realpath $script_path/../projects`
    source_path=`realpath $script_path/../../`
    pushd $source_path

    for volume_i in `docker volume ls --format "{{.Name}}"| grep theresis_tkeir`; do
        service_name=`echo $i | sed -e 's/volume_theresis_tkeir_'//`
        config_path="app/projects/default/configs"
        echo "current path: $PWD"
        echo "**** Create volume $volume_i directories"
        docker run --rm -v $volume_i:/data -w /source busybox rm -rf /data/projects
        docker run --rm -v $volume_i:/data -w /source busybox rm -rf /data/bin
        docker run --rm -v $volume_i:/data -w /source busybox mkdir -p /data/projects
        docker run --rm -v $volume_i:/data -w /source busybox mkdir -p /data/models
        echo "**** Copy configuration $source_path/app/projects/$2 to $volume_i"
        docker run --rm -v $source_path:/source -v $volume_i:/data -w /source busybox cp -r /source/app/projects/$2 /data/projects/default
        echo "**** Copy scripts and entry point"
        docker run --rm -v $source_path:/source -v $volume_i:/data -w /source busybox cp -r /source/app/bin /data/
        docker run --rm -v $source_path:/source -v $volume_i:/data -w /source busybox cp -r /source/app/ssl /data/
        docker run --rm -v $volume_i:/data busybox chown -R 1000.1000 /data

        echo "**** Start Initialization of docker volumes"
        if [ $volume_i == "volume_theresis_tkeir_clustering" ]; then
            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/embeddings_svc.py -c $config_path/embeddings.json --init
        elif [ $volume_i == "volume_theresis_tkeir_converter" ]; then
            echo "converter does not need initialization" 
        elif [ $volume_i == "volume_theresis_tkeir_embeddings" ]; then
            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/embeddings_svc.py -c $config_path/embeddings.json --init
        elif [ $volume_i == "volume_theresis_tkeir_keywordextractor" ]; then
            echo "Initializer tokenizer model for keywords"
            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/tokenizer_svc.py -c $config_path/tokenizer.json --init
        elif [ $volume_i == "volume_theresis_tkeir_mstagger" ]; then
            echo "mstagger does not need initialization"
        elif [ $volume_i == "volume_theresis_tkeir_nertagger" ]; then
            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/tokenizer_svc.py -c $config_path/tokenizer.json --init        
        elif [ $volume_i == "volume_theresis_tkeir_clusterinfer" ]; then
            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/embeddings_svc.py -c $config_path/embeddings.json --init
        elif [ $volume_i == "volume_theresis_tkeir_qa" ]; then
            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/qa_svc.py -c $config_path/qa.json --init
        elif [ $volume_i == "volume_theresis_tkeir_search" ]; then
            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/tokenizer_svc.py -c $config_path/tokenizer.json --init;
            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/embeddings_svc.py -c $config_path/embeddings.json --init
        elif [ $volume_i == "volume_theresis_tkeir_tkeir2index" ]; then
            echo "tkeir2index does not need initialization"
        elif [ $volume_i == "volume_theresis_tkeir_sentiment" ]; then            
            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/sentiment_svc.py -c $config_path/sentiment.json --init
        elif [ $volume_i == "volume_theresis_tkeir_summarizer" ]; then
            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/summarizer_svc.py -c $config_path/summarizer.json --init
        elif [ $volume_i == "volume_theresis_tkeir_syntactictagger" ]; then
            echo "Initializer tokenizer model for syntactictagger"
            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/tokenizer_svc.py -c $config_path/tokenizer.json --init
        elif [ $volume_i == "volume_theresis_tkeir_tokenizer" ]; then
            echo "Initializer tokenizer model"
            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/tokenizer_svc.py -c $config_path/tokenizer.json --init
        elif [ $volume_i == "volume_theresis_tkeir_zeroshotclassifier" ]; then
            docker run --rm -it  \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/zeroshotclassifier_svc.py -c $config_path/zeroshotclassifier.json --init
        elif [ $volume_i == "volume_theresis_tkeir_full" ]; then

            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/tokenizer_svc.py -c $config_path/tokenizer.json --init

            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/embeddings_svc.py -c $config_path/embeddings.json --init                    

            docker run --rm -it  \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/zeroshotclassifier_svc.py -c $config_path/zeroshotclassifier.json --init

            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/sentiment_svc.py -c $config_path/sentiment.json --init

            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/qa_svc.py -c $config_path/qa.json --init

            docker run --rm -it \
                    -v $volume_i:/home/tkeir_svc/tkeir/app \
                    -w /home/tkeir_svc/tkeir \
                    --entrypoint python3 \
                    theresis/tkeir \
                    thot/summarizer_svc.py -c $config_path/summarizer.json --init        
        fi
        docker run --rm -v $volume_i:/data busybox chown -R 1000.1000 /data
    done
fi

if [ $1 == "overload" ]; then
    if [ $# -ne 2 ]; then
        usage;
    fi    
    project_path=`realpath $script_path/../projects`
    source_path=`realpath $script_path/../../`
    searchsvc_path=`realpath $script_path/../../../`
    pushd $source_path

    for volume_i in `docker volume ls --format "{{.Name}}"| grep theresis_tkeir`; do
        service_name=`echo $i | sed -e 's/volume_theresis_tkeir_'//`
        config_path=app/projects/$2/configs
        echo "current path: $PWD"
        echo "**** Copy configuration $source_path/app/projects/$2 to $volume_i"
        docker run --rm -v $volume_i:/data -w /source busybox rm -rf /data/projects/default/config
        docker run --rm -v $volume_i:/data -w /source busybox rm -rf /data/bin
        docker run --rm -v $volume_i:/data -w /source busybox mkdir -p /data/projects/default
        docker run --rm -v $volume_i:/data -w /source busybox mkdir -p /data/models
        docker run --rm -v $source_path:/source -v $volume_i:/data -w /source busybox cp -r /source/app/projects/$2/default/config /data/projects/default/config
        echo "**** Copy scripts and entry point"
        docker run --rm -v $source_path:/source -v $volume_i:/data -w /source busybox cp -r /source/app/bin /data/
        docker run --rm -v $source_path:/source -v $volume_i:/data -w /source busybox cp -r /source/app/ssl /data/
        docker run --rm -v $volume_i:/data busybox chown -R 1000.1000 /data
    done
    popd
    # copy new code source
    echo "Copy source to theresis/tkeir"
    pushd $searchsvc_path
    echo "Mr Proper"
    docker stop working_tkeir
    docker rm working_tkeir
    echo "Run container"
    docker run -d --name working_tkeir --entrypoint=/home/tkeir_svc/tkeir/app/bin/wait_no_close.sh theresis/tkeir    
    echo "Copy and mark to load container"
    docker cp tkeir working_tkeir:/home/tkeir_svc
    docker exec -u0 -ti working_tkeir /bin/chown -R 1000.1000 /home/tkeir_svc/tkeir
    echo "Overload date:" > tkeir/overload.info
    date > tkeir/overload.info
    echo "Commit content"
    docker commit working_tkeir theresis/tkeir-copy
    docker stop working_tkeir
    docker rm working_tkeir
    check_image=`docker image list | grep theresis/tkeir-copy`
    echo "Check Image: $check_image"
    if [ ! -z "$check_image" ]; then
        echo "Remove old image"
        docker image rm theresis/tkeir
        echo "Remove tag new image"
        docker tag theresis/tkeir-copy theresis/tkeir
        check_image=`docker image list | grep theresis/tkeir`
        echo "check cuda image:$check_image"
        if [ ! -z "$check_image" ]; then

            docker rmi theresis/tkeir-copy
            #docker image rm theresis/tkeir-copy
        else
            echo "Error with tag"
        fi
    else
        echo "Error with commit"
    fi
    popd    
fi


