******
T-KEIR 
******

T-KEIR is set of services developped by Theresis.
The T-KEIR tools allows to apply numerous NLP tools, search, index and classify. The tools cover

  * advanced tokenizer configuration
  * named entities with validations rules
  * keywords extraction
  * SVO based on syntactic dependencies and rules
  * automatic summarization
  * sentiment analysis
  * unsupervised classification
  * relation clustering
  * question and answering
  * advanced query formulation and expansion based on clustering and text analysis


These tools work on *nix and docker environment.

Directory structure
===================

* **app/bin**            : scripts and tools for server execution
* **app/projects**       : template projects configuration and resources
* **doc**                : buildable documentation
* **runtimes/docker**    : docker environment
* **runtimes/k8s**       : minikube environment
* **resources**          : contain testing resources & automatic index creation data
* **thot**               : tkeir source code

Installation
************

The installation is hightly dockerized. 
The full documentation is available on https://t-keir.pages.thalesdigital.io/theresisnlp/


Prerequists
===========

The only prerequists is container envrionments:

* docker (19.03) and docker compose (1.27)
* python >=3.7
* poetry

To build the documentation the tools sphinx-doc is required. To build it goes in doc directory and type

:code:`#> builddoc.sh`

Container environment setup
===========================

Build tkeir docker image
----------------------------


You should build the docker base image. This image contains os and python dependencies and code of search ai with on entry point by service :  

* \*_svc : the services
* shell : run sleep loop. It allows interactive use of tools (useful for develop, debugging and testing)
* tests : run services tests

Go in docker directory and run the following command:
  
  :code:`#> ./builddocker.sh`

These builder will create docker volumes :
  * one docker volume per service : containing only the necessary data in term of model and resources
  * one test docker volume : containing all models and all resources (useful for dev and "shell" mode describe below)


Configure docker compose and directory paths
--------------------------------------------

You need to configure some path in **".env"** file in directory docker

* OPENDISTRO_VERSION : version of opendistrop (1.12.0)
* OPENDISTRO_HOST : opendistro host (0.0.0.0)
* OPENDISTRO_DNS_HOST : dns host name of opendistro (generally used by client)
* OPENDISTRO_PORT : opendistro port (9200)
* OPENDISTRO_USE_SSL : opendistro use ssl
* OPENDISTRO_VERIFY_CERTS : verify ssl certificate of opendistro
* OPENDISTRO_USER / OPENDISTRO_PASWWORD : login password of opendistro user
* CONVERTER_PORT : converter service port
* TOKENIZER_PORT : tokenizer service port
* MSTAGGER_PORT : morphosyntactic service port
* NERTAGGER_PORT : named entities service port
* SYNTAXTAGGER_PORT : syntax and relation service port
* SENT_EMBEDDING_PORT : sentence embedding service port
* PIPELINE_PORT  : tagging pipeline service port
* KEYWORD_PORT : keywords extraction service port
* AUTOMATIC_SUMMARY_PORT : automatic extractive summary port
* SENTIMENT_ANALYSIS_PORT : sentiment analysis service port
* CLASSIFICATION_PORT : unsupervised classification service port
* QA_PORT : question and answering service port
* CLUSTER_INFERENCE_PORT : semantic cluster inference port
* SEARCH_PORT : search service port
* INDEX_PORT : index service port
* TIKA_PORT: tika converter port
* WEB_PORT : web access port
* CONVERTER_HOST : converter service hostname or ip
* TOKENIZER_HOST : tokenizer service hostname or ip
* MSTAGGER_HOST : morpho syntactic tagger service hostname or ip
* NERTAGGER_HOST : named entities tagger service hostname or ip
* SYNTAXTAGGER_HOST : syntacic tagger and rule based svo extraction sevice hostname or ip
* SENT_EMBEDDING_HOST : sentience embedding sevice host name
* PIPELINE_HOST : tagger pipepline service host name
* KEYWORD_HOST : keyword extractor service hostname or ip
* AUTOMATIC_SUMMARY_HOST : automatic extractive service summary hostname or ip
* SENTIMENT_ANALYSIS_HOST : sentiment analysis service hostname or ip
* CLASSIFICATION_HOST : usupervised classification service hostname or ip
* QA_HOST : question and answering service hostname or ip
* CLUSTER_INFERENCE_HOST : semantic cluster inference host
* SEARCH_HOST : search service hostname or ip
* TIKA_HOST: tika converter host
* INDEX_HOST : indexing service hostname or ip
* WEB_HOST : web access service hostname or ip
* SEARCH_SSL=Search is in SSL model
* SEARCH_SSL_NO_VERIFY : no verify certificate
* ALLOWED_HOSTS: django allowed host
* ES_MEMORY : Elastic search memory

Notice the environment variable are not fixed in hard, you can easily change their names through configuration files

Copy or create data
===================

T-Keir comes with default configuration file. 

Index mappings
--------------

Index mapping is store in **TKEIR_PATH/resources/indices/indices_mapping**. if you create new mapping it MUST contains the same fields.
You can freely change the analyzers.

Resources
---------

The defaults resources are stored in **TKEIR_PATH/app/projects/(defaults,ai4eu,enronmail,...)/resources/modeling/tokenizer/[en|fr...]**. This directory contains file with list or csv tables.
The descriptions of these file are in **annotation-resources.json**.

Initialize with docker
======================

