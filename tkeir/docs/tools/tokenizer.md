# Tokenizer

The tokenizer is a tool allowing to tokenize "title" and "content" field of tkeir document.
This tools is a rest service.
Tokenization depends on annotation model created by the tool stored in **tkeir/thot/tasks/tokenizer/createAnnotationResouces.py**
This tools allows to create typed compound word list.

## Tokenizer API

!!swagger tokenizer.json!!


## Tokenizer configuration

Example of Configuration:

```json title="tokenizer.json"
--8<-- "./app/projects/template/configs/tokenizer.json"
```

Tokenizer is an aggreation of network configuration, serialize configuration, runtime configuration (in field converter), logger (at top level).
The segmenter configuration is a table containing path to Multiple Word Expression entries (MWE):

- **language** :the language of tokenizer
- **resources-base-path**: the path to the resources (containing file created by tools *createAnnotationResources.py*
- **mwe** : the file containing MWE entries
- **normalization-rules** : the file containing normalization rules
- **annotation-resources-reference** : reference to annotation file, needs on tokenizer init

Tokenizer accepts a rule file to select parser (not yet implemented), common typos fixing and word mapping (for example map english words to us words).
The normalization rule is a simple json file with the following fields:

- **parsers** (NOT YET IMPLEMENTED) : the available parser (for exemple pyvalem to parse chemestry formulas)
- **normalization/word-mapping**: mapping words
- **normalization/typos** : typos fixing

```json title="tokenizer-rules.json"
--8<-- "./app/projects/template/configs/tokenizer-rules.json"
```

### Configure tokenizer logger

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

### Configure tokenizer Network

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

### Configure tokenizer runtime

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

## Tokenizer service

To create these resources simply run

```shell
python3 thot/tasks/tokenizer/createAnnotationResource.py --entries=/home/tkeir_svc/tkeir/configs/default/configs/annotation-resources.json --output=/home/tkeir_svc/tkeir/configs/default/resources/modeling/tokenizer/en/tkeir_mwe.pkl
```

To run the command type simply from tkeir directory:

```shell
python3 thot/tokenizer_svc.py --config=<path to tokenizer configuration file>
```

or if you install tkeir wheel:

```shell
tkeir-tokenizer-svc --config=<path to tokenizer configuration file>
```


A light client can be run through the command

```shell
python3 thot/tokenizer_client.py --config=<path to tokenizer configuration file> --input=<input directory> --output=<output directory>
```

or if you install tkeir wheel:

```shell
python3 tkeir-tokenizer-client.py --config=<path to tokenizer configuration file> --input=<input directory> --output=<output directory>
```


## Tokenizer Tests

The converter service come with unit and functional testing.

### Tokenizer Unit tests

Unittest allows to test Tokenizer classes only.

```shell
python3 -m unittest thot/tests/unittests/TestTokenizerConfiguration.py
python3 -m unittest thot/tests/unittests/TestTokenizer.py
```

Notes:
: - if there is error due to the file **tkeir_mwe.mkl** it is normal. You can avoid this error by creating the

the resources model
: - the model data directory is mapped into docker-compose file, please check if all the configuration files are inside this directory

### Tokenizer Functional tests

```shell
python3 -m unittest thot/tests/functional_tests/TestTokenizerSvc.py
```
