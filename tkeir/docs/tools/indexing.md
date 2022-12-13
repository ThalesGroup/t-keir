# Indexer

The indexer is a tool allowing to index analyzed document.
This tools is a rest service.

## Indexer API

!!swagger indexer.json!!


## Indexer configuration

Example of Configuration:


```json title="indexing.json"
--8<-- "./app/projects/template/configs/indexing.json"
```

Indexer is an aggreation of network configuration, serialize configuration, runtime configuration (in field converter), logger (at top level).

### Configure indexer logger

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

### Configure indexer Network

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



### Configure indexer runtime

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

## Indexer service

To run the command type simply from tkeir directory:

```shell
python3 thot/index_svc.py --config=<path to indexer configuration file>
```

A light client can be run through the command

```shell
python3 thot/index_client.py --config=<path to indexer configuration file> --input=<input directory> --output=<output directory>
```

## Indexer Tests

The converter service come with unit and functional testing.

### Indexer Unit tests

Unittest allows to test Indexer classes only.

```shell
python3 -m unittest thot/tests/unittests/TestIndexingConfiguration.py
python3 -m unittest thot/tests/unittests/TestIndexing.py
```

### Indexer Functional tests

```shell
python3 -m unittest thot/tests/functional_tests/TestIndexingSvc.py
```
