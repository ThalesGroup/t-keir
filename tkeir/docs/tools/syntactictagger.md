# Syntactic tagger

The Named entity tagger is a tool allowing to extract Named Entities from "title_tokens" and "content_tokens" field of tkeir document.
This tools is a rest service where the API is described in **API section** and the configuration file is described in **Configuration section**.

## Syntactic tagger API

!!swagger syntactictagger.json!!

## Syntactic tagger configuration

Example of Configuration:


```json title="syntactic-tagger.json"
--8<-- "./app/projects/template/configs/syntactic-tagger.json"
```

Syntactic is an aggreation of network configuration, serialize configuration, runtime configuration (in field converter), logger (at top level).

Syntactic Rules allows to define rule for triple Subject, Predicate, Object extraction

Example of Configuration:


```json title="syntactic-tagger.json"
--8<-- "./app/projects/template/configs/syntactic-rules.json"
```

The rules allows to extract triple based on sequence matcher of spacy

The syntax of the field is:

- **\<name of rule>** :

  - **rule** : matcher rule or triple rule
  - **type** : subject, object, predicate of triple

### Configure Syntactic tagger logger

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

### Configure Syntactic tagger Network

Example of Configuration:


```json title="network configuration"
--8<-- "./docs/configuration/examples/networkconfiguration.json"
```

The network fields:

- **host** : hostname

- **port** : port of the service

- **associated-environement** : is the "host" and "port" associated environment variables that allows to replace the
  default one. This field is not mandatory.

  - "host" : associated "host" environment variable
  - "port" : associated "port" environment variable

- **ssl** : ssl configuration **IN PRODUCTION IT IS MANDATORY TO USE CERTIFICATE AND KEY THAT ARE \*NOT\* SELF SIGNED**

  - **cert** : certificate file
  - **key** : key file


### Configure Syntactic tagger runtime

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

## Syntactic tagger service

To run the command type simply from tkeir directory:

```shell
python3 thot/syntactictagger_svc.py --config=<path to ner configuration file>
```

or if you install tkeir wheel:

```shell
tkeir-syntactictagger-svc --config=<path to ner configuration file>
```


A light client can be run through the command

```shell
python3 thot/syntactictagger_client.py --config=<path to ner tagger configuration file> --input=<input directory> --output=<output directory>
```

or if you install tkeir wheel:

```shell
tkeir-syntactictagger-client --config=<path to ner tagger configuration file> --input=<input directory> --output=<output directory>
```


## Syntactic tagger Tests

The Syntactic tagger service come with unit and functional testing.

### Syntactic Tagger Unit tests

Unittest allows to test Tokenizer classes only.

```shell
python3 -m unittest thot/tests/unittests/TestSyntacticTaggerConfiguration.py
python3 -m unittest thot/tests/unittests/TestSyntacticTagger.py
```

### Syntactic tagger Functional tests

```shell
python3 -m unittest thot/tests/functional_tests/TestSyntacticTaggerSvc.py
```
