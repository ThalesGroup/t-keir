# Installation

These tools work on \*nix, WSL and docker environment.

## Pre-requist : prepare T-KEIR

* install git

```shell  title="Example under ubuntu"
#> sudo apt install git
```

* install poetry. Follow the instructions : [Poetry installation documentation](https://python-poetry.org/docs)

## Directory structure

* **app/bin**           : scripts and tools for server execution
* **app/projects**       : projects templates
* **doc**               : buildable documentation
* **runtimes/docker**   : docker environment
* **resources**         : contain testing resources & automatic index creation data
* **thot**              : tkeir source code


## Installation Prerequists

T-KEIR is a python software, **python 3.8** and **poetry** are necessary for an installation from gitlab/github.
Otherwise and from Thales environnement only, you can install by using pip command. The last way is to use docker

![Screenshot](resources/images/doc-tkeir-install-strategies.png)


To run the document go in directory **tkeir** and run mkdocs server:

```shell  title="Run the documentation server with mkdocs"
mkdocs serve
```

## Installation

After git repository cloning.
```shell  title="Build a python wheel package:"
#> poetry build
```

A wheel file will be created in "dist" directory. Then you can simply run a pip install on the created wheel.
Note that is highly recommanded to run wheel installation in a python virtual environment.

### Install from Wheel

You can directly install T-Keir from weel:

Go in "dist" folder (created by poetry)

```shell  title="Create a python virtual environement:"
#>  python3 -m venv <YOUR_ENV>`
```

```shell  title="Activate you environement:"
#> source <YOUR_ENV>/bin/activate
```

```shell  title="Install the Wheel:"
#> pip install <FILE_NAME>.whl
```

If there is a problem with **pycurl** install libcurl4-openssl-dev and libssl

```shell  title="E.G under debian/ubuntu:"
#> sudo apt install libcurl4-openssl-dev libssl-dev
```

### Build tkeir docker image

You could build the docker base image. This image contains os and python dependencies and code of search ai with one entry point
by service. The wheel package will be created, so you should ensure poetry is installed and in running path.

Go in **tkeir/runtimes/docker** directory and run the following command:

```shell 
#> ./builddocker.sh
```

### Configure the services

T-Keir provides a script to automatically generate configuration file:
```shell
#> python3 tkeir/thot/tkeir_init_project.py -t <PATH TO TKEIR>/tkeir/app/projects/template/ -o <PATH TO YOUR OUTPUT CONFIG DIR>
```

When you work with a docker you can use a share directory or a volume (to make configurer persistent).

```shell
#> docker run --rm -it -v <PATH TO YOUR SHARE DIRECTORY OR VOLUME NAME>:/home/tkeir_svc/share -w /home/tkeir_svc/tkeir --entrypoint python3 theresis/tkeir /home/tkeir_svc/tkeir/thot/tkeir_init_project.py -t /home/tkeir_svc/tkeir/app/projects/template -o /home/tkeir_svc/share
```

### Initialize/Load the models

When you build you docker volumes containing model and default configuration are automatically generated.
To update the configuration you can go into directory **app/bin** and run the command:
  
```shell
#> ./init-models.sh <PATH TO CONFIGURATION> <MODEL PATH>
```

Or from docker

```shell
#> docker run --rm -it -v $host_dir:$docker_dir -w /home/tkeir_svc/tkeir --entrypoint bash $tkeir_img /home/tkeir_svc/tkeir/app/bin/init-models.sh $docker_dir/project/configs $docker_dir/project/resources/modeling/net/
```

Where 

* **host_dir** is the variable containing the path to the shared host directory
* **docker_dir** is the variable containing the path to the shared docker directory
* **tkei_img** is the name of the image

Note, that the environment variable TRANSFORMERS_CACHE **HAVE TO BE** always set to model path before run a T-Keir service using models.

Take care of proxies. Please set correclty $HOME/.docker/config.json like that:

```json
  {
    "proxies":
    {
      "default":
      {
        "httpProxy": "your_http_proxy",
        "httpsProxy": "your_https_proxy",
        "noProxy": "your_no_proxy"
      }
    }
  }
```

For a docker compose network environment, don't forget to add **tkeir opendistro** hostname and all services in no_proxy.


### Configure environment variables

You need to configure some path in **".env"** file in directory docker

* ** TRANSFORMERS_CACHE ** : path to models
* ** OPENDISTRO_VERSION ** : version of opendistrop (1.12.0)
* ** OPENDISTRO_HOST ** : opendistro host (0.0.0.0)
* ** OPENDISTRO_DNS_HOST ** : dns host name of opendistro (generally used by client)
* ** OPENDISTRO_PORT ** : opendistro port (9200)
* ** TKEIR_DATA_PATH ** : the hosting path to the data that will be analyzed and indexed
* ** CONVERTER_PORT ** : converter service port
* ** TOKENIZER_PORT ** : tokenizer service port
* ** MSTAGGER_PORT ** : morphosyntactic service port
* ** NERTAGGER_PORT ** : named entities service port
* ** SYNTAXTAGGER_PORT ** : syntax and relation service port
* ** SENT_EMBEDDING_PORT ** : sentence embedding service port
* ** PIPELINE_PORT ** : tagging pipeline service port
* ** KEYWORD_PORT ** : keywords extraction service port
* ** AUTOMATIC_SUMMARY_PORT ** : automatic extractive summary port
* ** SENTIMENT_ANALYSIS_PORT ** : sentiment analysis service port
* ** CLASSIFICATION_PORT ** : unsupervised classification service port
* ** QA_PORT ** : question and answering service port
* ** CLUSTER_INFERENCE_HOST ** : semantic cluster inference port
* ** SEARCH_PORT ** : search service port
* ** TIKA_PORT ** : tika converter port
* ** INDEX_PORT ** : index service port
* ** WEB_PORT ** : web access port
* ** CONVERTER_HOST ** : converter service hostname or ip
* ** TOKENIZER_HOST ** : tokenizer service hostname or ip
* ** MSTAGGER_HOST ** : morpho syntactic tagger service hostname or ip
* ** NERTAGGER_HOST ** : named entities tagger service hostname or ip
* ** SYNTAXTAGGER_HOST ** : syntacic tagger and rule based svo extraction sevice hostname or ip
* ** SENT_EMBEDDING_HOST ** : sentience embedding sevice host name
* ** PIPELINE_HOST ** : tagger pipepline service host name
* ** KEYWORD_HOST ** : keyword extractor service hostname or ip
* ** AUTOMATIC_SUMMARY_HOST ** : automatic extractive service summary hostname or ip
* ** SENTIMENT_ANALYSIS_HOST ** : sentiment analysis service hostname or ip
* ** CLASSIFICATION_HOST ** : usupervised classification service hostname or ip
* ** QA_HOST ** : question and answering service hostname or ip
* ** CLUSTER_INFERENCE_HOST ** : semantic cluster inference host
* ** SEARCH_HOST ** : search service hostname or ip
* ** TIKA_HOST ** : tika converter host
* ** INDEX_HOST ** : indexing service hostname or ip
* ** WEB_HOST ** : web access service hostname or ip
* ** SEARCH_SSL ** : Search is in SSL model
* ** SEARCH_SSL_NO_VERIFY ** : no verify certificate
* ** TKEIR_SSL ** : \[True | False\], enable disable SSL even when SSL is specified in configuration file
* ** ALLOWED_HOSTS ** : django allowed host
* ** ES_MEMORY ** : Elastic search memory
* ** MODEL_PATH ** : path of models (huggingface)


## Copy or create data

T-Keir comes with default configuration file.
Nevertheless you can modify or add file. Most of them are configuration (see configuration section).

### Index mappings

Index mapping is store in **RESOURCES_DIRECTORY/indices/indices_mapping**. if you create new mapping it MUST contains the same fields.
You can freely change the analyzers.

### Resources

The resources are stored in **RESOURCES_DIRECTORY/modeling/tokenizer/\[en|fr...\]**. This directory contains file with list or csv tables.
The descriptions of these file are in **CONFIGS/annotation-resources.json**


# Quick start

![Screenshot](resources/images/doc-tkeir-quickstart-flow.png)


This section describes the step to create a full information retrieval engine.

## Run the installation part

Go in installation section and run it.
Do not forget to create your project configuration with "**tkeir_init_project.py**" and initialize the models with "**init-models.sh**". These steps allows to configure T-KEIR.

### Prepare T-KEIR and demo

You have to run the **installation**. It will set up configurations and models.

You have to edit the configuration files:

* **indexing.json** : change fields text-index, nms-index and relation-index by replacing "default-" by "drug-". Change elastic search host to "localhost" and set use-ssl to true.
* **search.json** : change field document-index-name by "drug-text-index". Change elastic search host to localhost.

Finaly, edit the file **tkeir/runtimes/docker/docker-compose-opendistro.yml** to change, if necessary, the path of the index.
By default it is **/data/index** the path have to be readable and writable for user running docker.
Then run

```shell
#> docker-compose -f docker-compose-opendistro.yml
```

Take care to the error display by opendistro, sometimes there is user rights issues.

For the demo, all is scripted, just go into **demos/quickstart/** and run or edit quickstart.sh

### Prepare you data

We propose to get an example dataset.
Create a temporary directory to store the data

```shell
wget https://archive.ics.uci.edu/ml/machine-learning-databases/00461/drugLib_raw.zip
unzip drugLib_raw.zip
```

Format tsv to csv:

```py linenums="1"
import pandas as pd
df = pd.read_csv("drugLibTrain_raw.tsv",sep="\t")
df.to_csv("data.csv",index=False)
df.columns
Index(['Unnamed: 0', 'urlDrugName', 'rating', 'effectiveness', 'sideEffects',
   'condition', 'benefitsReview', 'sideEffectsReview', 'commentsReview'],
  dtype='object')
```

Transform csv to "T-Keir" json files. Go into directory **tkeir/app/bin**

```shell
python3 csv2tkeir.py --input=<your data tmp>/data.csv \
                     --title=urlDrugName \
                     --content=benefitsReview,sideEffectsReview,commentsReview \
                     --kg=effectiveness,sideEffects,condition,rating \
                     --output=<your output directory>
```

### Analyse and index your document

T-Keir depends on Opendistro. We propose a docker compose file to pull and use Opendistro. For this demo, this part of software will be automatically run
in docker compose environement.
Do not forget to setup TRANSFORMERS_CACHE : path to models

To analyse and index document prepared in previous step, you have to run **batch_ingester.py** script from **tkeir** directory:

```shell
python3 thot/batch_ingester.py -c <PATH TO YOU CONFIGURATION FOLDER>/pipeline.json -i <PATH TO QUICKSTART FOLDER>/data/tkeir -o <PATH TO QUICKSTART FOLDER>/data/tkeir-out
```

After this process, all documents will be indexed. You can query Elastic Search with the following command:

```shell
curl -k https://admin:admin@localhost:9200/drug-text-index/_search | json_pp
```

### Run Search Service

Firstly run Q/A system:

```shell
python3 thot/qa_svc.py -c <PATH TO CONFIG>/qa.json
```

Check health:

```shell
curl http://localhost:10011/api/qa/health
```

Secondly run search service:

```shell
python3 thot/search_svc.py -c <PATH TO CONFIG>/search.json
```

Check health:

```shell
curl http://localhost:9000/api/searching/health
```

Finaly, on full version only (not available for OSS version) run web interface (in tkeir/thot/web/directory):

set path to web interface :

```shell
export WEB_TKEIR_APP=<PATH TO WEB DEMO>
```

```shell
python3 thot/web/manager.py runservice 0.0.0.0:8080 --insecure
```

To visualize a search request you can open firefox on http://<host of web server\>:8080/search



# Tools Overview

## Tkeir tools

TKeir tools is mostly a set of REST service, except Converter each service use generally as 'T-Keir' document
which store the extracted information (i.e. tokens, morphosyntax, named entities, syntax and SPO triples, semantic classes ...)

## How run the services

The services can be run a a same way:

```shell
python3 thot/<service_name>_svc.py -c service_config.json
```

## How use the services

There is two way to consume the service:

1. by developing your own access to the REST api
2. by using the python client

```shell
python3 thot/<service_name>_client.py -c service_config.json [client specific option] -s [http|https] -nsv
```

- -s option allows to select http scheme it should be http or https
- -nsv option allows to avoid ssl certificate verification

## Quick start / Docker compose

T-KEIR comes with ready to use docker compose. to run all services go in directory **runtime/docker**

```shell
docker-compose -f docker-compose-tkeir.yml up
```

## Quick start / Example service by service

Here we use all pre-configured service: the configuration environement is in  directory **app/projects/default/configs/\***.

### Converter

Converter is a tool allowing to convert different kind of document format to one compliant with **tkeir** tools.
This tools is a rest service where the API is described in **Tools  section**.

The available input format are:

- **raw** : a raw text format
- **email** : a mail format

To run the command type simply from tkeir directory:

```shell
python3 thot/converter_svc.py --config=/home/tkeir_svc/tkeir/configs/default/configs/converter.json
```

A light client can be run through the command

```shell
python3 thot/converter_client.py -c /home/tkeir_svc/tkeir/configs/default/configs/converter.json -t email -i /home/tkeir_svc/tkeir/thot/tests/data/test-raw/mail -o /home/tkeir_svc/tkeir/thot/tests/data/test-inputs/
```

### Tokenizer

The tokenizer is a tool allowing to tokenize "title" and "content" field of tkeir document.
This tools is a rest service where the API is described in **Tools  section**.

The available input format are:

- **raw** : a raw text format
- **email** : a mail format

To run the command type simply from tkeir directory:

```shell
python3 thot/tokenizer_svc.py --config=<path to tokenizer configuration file>
```

A light client can be run through the command

```shell
python3 thot/tokenizer_client.py --config=<path to tokenizer configuration file> --input=<input directory> --output=<output directory>
```

### Morphosyntactic tagger

The Morphosyntactic tagger is a tool allowing to extract Part Of Speech and lemma from "title_tokens" and "content_tokens" field of tkeir document.
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

```shell
python3 thot/mstagger_svc.py --config=<path to mstagger configuration file>
```

A light client can be run through the command

```shell
python3 thot/mstagger_client.py --config=<path to ms tagger configuration file> --input=<input directory> --output=<output directory>
```

### Named entity tagger

The Named entity tagger is a tool allowing to extract Named Entities from "title_tokens" and "content_tokens" field of tkeir document.
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

```shell
python3 thot/nertagger_svc.py --config=<path to ner configuration file>
```

A light client can be run through the command

```shell
python3 thot/nertagger_client.py --config=<path to ner tagger configuration file> --input=<input directory> --output=<output directory>
```

### Syntactic tagger and SVO Extraction

The syntactic tagger is a tool allowing to extract syntactic depencies and extract SVO.
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

```shell
python3 thot/syntactictagger_svc.py --config=<path to syntactic configuration file>
```

A light client can be run through the command

```shell
python3 thot/syntactictagger_client.py --config=<path to syntactic configuration file> --input=<input directory> --output=<output directory>
```

### Keyword Extraction

The keywords extractor is a tool allowing to extract keywords by using RAKE algoritms
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

```shell
python3 thot/keywordextractor_svc.py --config=<path to keywords configuration file>
```

A light client can be run through the command

```shell
python3 thot/keywordextractor_client.py --config=<path to keyword configuration file> --input=<input directory> --output=<output directory>
```

### Embbeding processing

The embeddings extraction is a tool allowing to extract embedding from "title_tokens" and "content_tokens", "ner", "svo" field of tkeir document.
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

```shell
python3 thot/embeddings_svc.py --config=<path to embeddings configuration file>
```

A light client can be run through the command

```shell
python3 thot/embeddings_client.py --config=<path to embeddings configuration file> --input=<input directory> --output=<output directory>
```

### Relation clustering

Relation clustering allows to create class on SVO extracted during the Syntactic tagging phase.

To run the command type simply from tkeir directory:

```shell
python3 thot/relation_clustering.py --config=<path to relation configuration file> -i <path to file with syntactic data extracted> -o <path to output folder>
```

There is also a service allowing inferencer according to a model computed with the previous command

To run the command type simply from tkeir directory:

```shell
python3 thot/clusterinfer_svc.py --config=<path to relation configuration file>
```

A light client can be run through the command

```shell
python3 thot/clusterinfer_client.py --config=<path to relation configuration file> --input=<input directory> --output=<output directory>
```

### Document classification

The document classification allows to classify document into user defined classes
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

```shell
python3 thot/zeroshotclassifier_svc.py --config=<path to configuration file>
```

A light client can be run through the command

```shell
python3 thot/zeroshotclassifier_client.py --config=<path to configuration file> --input=<input directory> --output=<output directory>
```

### Sentiment Analysis

The sentiment analsysis allows to classify document into 2 classes : POSITIVE and NEGATIVE
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

```shell
python3 thot/sentiment_svc.py --config=<path to configuration file>
```

A light client can be run through the command

```shell
python3 thot/sentiment_client.py --config=<path to configuration file> --input=<input directory> --output=<output directory>
```

### Document summary

The document summarizer allows to create a summary of document (by block of 500 words)
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

```shell
python3 thot/summarizer_svc.py --config=<path to configuration file>
```

A light client can be run through the command

```shell
python3 thot/summarizer_client.py --config=<path to configuration file> --input=<input directory> --output=<output directory> -m <min length> -M <max length>
```

### Document indexing

The document indexer allows to index a document
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

```shell
python3 thot/index_svc.py --config=<path to configuration file>
```

A light client can be run through the command

```shell
python3 thot/index_client.py --config=<path to configuration file> --input=<input directory>
```

Another way to index a directory is to use the tool tkeir2index
