# Zeroshot Classifier

The Zeroshot classifier is a tool allowing to classify a document according to classes defined in configuration file
This tools is a rest service.
Tokenization depends on annotation model created by the tool stored in **tkeir/thot/tasks/tokenizer/createAnnotationResouces.py**
This tools allows to create typed compound word list.

## Zeroshot Classifier API

!!swagger zsc.json!!


## Zeroshot Classifier configuration

Example of Configuration:

```json title="zeroshotclassifier.json"
--8<-- "./app/projects/template/configs/zeroshotclassifier.json"
```

Zeroshot Classifier is an aggreation of network configuration, serialize configuration, runtime configuration (in field converter), logger (at top level).
The zeroshot-classification configuration is a table containing classes configuration:

- **settings/language**: define classifier language \[en | fr\]
- **settings/use-cuda**: use cuda device
- **settings/cuda-device**: device number (multiple graphic cards)
- **\[classes\]/label**: label of classes
- **\[classes\]/content**: possible value for the classe (can view view as synonyms or sublasses)
- **re-labelling-strategy** :
  \* sum : master class is the sum of the scores of subclasses (synonyms)
  \* mean : master class is the mean of the scores of subclasses (synonyms)
  \* max : master class is the max of the scores of subclasses (synonyms)

### Configure classifier logger

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

### Configure classifier Network

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

### Configure classifier runtime

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

## Zeroshot Classifier service

To run the command type simply from tkeir directory:

```shell
python3 thot/zeroshotclassifier_svc.py --config=<path to configuration file>
```

A light client can be run through the command

```shell
python3 thot/zeroshotclassifier_client.py --config=<path to configuration file> --input=<input directory> --output=<output directory>
```

## Zeroshot Classifier Tests

The converter service come with unit and functional testing.

### Zeroshot Classifier Unit tests

Unittest allows to test Zeroshot Classifier classes only.

```shell
python3 -m unittest thot/tests/unittests/TestZeroshotClassifierConfiguration.py
python3 -m unittest thot/tests/unittests/TestZeroshotClassifier.py
```

### Zeroshot Classifier Functional tests

```shell
python3 -m unittest thot/tests/functional_tests/TestZeroshotClassifierSvc.py
```
