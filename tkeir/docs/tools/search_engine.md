# Search engine

## Index

Document indexing is the step allowing to store in the elastic search the document
analyzed during the steps of tokenization, tagging, keyword extraction ...


### Indexing configuration

Example of Configuration:


```json title="indexing.json"
--8<-- "./app/projects/template/configs/indexing.json"
```

The indexing configuration is an aggreation of serialize configuration, logger (at top level).
The the indexing configuration needs an ElasticSearch :

- **document/remove-knowledge-graph-duplicates**: in the analyzed document knowledge graph items are positions wise, to avoid duplication in the index you can suppress position an thus make items uniq
- **elasticsearch/network**: network configuration of E.S.
- **elasticsearch/nms-index**: index containing vectors (obsolete),
- **elasticsearch/text-index**: index containing analyzed textual document,
- **elasticsearch/relation-index**: index containing relations (obsolete),

### Run Index process

To run the command type simply from tkeir directory:

```shell
python3 thot/tkeir2index --config=<path to indexing configuration file> -d <directory to index> -t document
```

Another way is to use index service (here each document are indexed separately, with tkeir2index we use bulk that is much more efficient)

```shell
python3 thot/index_svc --config=<path to indexing configuration file>
```

It is possible to use a quick client:

```shell
python3 thot/index_client --config=<path to indexing configuration file> -i <path to tkeir document>
```

## Search

Search component can be see as a proxy to ElasticSearch (E.S.). Nonetheless, it allows to create specifc E.S
queries based on query analysis. It also allows to manipulate ranking scores.

### Search API


!!swagger searching.json!!

### Search Configuration

Example of Configuration:

```json title="search.json"
--8<-- "./app/projects/template/configs/search.json"
```

The search configuration allows to set up the search behaviour according the query analysis. The other configuration are not specific to the service.

- searching/document-index-name: the name of the index where are stored the documents
- searching/disable-document-analysis : document analysis is not mandatory and can be disable
- searching/qa/host : question answering sub system host
- searching/qa/port : question answering sub system port
- searching/qa/max-question-size: max size of the question (to run qa subsystem)
- searching/qa/max-ranked-doc: max number of ranked document where is appy Q/A
- searching/qa/use-ssl: qa subsystem access by ssl
- searching/qa/no-ssl-verify: qa subsystem access verify certificates
- searching/suggester/number-of-suggestions: max number of suggestions
- searching/suggester/spell-check: Not yet implemented
- searching/aggregator/host: hostname of searx
- searching/aggregator/port": port of searx
- searching/aggregator/index": index (or not) searx results
- searching/aggregator/engines": searx engines used
- searching/aggregator/index-pipeline":index pipeline network configuration
- searching/search-policy/semantic-cluster/semantic-quantizer-model : path to clustering model to use "statistical" semantic
- searching/search-policy/settings/basic-querying/uniq-word-query : transform query in bag of word
- searching/search-policy/settings/basic-querying/boosted-uniq-word-query : weigthening words according to their frequency in query
- searching/search-policy/settings/basic-querying/cut-query": maximum number of uniq word with the query
- searching/search-policy/settings/advanced-querying/use-lemma:use lemmatised field of index
- searching/search-policy/settings/advanced-querying/use-keywords: use keywords field of index
- searching/search-policy/settings/advanced-querying/use-knowledge-graph: use knowledge graph (the triple) of index
- searching/search-policy/settings/advanced-querying/use-concepts: use concepts of the index
- searching/search-policy/settings/advanced-querying/use-sentences: use sentence querying
- searching/search-policy/settings/advanced-querying/querying/match-phrase-slop: slop in match phrase clause
- searching/search-policy/settings/advanced-querying/querying/match-phrase-boosting: default boosting value for match phrase
- searching/search-policy/settings/advanced-querying/querying/match-sentence/number-and-symbol-filtering": filter symbol andnumber from sentences
- searching/search-policy/settings/advanced-querying/querying/match-sentence/max-number-of-words: set the maximum length (words) in the sentence
- searching/search-policy/settings/advanced-querying/querying/match-keywords/match-keyword/number-and-symbol-filtering": filter number and symbols
- searching/search-policy/settings/advanced-querying/querying/match-keywords/semantic-skip-highest-ranked-classes: when you use semantic class (comming from clustering) the most common classes are often irrelevant, you can skip this classes
- searching/search-policy/settings/advanced-querying/querying/match-keywords/semantic-max-boosting": query boosting in match-phrase clause
- searching/search-policy/settings/advanced-querying/querying/match-svo/semantic-use-class-triple : create query clause with all semantic classes
- searching/search-policy/settings/advanced-querying/querying/match-svo/semantic-use-lemma-property-object": use lemma on subject, class on property and object
- searching/search-policy/settings/advanced-querying/querying/match-svo/semantic-use-subject-lemma-object": use lemma on property, class on subject and object
- searching/search-policy/settings/advanced-querying/querying/match-svo/semantic-use-subject-property-lemma": use lemma on object, class on subject an property
- searching/search-policy/settings/advanced-querying/querying/match-svo/semantic-use-lemma-lemma-object": use lemma on subject and property, class on object
- searching/search-policy/settings/advanced-querying/querying/match-svo/semantic-use-lemma-property-lemma": use lemma on subject ad object, class on property
- searching/search-policy/settings/advanced-querying/querying/match-svo/semantic-use-subject-lemma-lemma": use lemma on property and object, class on subject
- searching/search-policy/settings/advanced-querying/querying/match-svo/semanic-max-boosting":no yet implement
- searching/search-policy/settings/advanced-querying/querying/match-concept/concept-boosting: boost concept clause
- searching/search-policy/settings/advanced-querying/querying/match-concept/concept-pruning: top N of concept used
- searching/search-policy/settings/query-expansion/term-pruning: max number of term used in expansion
- searching/search-policy/settings/query-expansion/suppress-number: filter number
- searching/search-policy/settings/query-expansion/suppress-numberkeep-word-collection-thresold-under : frequency of document where the word appear should lesser than this frequency
- searching/search-policy/settings/query-expansion/word-boost-thresold-above: frequency of word in the document should be greater than this number
- searching/search-policy/settings/scoring/normalize-score: normalize elastic search score max score max
- searching/search-policy/settings/scoring/document-query-intersection-penalty: document and query intersection normalized : no-normalization, by-query-size, by-union-size(jaccard)
- searching/search-policy/settings/scoring/run-clause-separately: clause can be run separately in this case the ranked lists are merged, or put in a uniq query
- searching/search-policy/settings/scoring/expand-results": when you run clause separately and merge result it is interesting to expand result list size to cover more ranked documents
- searching/search-policy/settings/results/set-highlight: highlight snippets
- searching/search-policy/settings/results/see-also/number-of-cross-links: compute see-also graph with number of cross links docs per ranked doc
- searching/search-policy/settings/resultsexcludes : excluded some fields from returned list

### Configure Search Network

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


### Configure Search runtime

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

### Run Search engine service

To run the command type simply from tkeir directory:

```shell
python3 thot/search_svc.py --config=<path to relation configuration file>
```
