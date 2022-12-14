# Cluster Inference

The Cluster Inference is a tool allowing to infer cluster classes on knowledge graph entries
This tools is a rest service.

## Cluster Inference API

!!swagger clusterinfer.json!!

This API is also available via the service itself on http://<service host\>:<service port\>/swagger

## Cluster Inference configuration

Example of Configuration:


```json title="relation.json"
--8<-- "./app/projects/template/configs/relations.json"
```

### Configure cluster inference logger

Logger is configuration at top level of json in *logger* field.

Example of Configuration:

```json title="logger configuration"
--8<-- "./docs/configuration/examples/loggerconfiguration.json"
```

The logger fields are:

- **logging-file** is the filename of the log file (notice that "-\<logname>" will be added to this name=

- **logging-path** is the path to the logfile (if it does not exist it will be created)

- **logging-level** contains two fields:

  - **file** for the logging level of the file
  - **screen** for the logging level on screen output

  Both can be set to the following values:

  - **debug** for the debug level and developper information
  - **info** for the level of information
  - **warning** to display only warning and errors
  - **error** to display only error

### Configure cluster inference Network

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


### Configure cluster inference runtime

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

## Cluster Inference service

To run the command type simply from tkeir directory:

```shell
python3 thot/clusterinfer_svc.py --config=<path to configuration file>
```

or if you install tkeir wheel:

```shell
tkeir-clusterinfer-svc.py --config=<path to configuration file>
```

A light client can be run through the command

```shell
python3 thot/clusterinfer_client.py --config=<path to configuration file> --input=<input directory> --output=<output directory>
```

or if you install tkeir wheel:

```shell
tkeir-clusterinfer-client.py --config=<path to configuration file> --input=<input directory> --output=<output directory>
```


## Cluster Inference Tests

The converter service come with unit and functional testing.

### Cluster Inference Unit tests

Unittest allows to test Cluster Inference classes only.

```shell
python3 -m unittest thot/tests/unittests/TestRelationClusterizerConfiguration.py
python3 -m unittest thot/tests/unittests/TestClusterInference.py
```

### Cluster Inference Functional tests

```shell
python3 -m unittest thot/tests/functional_tests/TestClusterInferSvc.py
```
