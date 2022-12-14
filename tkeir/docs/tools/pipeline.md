# Pipeline

The pipeline is a tool allowing to pipeline services takingtkeir_doc as input in there REST API.
This tools is a rest service.

## Pipeline API


!!swagger pipeline.json!!


## Pipeline configuration

Example of Configuration:


```json title="pipeline.json"
--8<-- "./app/projects/template/configs/pipeline.json"
```

Pipeline is an aggreation of network configuration, serialize configuration, runtime configuration (in field converter), logger (at top level).

The settings of pipeline allows to define a strategy to run the tasks:

* **pipeline/settings/strategy** : \[serial (the task are run for a given list),monolthic (the task are alredy run), service (the task are run through a service)\]
* **pipeline/settings/max-time-loop** : max time to run the servic

The pipeline is a chained list of tasks:

- **pipeline/tasks/\[task name\]/task** : task name
- **pipeline/tasks/\[task name\]/previous-task** : previous task name
- **pipeline/tasks/\[task name\]/save-output** : the task output is save or not
- **pipeline/tasks/\[task name\]/clean-input-folder-after-analysis** : does not store data for this task
- **pipeline/tasks/\[task name\]/resources-base-path** : path of resources/configuration file of the task
- **pipeline/tasks/\[task name\]/configuration** : configuration of the task

### Configure pipeline logger

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

### Configure pipeline Network

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


### Configure pipeline runtime

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

## Pipeline service

To run the command type simply from tkeir directory:

```shell
python3 thot/pipeline_svc.py --config=<path to pipeline configuration file>
```

or if you install tkeir wheel:

```shell
tkeir-pipeline-svc --config=<path to pipeline configuration file>
```

A light client can be run through the command

```shell
python3 thot/pipeline_client.py --config=<path to pipeline configuration file> --input=<input directory> --output=<output directory> --loop-time=<time between two get loop> --scheme [http|https] --nsv (not verify ssl)
```

or if you install tkeir wheel:

```shell
tkeir-pipeline-client --config=<path to pipeline configuration file> --input=<input directory> --output=<output directory> --loop-time=<time between two get loop> --scheme [http|https] --nsv (not verify ssl)
```

## Pipeline as batch processing

You can also run the pipeline with a batch function:

```shell
python3 thot/batch_ingester.py -c <PATH TO YOU CONFIGURATION FOLDER>/pipeline.json -i <PATH TO DATA FOLDER>/data/tkeir -o <PATH TO DATA FOLDER>/data/tkeir-out
```

or if you install tkeir wheel:

```shell
tkeir-batch-ingester -c <PATH TO YOU CONFIGURATION FOLDER>/pipeline.json -i <PATH TO DATA FOLDER>/data/tkeir -o <PATH TO DATA FOLDER>/data/tkeir-out
```
