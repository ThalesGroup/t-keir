# Keywords extractor

The Keywords extractor is a tool allowing to extract keywords from "title_morphosyntax" and "content_morphosyntax" field of tkeir document.
This tools is a rest service where the API is described in **API section** and the configuration file is described in **Configuration section**.

## Keywords extractor API

!!swagger keywords.json!!

## Keywords extractor configuration

Example of Configuration:


```json title="keywords.json"
--8<-- "../app/projects/template/configs/keywords.json"
```

Keywords extractor is an aggreation of network configuration, serialize configuration, runtime configuration (in field converter), logger (at top level).
The extractor allows to define validation rules for keywords:

- **language** :the language of tokenizer
- **resources-base-path**: the path to the resources (containing file created by tools *createAnnotationResources.py*
- **keywords-rules** : validation rules
- **prunning** : max number of words in keyword sequence

Keywords rules allows to filter and validate rules according to their POS Tags.

Example of Configuration:

```json title="indexing.json"
--8<-- "../app/projects/template/configs/keywords-rules.json"
```


The validation rule:

- **possible-pos-in-syntagm**: the list of the accepted POS tags in the syntagm associated to Named entity
- **at-least**: the minimal POS Tag

### Configure Keywords extractor logger

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

### Configure Keywords extractor Network

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


### Configure Keywords extractor runtime

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

## Keywords extractor service

To run the command type simply from tkeir directory:

```shell
python3 thot/keywordextractor_svc.py --config=<path to keywords configuration file>
```

A light client can be run through the command

```shell
python3 thot/keywordextractor_client.py --config=<path to keywords configuration file> --input=<input directory> --output=<output directory>
```

## Keywords extractor Tests

The Keywords extractor service come with unit and functional testing.

### Keywords Unit tests

Unittest allows to test Tokenizer classes only.

```shell
python3 -m unittest thot/tests/unittests/TestKeywordsConfiguration.py
python3 -m unittest thot/tests/unittests/TestKeywordsExtractor.py
```

### Keywords extractor Functional tests

```shell
python3 -m unittest thot/tests/functional_tests/TestKeywordsExtractorSvc.py
```
