# Automatic Summary

The Automatic Summary service is a tool allowing to get extrcative summary from a document.
This tools is a rest service where the API is described in **API section** and the configuration file is described in **Configuration section**.

## Automatic Summary API

!!swagger summary.json!!

## Automatic Summary configuration

Example of Configuration:

```json title="summarizer.json"
--8<-- "../app/projects/template/configs/summarizer.json"
```

Automatic Summary configuration is an aggreation of network configuration, serialize configuration, runtime configuration (in field converter), logger (at top level).

### Configure Automatic Summary Settings

Settings (in field **summarizer**) allows to configure some default behaviours of summarizer:

- **settings/language**: define summarizer language \[en | fr\]
- **settings/min-percent**: minimum summarizer size in percent
- **settings/max-percent**: maximum summarizer size in percent
- **settings/use-cuda**: use cuda device
- **settings/cuda-device**: device number (multiple graphic cards)

### Configure Automatic Summary logger

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

### Configure Automatic Summary Network

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


### Configure Automatic Summary runtime

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

## Automatic Summary service

To run the command type simply from tkeir directory:

```shell
python3 thot/summarizer_svc.py --config=<path to summarizer configuration file>
```

A light client can be run through the command

```shell
python3 thot/summarizer_client.py --config=<path to summarizer configuration file> --input=<input directory> --output=<output directory> -m <minimal output summary length by block> -M <maximal output summary length by block> [-mp <minimal percentage of block length> -Mp <maximal percentage of text block>]
```

## Automatic Summary Tests

The Automatic Summary service come with unit and functional testing.

### Summarizer Unit tests

Unittest allows to test Tokenizer classes only.

```shell
python3 -m unittest thot/tests/unittests/TestSummarizerConfiguration.py
python3 -m unittest thot/tests/unittests/TestSummaryExtractor.py
```

### Summarizer Functional tests

```shell
python3 -m unittest thot/tests/functional_tests/TestSummarySvc.py
```
