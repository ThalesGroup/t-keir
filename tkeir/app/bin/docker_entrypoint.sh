#!/bin/bash
############################################################################################################
# Author : Eric Blaudez
# Copyright (c) 2019 by THALES
# Description:
# docker entry point allows to run command in tkeir docker
#
# VIA docker:
#   $>docker run -it --entrypoint /home/tkeir_svc/tkeir/app/bin/entrypoint.sh <entry point command>
#
# VIA docker-compose
# ...
   #entrypoint: [/home/tkeir_svc/tkeir/app/bin/docker_entrypoint.sh, <entry point command>]
# ...
#
# Entry point commands:
# * init     : initialize directories and models
# * *_svc    : run services
# * init_*_svc    : run service initialization (to stroe model in volumes)
# * tests    : run tests
# * web      : run web interface
############################################################################################################

# Go up on file directory & prepare monitor
cd `dirname $0`
current_path=`dirname $0`
echo "Proxy:"
echo "------"
echo "http:$HTTP_PROXY"
echo "https:$HTTPS_PROXY"
echo "no:$NO_PROXY"

start_svc() {
    script_name=$1
    pushd /home/tkeir_svc/tkeir
    echo "Script name:$script_name"
    config_name=""
    if [ $script_name == "converter" ]; then
        config_name="converter.json"
    elif [ $script_name == "tokenizer" ]; then
        config_name="tokenizer.json"
    elif [ $script_name == "mstagger" ]; then
        config_name="mstagger.json"
    elif [ $script_name == "nertagger" ]; then
        config_name="nertagger.json"
    elif [ $script_name == "syntactictagger" ]; then
        config_name="syntactic-tagger.json"
    elif [ $script_name == "keywordextractor" ]; then
        config_name="keywords.json"
    elif [ $script_name == "zeroshotclassifier" ]; then
        config_name="zeroshotclassifier.json"
    elif [ $script_name == "clusterinfer" ]; then
        config_name="relations.json"
    elif [ $script_name == "qa" ]; then
        config_name="qa.json"
    elif [ $script_name == "embeddings" ]; then
        config_name="embeddings.json"
    elif [ $script_name == "summarizer" ]; then
        config_name="summarizer.json"
    elif [ $script_name == "sentiment" ]; then
        config_name="sentiment.json"
    elif [ $script_name == "search" ]; then
        config_name="search.json"
	    pip3 install -r  /home/tkeir_svc/searx/requirements.txt
        pushd /home/tkeir_svc/searx/searx
        python3 webapp.py &
        popd
    elif [ $script_name == "index" ]; then
        config_name="indexing.json"    
    elif [ $script_name == "pipeline" ]; then
        config_name="pipeline.json"
    fi
    python3 thot/$1_svc.py -c /home/tkeir_svc/tkeir/app/projects/default/configs/$config_name
}

init_svc() {
    script_name=`echo $1 | sed -e 's/init_//'`
    pushd /home/tkeir_svc/tkeir
    config_name=""
    if [ $script_name == "converter" ]; then
        config_name="converter.json"
    elif [ $script_name == "tokenizer" ]; then
        config_name="tokenizer.json"
    elif [ $script_name == "mstagger" ]; then
        config_name="mstagger.json"
    elif [ $script_name == "nertagger" ]; then
        config_name="nertagger.json"
    elif [ $script_name == "syntactictagger" ]; then
        config_name="syntactic-tagger.json"
    elif [ $script_name == "keywordextractor" ]; then
        config_name="keywords.json"
    elif [ $script_name == "zeroshotclassifier" ]; then
        config_name="zeroshotclassifier.json"
    elif [ $script_name == "clusterinfer" ]; then
        config_name="relations.json"
    elif [ $script_name == "qa" ]; then
        config_name="qa.json"
    elif [ $script_name == "embeddings" ]; then
        config_name="embeddings.json"
    elif [ $script_name == "summarizer" ]; then
        config_name="summarizer.json"
    elif [ $script_name == "sentiment" ]; then
        config_name="sentiment.json"
    elif [ $script_name == "search" ]; then
        config_name="search.json"        
        pushd /home/tkeir_svc/searx/searx
        python3 webapp.py &
        popd
    elif [ $script_name == "index" ]; then
        config_name="indexing.json"        
    elif [ $script_name == "pipeline" ]; then
        config_name="pipeline.json"
    fi
    python3 thot/$script_name\_svc.py -c /home/tkeir_svc/tkeir/app/projects/default/configs/$config_name --init
}

start_indexing() {
    # /from_host_data/ and /from_host_data2/ are shared with -v argument of docker
    pushd /home/tkeir_svc/tkeir
    python3 thot/tkeir2index.py -t document -c /from_host_data/indexing.json -d /from_host_data2/ 
}

start_shell() {
    /home/tkeir_svc/tkeir/app/bin/wait_no_close.sh
}

start_web() {
    pushd /home/tkeir_svc/tkeir/thot/web
    export WEB_TKEIR_APP=/home/tkeir_svc/tkeir/app/projects/default/web
    echo "Web path:$WEB_TKEIR_APP"
    python3 manage.py runserver 0.0.0.0:$WEB_PORT --insecure
}

start_jupyter() {
    pushd /home/tkeir_svc/
    jupiter-lab
}


start_test() {
    pushd /home/tkeir_svc/tkeir/thot/tests
    ./TestSuite.sh
    exit $?
}


case "$1" in
    init_tokenizer|init_classifier|init_qa|init_sentiment|init_summarizer|init_embeddings|init_zeroshotclassifier) init_svc $1;;
    converter|tokenizer|mstagger|nertagger|syntactictagger|keywordextractor|zeroshotclassifier|clusterinfer|qa|embeddings|summarizer|sentiment|search|index|pipeline) start_svc $1;;
    indexing) start_indexing;;
    web) start_web;;
    jupyter) start_jupyter;;
    shell)   start_shell;;
    test)   start_test;;
    *) echo "usage: $0 converter|tokenizer|mstagger|nertagger|syntactictagger|keywords|zeroshotclassifier|search|indexer|qa|sentiment|summarizer|embeddings|clusterinfer|shell" >&2
       echo "usage: $0 init_tokenizer|init_qa|init_sentiment|init_summarizer|init_embeddings|init_zeroshotclassifier" >&2
       echo "usage: $0 test" >&2
       exit 1
       ;;
esac
