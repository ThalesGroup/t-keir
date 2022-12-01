#!/bin/bash

curl -k --header 'apikey: [API_KEY]' -XGET https://localhost:8443/converter/1.0/api/converter/health | json_pp
curl -k --header 'apikey: [API_KEY]' -XGET https://localhost:8443/tokenizer/1.0/api/tokenizer/health | json_pp
curl -k --header 'apikey: [API_KEY]' -XGET https://localhost:8443/mstagger/1.0/api/mstagger/health | json_pp
curl -k --header 'apikey: [API_KEY]' -XGET https://localhost:8443/nertagger/1.0/api/nertagger/health | json_pp
curl -k --header 'apikey: [API_KEY]' -XGET https://localhost:8443/syntax/1.0/api/syntactictagger/health | json_pp
curl -k --header 'apikey: [API_KEY]' -XGET https://localhost:8443/embeddings/1.0/api/embeddings/health  | json_pp
curl -k --header 'apikey: [API_KEY]' -XGET https://localhost:8443/pipeline/1.0/api/pipeline/health | json_pp
curl -k --header 'apikey: [API_KEY]' -XGET https://localhost:8443/keywords/1.0/api/keywordsextractor/health | json_pp
curl -k --header 'apikey: [API_KEY]' -XGET https://localhost:8443/summarizer/1.0/api/summarizer/health | json_pp
curl -k --header 'apikey: [API_KEY]' -XGET https://localhost:8443/sentiment/1.0/api/sentimentclassifier/health | json_pp
curl -k --header 'apikey: [API_KEY]' -XGET https://localhost:8443/classfier/1.0/api/zeroshotclassifier/health | json_pp
curl -k --header 'apikey: [API_KEY]' -XGET https://localhost:8443/qa/1.0/api/qa/health | json_pp
curl -k --header 'apikey: [API_KEY]' -XGET https://localhost:8443/index/1.0/api/indexing/health | json_pp
curl -k --header 'apikey: [API_KEY]' -XGET https://localhost:8443/clusterinfer/1.0/api/clusterinfer/health | json_pp


