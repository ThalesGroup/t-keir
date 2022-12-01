***************
Tools Overview
***************

===========
Tkeir tools
===========

TKeir tools is mostly a set of REST service, except Converter each service use generally as 'T-Keir' document 
which store the extracted information (i.e. tokens, morphosyntax, named entities, syntax and SPO triples, semantic classes ...)

====================
How run the services
====================

The services can be run a a same way:

.. code-block:: shell

  python3 thot/<service_name>_svc.py -c service_config.json


====================
How use the services
====================

There is two way to consume the service:

1. by developing your own access to the REST api
2. by using the python client

.. code-block:: shell

  python3 thot/<service_name>_client.py -c service_config.json [client specific option] -s [http|https] -nsv

* -s option allows to select http scheme it should be http or https
* -nsv option allows to avoid ssl certificate verification


============================
Quick start / Docker compose
============================

T-KEIR comes with ready to use docker compose. to run all services go in directory **runtime/docker**

.. code-block:: shell

  docker-compose -f docker-compose-tkeir.yml up


========================================
Quick start / Example service by service
========================================

Here we use all pre-configured service: the configuration environement is in  directory **app/projects/default/configs/***.

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


Syntactic tagger and SVO Extraction
-----------------------------------

The syntactic tagger is a tool allowing to extract syntactic depencies and extract SVO.
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

.. code-block:: shell 

  python3 thot/syntactictagger_svc.py --config=<path to syntactic configuration file>

A light client can be run through the command

.. code-block:: shell 
  
  python3 thot/syntactictagger_client.py --config=<path to syntactic configuration file> --input=<input directory> --output=<output directory>


Keyword Extraction
------------------

The keywords extractor is a tool allowing to extract keywords by using RAKE algoritms
This tools is a rest service where the API is described in **Tools  section**.

To run the command type simply from tkeir directory:

.. code-block:: shell 

  python3 thot/keywordextractor_svc.py --config=<path to keywords configuration file>

A light client can be run through the command

.. code-block:: shell 
  
  python3 thot/keywordextractor_client.py --config=<path to keyword configuration file> --input=<input directory> --output=<output directory>


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


There is also a service allowing inferencer according to a model computed with the previous command

To run the command type simply from tkeir directory:

.. code-block:: shell 

  python3 thot/clusterinfer_svc.py --config=<path to relation configuration file>

A light client can be run through the command

.. code-block:: shell 
  
  python3 thot/clusterinfer_client.py --config=<path to relation configuration file> --input=<input directory> --output=<output directory>



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
  
  python3 thot/summarizer_client.py --config=<path to configuration file> --input=<input directory> --output=<output directory> -m <min length> -M <max length>

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







