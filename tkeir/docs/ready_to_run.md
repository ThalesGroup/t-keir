# From Zero to Hero: Create Quickly a ready to run application

![Screenshot](resources/images/doc-tkeir-quickstart-flow.png)


This section describes the step to create a full information retrieval engine.

## Pre-requisite : run the installation part

Go in installation section and run it.
Do not forget to create your project configuration with "**tkeir_init_project.py**" and initialize the models with "**init-models.sh**". These steps allows to configure T-KEIR.

## Prepare T-KEIR and demo

You have to run the **installation**. It will set up configurations and models.

You have to edit the configuration files:

* **indexing.json** : change fields text-index, nms-index and relation-index by replacing "default-" by "drug-". Change elastic search host to "localhost" and set use-ssl to true.
* **search.json** : change field document-index-name by "drug-text-index". Change elastic search host to localhost.

Finaly, edit the file **tkeir/runtimes/docker/docker-compose-opendistro.yml** to change, if necessary, the path of the index.
By default it is **/data/index** the path have to be readable and writable for user running docker.
Then run

```shell
#> docker-compose -f docker-compose-opendistro.yml
```

Take care to the error display by opendistro, sometimes there is user rights issues.

For the demo, all is scripted, just go into **demos/quickstart/** and run or edit **quickstart.sh**

### Analyse and index your document

T-Keir depends on Opendistro. We propose a docker compose file to pull and use Opendistro. For this demo, this part of software will be automatically run
in docker compose environement.
Do not forget to setup TRANSFORMERS_CACHE : path to models

To analyse and index document prepared in previous step, you have to run **batch_ingester.py** script from **tkeir** directory:

```shell
python3 thot/batch_ingester.py -c <PATH TO YOUR OUTPUR CONFIGURATION>/project/configs/pipeline.json -i <PATH TO QUICKSTART FOLDER>/data/tkeir -o <PATH TO QUICKSTART FOLDER>/data/tkeir-out
```

or if you install wheel:

```shell
tkeir-batch-ingester -c <PATH TO YOU CONFIGURATION FOLDER>/pipeline.json -i <PATH TO QUICKSTART FOLDER>/data/tkeir -o <PATH TO QUICKSTART FOLDER>/data/tkeir-out
```


After this process, all documents will be indexed. You can query Elastic Search with the following command:

```shell
curl -k https://admin:admin@localhost:9200/drug-text-index/_search | json_pp
```

### Run Search Service

Firstly run Q/A system:

```shell
python3 thot/qa_svc.py -c <PATH TO CONFIG>/qa.json
```

or if you install wheel:

```shell
tkeir-qa-svc -c <PATH TO CONFIG>/qa.json
```


Check health:

```shell
curl http://localhost:10011/api/qa/health
```

Secondly run search service:

```shell
python3 thot/search_svc.py -c <PATH TO CONFIG>/search.json
```

or if you install wheel:

```shell
tkeir-search-svc.py -c <PATH TO CONFIG>/search.json
```

Check health:

```shell
curl http://localhost:9000/api/searching/health
```

Finaly, on full version only (not available for OSS version) run web interface (in tkeir/thot/web/directory):

set path to web interface :

```shell
export WEB_TKEIR_APP=<PATH TO WEB DEMO>
```

```shell
python3 thot/web/manager.py runservice 0.0.0.0:8080 --insecure
```

To visualize a search request you can open firefox on http://<host of web server\>:8080/search

