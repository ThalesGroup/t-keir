Feature: Multi-service health matrix
  As an operator
  I want every T-KEIR service to expose a stable health contract
  So that Compose / Helm probes and the HMI can detect outages

  @offline
  Scenario: Offline health harness is wired
    Given the offline harness is ready
    Then the offline harness reports ready

  @live @rag
  Scenario: RAG health is ok
    Given the RAG service is available
    When I GET "/health"
    Then the response status is 200

  @live @ingest
  Scenario: Ingest health is ok
    Given the ingest service is available
    When I GET "/health" on ingest
    Then the response status is 200

  @live @agent
  Scenario: Agent health identifies the service
    Given the agent service is available
    When I GET "/health" on agent
    Then the response status is 200
    And the JSON field "service" equals "tkeir-agent"

  @live @governor
  Scenario: Governor health is ok
    Given the governor service is available
    When I GET "/health" on governor
    Then the response status is 200
    And the JSON field "status" equals "ok"

  @live @okf
  Scenario: OKF health is ok
    Given the OKF service is available
    When I GET "/health" on okf
    Then the response status is 200

  @live @audit
  Scenario: Audit health is ok
    Given the audit service is available
    When I GET "/health" on audit
    Then the response status is 200
