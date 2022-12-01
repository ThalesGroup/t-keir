
curl -k -XPOST --header "content-Type: application/json" "https://localhost:8000/api/searching/querying" -d'
{ 
  "from":0,
  "size":5,
  "content":"Is there a dataset from Earth Observation ?",
  "options":{
    "exclude":["summary","sentiment","categories","text_suggester","lemma_title","lemma_content","content"],
    "disable":["qa","aggregator"]    
  },
  "add-clause":{
    "type":"must",
    "clause": {
      "bool":{
        "must":[
          {"wildcard":{"source_doc_id":"https://www.ai4europe.eu/research/ai-catalog*"}},
          {"match":{"content":"dataset"}},
          {"match":{"content":"agriculture"}},
          {"match":{"content":"knowledge representation"}}
	      ]
      }
    }
  }
}'

curl -k -XPOST --header "content-Type: application/json" "https://localhost:8000/api/searching/querying" -d'
{ 
  "from":0,
  "size":5,
  "content":"What is YOLO ?",
  "options":{
    "exclude":["summary","sentiment","categories","text_suggester","lemma_title","lemma_content"],
    "disable":["qa","aggregator"]    
  },
  "add-clause":{
    "type":"must",
    "clause": {
      "bool":{
        "must":[
          {"wildcard":{"source_doc_id":"https://www.ai4europe.eu/research/ai-catalog*"}},
          {"match":{"content":"physical ai"}},
          {"match":{"content":"computer vision"}},
          {"match":{"content":"trustworthy ai"}}
	      ]
      }
    }
  }
}'

curl -k -XPOST --header "content-Type: application/json" "https://localhost:8000/api/searching/querying" -d'
{ 
  "from":0,
  "size":5,
  "content":"What is VSAM ?",
  "options":{
    "exclude":["summary","sentiment","categories","text_suggester","lemma_title","lemma_content"],
    "disable":["qa","aggregator"]    
  },
  "add-clause":{
    "type":"must",
    "clause": {
      "bool":{
        "must":[
          {"wildcard":{"source_doc_id":"https://www.ai4europe.eu/research/ai-catalog*"}},
          {"match":{"content":"physical ai"}}
	      ]
      }
    }
  }
}'


