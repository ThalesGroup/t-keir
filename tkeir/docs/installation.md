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

* install pyhton (3.8) and poetry. Follow the instructions : [Poetry installation documentation](https://python-poetry.org/docs)

When **python** and **pip** package manager are installed you can simply run: 

```shell  title="Example install poetry"
#> pip3 install poetry
```

* clone repository

```shell  title="Example of repository clonning into 't-keir-oss' directory"
#> git clone https://github.com/ThalesGroup/t-keir.git t-keir-oss
```

### T-Keir Directory structure

* **app/bin**           : scripts and tools for server execution
* **app/projects**      : projects templates (use by T-Keir to create user configuration file - do not edit or modify)
* **docs**              : buildable documentation
* **runtimes/docker**   : docker environment
* **tests**             : internal unit tests
* **thot**              : tkeir source code


### Python environnment

T-KEIR is a python software, **python >=3.8** and **poetry** are necessary for an installation from gitlab/github.
Otherwise and from Thales environnement only, you can install by using pip command. The last way is to use docker

![Screenshot](resources/images/doc-tkeir-install-strategies.png)


Optionnaly, to run the documentation server go in directory **tkeir** and run mkdocs server :

```shell  title="Example of mkdocs installation under ubuntu"
#> sudo apt install mkdocs
```


```shell  title="Run the documentation server with mkdocs"
mkdocs serve
```


## Installation running

T-Keir provides a script to install all in one time (section [Quick installation with script](#Quick-installation-with-script)).
Alternatively, you can follow step by the installation (section [Step by step](#Step-by-step)).

### Quick installation with the installation script

The 'quick installation script' is in the root of T-Keir directory. As pre-requisite you have to make sure **wget** is installed. 

After git repository cloning.
```shell  title="Install T-Keir"
#> ./install.sh $HOME/mytkeir
```

The script will install T-Keir in repository '$HOME/mytkeir' in a dedicated python environment ('$HOME/mytkeir/tkeirenv').
Notice that this installation will also install Opensearch 2.9.0 as a third party tool.

### Step by Step

After git repository cloning.
```shell  title="Build a python wheel package:"
#> poetry build
```

A wheel file will be created in "**dist**" directory. Then you can simply run a pip install on the created wheel.
Note that is highly recommanded to run wheel installation in a python virtual environment.

#### Install from Wheel

You can directly install T-Keir from weel:

Go in "dist" folder (created by poetry - under **t-keir-oss** directory created by github cloning)

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

#### Install T-Keir with a docker image

You could build the docker base image. This image contains os and python dependencies and code of search ai with one entry point
by service. The wheel package will be created, so you should ensure poetry is installed and in running path.

Go in **tkeir/runtimes/docker** directory and run the following command:

```shell 
#> ./builddocker.sh
```

## Configure the services

T-Keir provides a script to automatically generate configuration file:

### Nomenclature

* PATH_TO_TKEIR : to the the name of directory containing t-keir (the clone of github, in this installation guide it is **t-keir-oss**)
* PATH_TO_YOUR_OUTPUR_CONFIG_DIR : this is your workspace space (where you configuration files are created and stores, where there are your model)
* PATH_TO_YOUR_SHARE_DIRECTORY_OR_VOLUME_NAME : share directory need by docker to communication with host


### Command lines


```shell
python3 tkeir/thot/tkeir_init_project.py -t <PATH TO TKEIR>/tkeir/app/projects/template/ -o <PATH TO YOUR OUTPUT CONFIG DIR>
```

or if you install T-Keir wheel:

```shell
tkeir-init-project -t <PATH TO TKEIR>/tkeir/app/projects/template/ -o <PATH TO YOUR OUTPUT CONFIG DIR>
```

When you work with a docker you can use a share directory or a volume (to make configurer persistent).

```shell
docker run --rm -it -v <PATH TO YOUR SHARE DIRECTORY OR VOLUME NAME>:/home/tkeir_svc/share -w /home/tkeir_svc/tkeir --entrypoint python3 theresis/tkeir /home/tkeir_svc/tkeir/thot/tkeir_init_project.py -t /home/tkeir_svc/tkeir/app/projects/template -o /home/tkeir_svc/share
```

### Initialize/Load the models

When you build you docker volumes containing model and default configuration are automatically generated.
To update the configuration you can go into directory **app/bin** and run the command:
  
```shell
./init-models.sh <PATH TO YOUR OUTPUT CONFIG DIR>/project/configs  <PATH TO YOUR OUTPUT CONFIG DIR>/project/models
```

Or from docker

```shell
docker run --rm -it -v $host_dir:$docker_dir -w /home/tkeir_svc/tkeir --entrypoint bash $tkeir_img /home/tkeir_svc/tkeir/app/bin/init-models.sh $docker_dir/project/configs $docker_dir/project/resources/modeling/net/
```

Where 

* **host_dir** is the variable containing the path to the shared host directory
* **docker_dir** is the variable containing the path to the shared docker directory
* **tkei_img** is the name of the image

Note, that the environment variable TRANSFORMERS_CACHE **HAVE TO BE** always set to model path before run a T-Keir service using models.

Take care of proxies. Please set correclty $HOME/.docker/config.json like that:

```json
  {
    "proxies":
    {
      "default":
      {
        "httpProxy": "your_http_proxy",
        "httpsProxy": "your_https_proxy",
        "noProxy": "your_no_proxy"
      }
    }
  }
```

For a docker compose network environment, don't forget to add **tkeir opendistro** hostname and all services in no_proxy.


## Copy or create data

T-Keir comes with default configuration file.
Nevertheless you can modify or add file. Most of them are configuration (see configuration section).

### Index mappings

Index mapping is store in **RESOURCES_DIRECTORY/indices/indices_mapping**. if you create new mapping it MUST contains the same fields.
You can freely change the analyzers.

### Resources

The resources are stored in **RESOURCES_DIRECTORY/modeling/tokenizer/\[en|fr...\]**. This directory contains file with list or csv tables.
The descriptions of these file are in **CONFIGS/annotation-resources.json**
