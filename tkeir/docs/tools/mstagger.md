# Morphosyntactic tagger

The Morphosyntactic Tagger is a tool allowing to tag the fields "title_tokens" and "content_tokens" of the tkeir document.
This tools is a rest service.
Morphosyntactic tagger is based on spacy toolbox.

## Morphosyntactic tagger API


!!swagger mstagger.json!!

## Morphosyntactic tagger configuration

Example of Configuration:

```json title="mstagger.json"
--8<-- "./app/projects/template/configs/mstagger.json"
```

Morphosyntactic tagger is an aggreation of network configuration, serialize configuration, runtime configuration (in field converter), logger (at top level).
The segmenter configuration is a table containing path to Multiple Word Expression entries (MWE):

- **language** :the language of tokenizer
- **resources-base-path**: the path to the resources (containing file created by tools *createAnnotationResources.py*
- **mwe** : the file containing MWE entries

### Configure Morphosyntactic tagger logger

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

### Configure Morphosyntactic tagger Network

Example of Configuration:

```json title="network configuration"
--8<-- "./docs/configuration/examples/networkconfiguration.json"
```

The network fields:

- **host** : hostname

- **port** : port of the service

- **associated-environement**

  : default one. This field is not mandatory.

  - "host" : associated "host" environment variable
  - "port" : associated "port" environment variable

- **ssl** : ssl configuration **IN PRODUCTION IT IS MANDATORY TO USE CERTIFICATE AND KEY THAT ARE \*NOT\* SELF SIGNED**

  - **cert** : certificate file
  - **key** : key file


### Configure Morphosyntactic tagger runtime

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

## Morphosyntactic tagger service

To run the command type simply from tkeir directory:

```shell
python3 thot/mstagger_svc.py --config=<path to Morphosyntactic Tagger configuration file>
```

or if you install tkeir wheel:

```shell
tkeir-mstagger-svc --config=<path to Morphosyntactic Tagger configuration file>
```


A light client can be run through the command

```shell
python3 thot/mstagger_client.py --config=<path to Morphosyntactic Tagger configuration file> --input=<input directory> --output=<output directory>
```
or if you install tkeir wheel:

```shell
tkeir-mstagger-client --config=<path to Morphosyntactic Tagger configuration file> --input=<input directory> --output=<output directory>
```


or if you install tkeir wheel:

## Morphosyntactic Tagger Tests

The Morphosyntactic tagger service come with unit and functional testing.

### Morphosyntactic Tagger Unit tests

Unittest allows to test Tokenizer classes only.

```shell
python3 -m unittest thot/tests/unittests/TestMorphoSyntacticTaggerConfiguration.py
python3 -m unittest thot/tests/unittests/TestMorphoSyntacticTagger.py
```

### Morphosyntactic Tagger Functional tests

```shell
python3 -m unittest thot/tests/functional_tests/TestMorphoSyntacticTaggerSvc.py
```
