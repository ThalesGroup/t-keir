******************
Sentiment Analyzer
******************

The Sentitment classifier is a tool allowing to classify a document according to 2 classes:NEGATIVE and POSITIVE
This tools is a rest service.

======================
Sentiment Analyzer API
======================

.. openapi:: ../resources/api/sentiment.json

This API is also available via the service itself on http://<service host>:<service port>/swagger

================================
Sentiment Analyzer configuration
================================

Example of Configuration:

.. literalinclude:: ../../../app/projects/template/configs/sentiment.json
    :language: json

Sentiment Analyzer is an aggreation of network configuration, serialize configuration, runtime configuration (in field converter), logger (at top level).

Configure Sentiment classifier Settings
---------------------------------------

Settings (in field **sentiment**) allows to configure some default behaviours of sentiment:


* **settings/language**: define language [en | fr]
* **settings/use-cuda**: use cuda device
* **settings/cuda-device**: device number (multiple graphic cards)

Configure Sentiment classifier logger
-------------------------------------

Logger is configuration at top level of json in *logger* field.

Example of Configuration:

.. literalinclude:: ../configuration/examples/loggerconfiguration.json
    :language: json

The logger fields is:

* **logging-level** 

  It can be set to the following values:

  * **debug** for the debug level and developper information
  * **info** for the level of information
  * **warning** to display only warning and errors
  * **error** to display only error
  * **critical** to display only error


Configure Sentiment classifier Network
--------------------------------------

Example of Configuration:

.. literalinclude:: ../configuration/examples/networkconfiguration.json
    :language: json


The network fields:

* **host** : hostname
* **port** : port of the service
* **associated-environement** : is the "host" and "port" associated environment variables that allows to replace the default one. This field is not mandatory.

  * "host" : associated "host" environment variable
  * "port" : associated "port" environment variable

* **ssl** : ssl configuration **IN PRODUCTION IT IS MANDATORY TO USE CERTIFICATE AND KEY THAT ARE *NOT* SELF SIGNED**
  
  * **cert** : certificate file
  * **key** : key file 

Configure Sentiment classifier Serialize
----------------------------------------

Example of Configuration:

.. literalinclude:: ../configuration/examples/serializeconfiguration.json
    :language: json

The serialize fields:

* **input** : serialize input of service

  * **path** : path of serialized fields
  * **keep-service-info** : True if serialize info is kept
  * **associated-environement** : is the "path" and "keep-service-info" associated environment variables that allows to replace the  default one. This field is not mandatory.

    * **path** : associated "path" environment variable
    * **keep-service-info** : associated "keep-service-info" environment variable

* output : serialize output of service

  * **path** : path of serialized fields
  * **keep-service-info** : True if serialize info is kept
  * **associated-environement** : if the "path" and "keep-service-info" associated environment variables that allows to replace the  default one. This field is not mandatory.
      
    * **path** : associated "path" environment variable
    * **keep-service-info** : associated "keep-service-info" environment variable
  
Configure Sentiment classifier runtime
--------------------------------------

Example of Configuration:

.. literalinclude:: ../configuration/examples/runtimeconfiguration.json
    :language: json


The Runtime fields:
  
* **request-max-size** : how big a request may be (bytes)
* **request-buffer-queue-size**: request streaming buffer queue size
* **request-timeout** : how long a request can take to arrive (sec)
* **response-timeout** : how long a response can take to process (sec)
* **keep-alive**: keep-alive 
* **keep-alive-timeout**: how long to hold a TCP connection open (sec)
* **graceful-shutdown_timeout** : how long to wait to force close non-idle connection (sec)
* **workers** : number of workers for the service on a node
* **associated-environement** : if one of previous field is on the associated environment variables that allows to replace the  default one. This field is not mandatory.

  * **request-max-size** : overwrite with environement variable
  * **request-buffer-queue-size**: overwrite with environement variable
  * **request-timeout** : overwrite with environement variable
  * **response-timeout** : overwrite with environement variable
  * **keep-alive**: overwrite with environement variable
  * **keep-alive-timeout**: overwrite with environement variable
  * **graceful-shutdown_timeout** : overwrite with environement variable
  * **workers** : overwrite with environement variable


==========================
Sentiment Analyzer service
==========================


To run the command type simply from tkeir directory:

.. code-block:: shell 
  
    python3 thot/sentiment_svc.py --config=<path to configuration file>

A light client can be run through the command

.. code-block:: shell 
  
    python3 thot/sentiment_client.py --config=<path to configuration file> --input=<input directory> --output=<output directory>



========================
Sentiment Analyzer Tests
========================

The converter service come with unit and functional testing. 


Sentiment Analyzer Unit tests
------------------------------

Unittest allows to test Sentiment Analyzer classes only.

.. code-block:: shell 

  python3 -m unittest thot/tests/unittests/TestSentimentConfiguration.py
  python3 -m unittest thot/tests/unittests/TestSentiment.py

 

Sentiment Analyzer Functional tests
------------------------------------

.. code-block:: shell 

  python3 -m unittest thot/tests/functional_tests/TestSentimentSvc.py


