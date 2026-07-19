# Installation

These tools work on \*nix, WSL and docker environment.

## Pre-requist : prepare T-KEIR

* install git

```shell  title="Example under ubuntu"
#> sudo apt install git
```

* install uv. Follow the instructions : [uv installation documentation](https://docs.astral.sh/uv/getting-started/installation/)

## Directory structure

* **app/bin**           : scripts and tools for server execution
* **configs**           : bundled service configuration files
* **docs**              : buildable documentation
* **resources**         : lexical resources and rule files for taggers
* **thot**              : tkeir source code
* **thot/tools**        : CLI tools (pipeline, Vespa search/RAG, annotation resources)


## Installation Prerequists

T-KEIR is a python software; **Python >= 3.10** (3.11 recommended) and **uv** are necessary for an installation from gitlab/github.
Otherwise and from Thales environnement only, you can install by using pip command. The last way is to use docker

Installation options:

1. **uv / wheel** (recommended OSS path) — `make setup` or `uv build` + `pip install`
2. **Dev container** — reopen in `.devcontainer/` then `make setup`
3. **Docker / workspace install** — `make install-workspace` (see root `Makefile`)

To run the documentation go to the repository root and run:

```shell  title="Run the documentation server with mkdocs"
make docs
# or: cd tkeir && uv run mkdocs serve
```

## Installation

After git repository cloning.
```shell  title="Build a python wheel package:"
#> uv build
```

A wheel file will be created in "dist" directory. Then you can simply run a pip install on the created wheel.
Note that is highly recommanded to run wheel installation in a python virtual environment.

### Install from Wheel

You can directly install T-Keir from weel:

Go in "dist" folder (created by uv)

```shell  title="Create a python virtual environement:"
#>  python3 -m venv <YOUR_ENV>`
```

```shell  title="Activate you environement:"
#> source <YOUR_ENV>/bin/activate
```

```shell  title="Install the Wheel:"
#> pip install <FILE_NAME>.whl
```

If there is a problem with **pycurl** install libcurl4-openssl-dev and libssl

```shell  title="E.G under debian/ubuntu:"
#> sudo apt install libcurl4-openssl-dev libssl-dev
```

### Configure the services

Bundled service configuration files live in **configs/**. Edit them directly or copy them to your workspace.

### Initialize/Load the models

Go into directory **app/bin** and run:

```shell
#> ./init-models.sh <PATH TO TKEIR>/tkeir/configs <MODEL PATH>
```

Note, that the environment variable TRANSFORMERS_CACHE **HAVE TO BE** always set to model path before run a T-Keir service using models.



## Copy or create data

T-Keir comes with default configuration file.
Nevertheless you can modify or add file. Most of them are configuration (see configuration section).

### Resources

The resources are stored in **RESOURCES_DIRECTORY/modeling/tokenizer/\[en|fr...\]**. This directory contains file with list or csv tables.
The descriptions of these file are in **resources/modeling/tokenizer/en/annotation-resources.json**


# Quick start

This section describes the steps to run the T-KEIR document analysis pipeline.

## Run the installation part

Go in installation section and run it.

### Prepare T-KEIR and demo

Run setup, then the bundled quickstart on test fixtures:

```shell
make setup
make quickstart
```

This runs the pipeline on `tkeir/tests/fixtures/test-raw/` and all `converter_test*` files. Output goes to `output/quickstart/`.

### Analyse your documents

Run the unified pipeline on your documents. Use **`-t auto`** for PDFs and Office
files; use **`-t raw`** for plain text only.

```shell
tkeir-pipeline -c tkeir/configs/pipeline.yaml -i <INPUT FILE OR DIR> -o <OUTPUT DIR> -t auto
```

The pipeline runs in order: converter → language detection → resource selection → tokenizer → morphosyntax → NER → syntax → keywords. Each step enriches the output JSON document.

`make pipeline` installs spaCy models automatically. MWE handling is disabled by
default; run `make init-models` and pass `--use-mwe` only when you need
compound-word detection.

### Vespa indexing and RAG

Pipeline outputs (`*.pipeline.json`) can be indexed into Vespa for hybrid retrieval:

```shell
# From repository root
make bootstrap    # start Vespa + deploy schemas
make index-fixtures   # build tkeir/tests/indexing/output from PDF fixtures
make index        # index *.pipeline.json (default: tkeir/tests/indexing/output)
make rag          # FastAPI RAG on :8090
```

Python modules live under `thot/tools/search/`; the root `Makefile` invokes them via `python -m thot.tools.search.*`.

### Tool layout (`thot/tools/`)

| Module | Purpose |
|---|---|
| `pipeline.py` | Document analysis pipeline (`tkeir-pipeline`) |
| `search/` | Vespa indexing, init, RAG API |
| `annotation/` | MWE trie compilation (`tkeir-create-annotation-resource`) |