Take care of proxies. Please set correclty $HOME/.docker/config.json like that:

.. code-block:: json

  {
    "proxies":
    {
      "default":
      {
        "httpProxy": "your_http_proxy",
        "httpsProxy": "your_https_proxy",
        "noProxy": "your_no_proxy,tkeir_opendistro"
      }
    }
  }

Don't forget to add **tkeir_opendistro** in no_proxy (for docker environment)


Usage
=====


Shell "mode" allows to run all services manually, it is generally used during the development. Go in directory **runtimes/docker** and type:

  :code:`#> docker-compose -f docker-compose-shell.yml up`

To run all services services manually, it is generally used during the development. Go in directory **runtimes/docker** and type:

  :code:`#> docker-compose -f docker-compose-tkeir.yml up`


Converter
---------

Converter is a tool allowing to convert different kind of document format to one compliant with **tkeir** tools.
This tools is a rest service where the API is described in **Tools  section**.

The available input format are:

* **raw** : a raw text format
* **email** : a mail format

To run the command type simply from tkeir directory:

.. code-block:: shell 
  
  python3 thot/converter_svc.py --config=/home/tkeir_svc/tkeir/configs/default/configs/converter.json

A light client can be run through the command

.. code-block:: shell 
  
  python3 thot/converter_client.py -c /home/tkeir_svc/tkeir/configs/default/configs/converter.json -t email -i /home/tkeir_svc/tkeir/thot/tests/data/test-raw/mail -o /home/tkeir_svc/tkeir/thot/tests/data/test-inputs/ 


Tokenizer
---------

The tokenizer is a tool allowing to tokenize "title" and "content" field of tkeir document.
This tools is a rest service where the API is described in **Tools  section**.

The available input format are:

* **raw** : a raw text format
* **email** : a mail format

To run the command type simply from tkeir directory:

.. code-block:: shell 
  
  python3 thot/tokenizer_svc.py --config=<path to tokenizer configuration file>

A light client can be run through the command

.. code-block:: shell 
  
  python3 thot/tokenizer_client.py --config=<path to tokenizer configuration file> --input=<input directory> --output=<output directory>

Morphosyntactic tagger
----------------------

The Morphosyntactic tagger is a tool allowing to extract Part Of Speech and lemma from "title_tokens" and "content_tokens" field of tkeir document.
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

.. code-block:: shell 
  
  python3 thot/mstagger_svc.py --config=<path to mstagger configuration file>


A light client can be run through the command

.. code-block:: shell 
  
  python3 thot/mstagger_client.py --config=<path to ms tagger configuration file> --input=<input directory> --output=<output directory>


Named entity tagger
-------------------

The Named entity tagger is a tool allowing to extract Named Entities from "title_tokens" and "content_tokens" field of tkeir document.
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

.. code-block:: shell 

  python3 thot/nertagger_svc.py --config=<path to ner configuration file>

A light client can be run through the command

.. code-block:: shell 
  
  python3 thot/nertagger_client.py --config=<path to ner tagger configuration file> --input=<input directory> --output=<output directory>


Embbeding processing
--------------------

The embeddings extraction is a tool allowing to extract embedding from "title_tokens" and "content_tokens", "ner", "svo" field of tkeir document.
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

.. code-block:: shell 
  
  python3 thot/embeddings_svc.py --config=<path to embeddings configuration file>

A light client can be run through the command

.. code-block:: shell 
  
  python3 thot/embeddings_client.py --config=<path to embeddings configuration file> --input=<input directory> --output=<output directory>


Relation clustering
-------------------

Relation clustering allows to create class on SVO extracted during the Syntactic tagging phase.

To run the command type simply from tkeir directory:

.. code-block:: shell 
 
  python3 thot/relation_clustering.py --config=<path to relation configuration file> -i <path to file with syntactic data extracted> -o <path to output folder>


Document classification
-----------------------

The document classification allows to classify document into user defined classes
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

.. code-block:: shell 
  
  python3 thot/zeroshotclassifier_svc.py --config=<path to configuration file>

A light client can be run through the command

.. code-block:: shell 
  
  python3 thot/zeroshotclassifier_client.py --config=<path to configuration file> --input=<input directory> --output=<output directory>


Sentiment Analysis
------------------

The sentiment analsysis allows to classify document into 2 classes : POSITIVE and NEGATIVE
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

.. code-block:: shell 
  
  python3 thot/sentiment_svc.py --config=<path to configuration file>

A light client can be run through the command

.. code-block:: shell 
  
  python3 thot/sentiment_client.py --config=<path to configuration file> --input=<input directory> --output=<output directory>


Document summary
----------------

The document summarizer allows to create a summary of document (by block of 500 words)
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

.. code-block:: shell 
  
  python3 thot/summarizer_svc.py --config=<path to configuration file>

A light client can be run through the command

.. code-block:: shell 
  
  python3 thot/summarizer_client.py --config=<path to configuration file> --input=<input directory> --output=<output directory> -m <min length> -M <max length> [-mp <min percentage> -Mp <max percentage>]

Document indexing
-----------------

The document indexer allows to index a document
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

.. code-block:: shell 
  
  python3 thot/index_svc.py --config=<path to configuration file>

A light client can be run through the command

.. code-block:: shell 
  
  python3 thot/index_client.py --config=<path to configuration file> --input=<input directory>


Another way to index a directory is to use the tool tkeir2index
