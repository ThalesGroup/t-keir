# Embbeding processing

The embeddings extraction is a tool allowing to extract embedding from "title_tokens" and "content_tokens", "ner", "svo" field of tkeir document.
This tools is a rest service where the API is described in **API section** and the configuration file is described in **Configuration section**.

## Embeddings API


!!swagger embeddings.json!!

## Embeddings configuration

Example of Configuration:


```json title="relation.json"
--8<-- "./app/projects/template/configs/embeddings.json"
```

Embedding configuration is an aggreation of network configuration, serialize configuration, runtime configuration (in field converter), logger (at top level).
The models fiels allows to configure model access

"language":"multi",

: "use-cuda":true,
  "batch-size":256

- **language** :the language of model (not yet implemented, use multi for language agnostic)
- **use-cuda**: use cuda to run the model
- **batch-size** : size of batch sent to the model

### Configure Embeddings logger

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

### Configure Embeddings Network

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


### Configure Embeddings runtime

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

## Embeddings service

To run the command type simply from tkeir directory:

```shell
python3 thot/embeddings_svc.py --config=<path to embeddings configuration file>
```

A light client can be run through the command

```shell
python3 thot/embeddings_client.py --config=<path to embeddings configuration file> --input=<input directory> --output=<output directory>
```

## Embeddings Tests

The Embeddings service come with unit and functional testing.

### Embeddings Unit tests

Unittest allows to test Tokenizer classes only.

```shell
python3 -m unittest thot/tests/unittests/TestEmbeddingConfiguration.py
python3 -m unittest thot/tests/unittests/TestEmbeddings.py
```

### Embeddings Functional tests

```shell
python3 -m unittest thot/tests/functional_tests/TestEmbeddingsSvc.py
```
