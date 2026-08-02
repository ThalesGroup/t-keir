Feature: RAG search and health
  As an analyst
  I want the RAG API to expose health and search endpoints
  So that the workbench can retrieve evidence safely

  @offline
  Scenario: Offline harness is wired
    Given the offline harness is ready
    Then the offline harness reports ready

  @live @rag
  Scenario: RAG health returns success
    Given the RAG service is available
    When I GET "/health"
    Then the response status is 200

  @live @rag
  Scenario: RAG ready is healthy or degraded
    Given the RAG service is available
    When I GET "/ready"
    Then the response status is one of 200, 503

  @live @rag
  Scenario: Search rejects an empty query
    Given the RAG service is available
    When I POST "/search" with JSON:
      """
      {"query": "", "hits": 5}
      """
    Then the response status is one of 400, 422

  @live @rag
  Scenario: Search rejects a missing query field
    Given the RAG service is available
    When I POST "/search" with JSON:
      """
      {}
      """
    Then the response status is one of 400, 422

  @live @rag
  Scenario: Search accepts a smoke query shape
    Given the RAG service is available
    When I POST "/search" with JSON:
      """
      {"query": "smoke coverage probe", "hits": 1, "language": "en"}
      """
    Then the response status is one of 200, 502, 503

  @live @rag
  Scenario: RAG query rejects an empty query
    Given the RAG service is available
    When I POST "/rag/query" with JSON:
      """
      {"query": "", "hits": 5}
      """
    Then the response status is one of 400, 422

  @live @rag
  Scenario: RAG query accepts a smoke query shape
    Given the RAG service is available
    When I POST "/rag/query" with JSON:
      """
      {"query": "smoke coverage probe", "hits": 1, "language": "en"}
      """
    Then the response status is one of 200, 502, 503
