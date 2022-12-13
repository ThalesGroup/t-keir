# Named entity tagger

The Named entity tagger is a tool allowing to extract Named Entities from "title_tokens" and "content_tokens" field of tkeir document.
This tools is a rest service where the API is described in **API section** and the configuration file is described in **Configuration section**.

## NER Tagger API

!!swagger nertagger.json!!

## NER tagger configuration

Example of Configuration:

```json title="ner.json"
--8<-- "./app/projects/template/configs/nertagger.json"
```

NER Tagger is an aggreation of network configuration, serialize configuration, runtime configuration (in field converter), logger (at top level).
The label configuration allows to define validation rules file:

- **language** :the language of tokenizer
- **resources-base-path**: the path to the resources (containing file created by tools *createAnnotationResources.py*
- **ner-rules** : rules to filter labels

NER Rules allows to filter and validate rules according to their POS Tags.

Example of Configuration:


```json title="indexing.json"
--8<-- "./app/projects/template/configs/ner-rules.json"
```

The validation rule is a set of triple:

- **label**: label of named entity to validat
- **possible-pos-in-syntagm**: the list of the accepted POS tags in the syntagm associated to Named entity
- **at-least**: the minimal POS Tag

### Configure NER tagger logger

Logger is configuration at top level of json in *logger* field.

Example of Configuration:

```json title="logger configuration"
--8<-- "./docs/configuration/examples/loggerconfiguration.json"
```

The logger fields is:

- **logging-level**

  It can be set to the following values:

  - **debug** for the debug level and developper information
  - **info** for the level of information
  - **warning** to display only warning and errors
  - **error** to display only error
  - **critical** to display only error

### Configure NER tagger Network

Example of Configuration:

```json title="network configuration"
--8<-- "./docs/configuration/examples/networkconfiguration.json"
```

The network fields:

- **host** : hostname

- **port** : port of the service

- **associated-environement** : is the "host" and "port" associated environment variables that allows to replace the default one. This field is not mandatory.

  - "host" : associated "host" environment variable
  - "port" : associated "port" environment variable

- **ssl** : ssl configuration **IN PRODUCTION IT IS MANDATORY TO USE CERTIFICATE AND KEY THAT ARE \*NOT\* SELF SIGNED**

  - **cert** : certificate file
  - **key** : key file



### Configure NER tagger runtime

Example of Configuration:

```json title="network configuration"
--8<-- "./docs/configuration/examples/runtimeconfiguration.json"
```

The Runtime fields:

- **request-max-size** : how big a request may be (bytes)

- **request-buffer-queue-size**: request streaming buffer queue size

- **request-timeout** : how long a request can take to arrive (sec)

- **response-timeout** : how long a response can take to process (sec)

- **keep-alive**: keep-alive

- **keep-alive-timeout**: how long to hold a TCP connection open (sec)

- **graceful-shutdown_timeout** : how long to wait to force close non-idle connection (sec)

- **workers** : number of workers for the service on a node

- **associated-environement** : if one of previous field is on the associated environment variables that allows to replace the  default one. This field is not mandatory.

  - **request-max-size** : overwrite with environement variable
  - **request-buffer-queue-size**: overwrite with environement variable
  - **request-timeout** : overwrite with environement variable
  - **response-timeout** : overwrite with environement variable
  - **keep-alive**: overwrite with environement variable
  - **keep-alive-timeout**: overwrite with environement variable
  - **graceful-shutdown_timeout** : overwrite with environement variable
  - **workers** : overwrite with environement variable

## NER tagger service

To run the command type simply from tkeir directory:

```shell
python3 thot/nertagger_svc.py --config=<path to ner configuration file>
```

A light client can be run through the command

```shell
python3 thot/nertagger_client.py --config=<path to ner tagger configuration file> --input=<input directory> --output=<output directory>
```

## NER Tagger Tests

The NER Tagger service come with unit and functional testing.

### NERTagger Unit tests

Unittest allows to test Tokenizer classes only.

```shell
python3 -m unittest thot/tests/unittests/TestNERTaggerConfiguration.py
python3 -m unittest thot/tests/unittests/TestNERTagger.py
```

### NER Tagger Functional tests

```shell
python3 -m unittest thot/tests/functional_tests/TestNERTaggerSvc.py
```
