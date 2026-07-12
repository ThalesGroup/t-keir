# Installation

Tested environments:

* ubuntu 20.04
* Almalinux 8


## Installation Pre-requist : prepare T-KEIR

### Prepare environment

* install git

```shell  title="Example under ubuntu"
#> sudo apt install git
```

```shell  title="Example under almalinux"
#> sudo dnf install git
```

* install wget

```shell  title="Example under ubuntu"
#> sudo apt install wget
```

```shell  title="Example under almalinux"
#> sudo dnf install wget
```

* install Python (**>= 3.10**, 3.11 recommended) and [uv](https://docs.astral.sh/uv/getting-started/installation/)

When **python** and **pip** package manager are installed you can simply run: 

```shell  title="Example under ubuntu"
#> sudo apt install python3 python3-pip
```

```shell  title="Example under almalinux"
#> sudo dnf install python3
#> sudo dnf install python3-pip
```

```shell  title="Example install uv"
#> curl -LsSf https://astral.sh/uv/install.sh | sh
```

* clone repository

```shell  title="Example of repository clonning into 't-keir-oss' directory"
#> git clone https://github.com/ThalesGroup/t-keir.git t-keir-oss
```

### T-Keir Directory structure

* **configs**           : bundled pipeline and task configuration files
* **docs**              : MkDocs documentation (`make docs` from repository root)
* **tests**             : unit and functional tests
* **thot**              : T-KEIR source code and CLI tools (`thot/tools/`)


### Python environment

T-KEIR requires **Python >= 3.10** and **uv** for installation from GitHub.
From the repository root, run `make setup` (see [Quickstart](ready_to_run.md)).

### Dev container (recommended)

Instead of installing Python and system packages on the host, use the bundled dev
container: `make devcontainer` or `bash .devcontainer/enter-devcontainer.sh` from the
host; or open the repository root in Cursor/VS Code → Command Palette →
**Dev Containers: Reopen in Container**. Step-by-step instructions:
[Dev Container](devcontainer.md).


## Installation running

T-Keir provides a script to install all in one time (section [Quick installation with script](#Quick-installation-with-script)).
Alternatively and for expert, you can follow the step by step installation (section [Step by step](#Step-by-step)).

### **<span style="color:green">\[RECOMMANDED\]</span>** Quick installation with the installation script

The 'quick installation script' is in the root of T-Keir directory. As pre-requisite you have to make sure **wget** is installed. 

After git repository cloning.
```shell  title="Install T-Keir"
#> ./install.sh $HOME/mytkeir
```

The script installs dependencies into `tkeir/.venv`. For the current OSS workflow,
prefer `make setup` from the repository root instead of the legacy `install.sh` path.


### **<span style="color:red">\[EXPERT\] </span>** Step by Step

After git repository cloning.
```shell  title="Build a python wheel package:"
#> uv build
```

A wheel file will be created in "**dist**" directory. Then you can simply run a pip install on the created wheel.
Note that is highly recommanded to run wheel installation in a python virtual environment.

#### Install from Wheel

You can directly install T-Keir from weel:

Go in "dist" folder (created by uv - under **t-keir-oss** directory created by github cloning)

```shell  title="Create a python virtual environement:"
#>  python3 -m venv $HOME/tkeirenv`
```

```shell  title="Activate you environement:"
#> source $HOME/tkeirenv/bin/activate
```

```shell  title="Install the Wheel:"
#> pip install <FILE_NAME>.whl
```

**Troubleshooting** : if there is a problem with **pycurl** install libcurl4-openssl-dev and libssl

```shell  title="E.G under debian/ubuntu:"
#> sudo apt install libcurl4-openssl-dev libssl-dev
```

#### Configure the services

Service configuration files are bundled in **tkeir/configs/**. You can copy or edit them directly; paths to lexical resources are resolved relative to the tkeir package root.

##### Initialize tokenizer resources

Build the multi-word expression pickle before the first pipeline run:

```shell
make init-models
```

Or explicitly:

```shell
tkeir-create-annotation-resource \
  --entries-file resources/modeling/tokenizer/en/annotation-resources.json \
  --output resources/modeling/tokenizer/en/tkeir_mwe.pkl
```

Set `TRANSFORMERS_CACHE` when downloading Hugging Face models used by optional tasks.

## Copy or create data

T-Keir comes with default configuration file.
Nevertheless you can modify or add file. Most of them are configuration (see configuration section).

### Index mappings

Index mapping support has been removed from this distribution.

### Resources

Lexical resources and rule files are stored in **resources/modeling/tokenizer/\[en|fr...\]**. Their usage is described in **resources/modeling/tokenizer/en/annotation-resources.json**.
