# -*- coding: utf-8 -*-
"""Built-in SHACL shapes for document ontology validation."""

DOCUMENT_SHACL_SHAPES_TTL = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix tkeir: <http://tkeir.local/ontology/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

tkeir:ProductOwnershipShape a sh:NodeShape ;
  sh:targetClass tkeir:Product ;
  sh:property [
    sh:path [
      sh:alternativePath (
        tkeir:ownedBy
        tkeir:createdBy
        tkeir:publishedBy
      )
    ] ;
    sh:class tkeir:Company ;
    sh:minCount 1 ;
    sh:message "A Product must be owned or created by a Company." ;
  ] .

tkeir:MetricNumericValueShape a sh:NodeShape ;
  sh:targetClass tkeir:Metric ;
  sh:property [
    sh:path tkeir:hasNumericValue ;
    sh:datatype xsd:decimal ;
    sh:minCount 1 ;
    sh:message "A Financial Metric must have a numeric object target." ;
  ] .
"""
