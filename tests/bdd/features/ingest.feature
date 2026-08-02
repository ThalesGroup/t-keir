Feature: Document ingest API
  As an admin
  I want the ingest service to expose health and accept status probes
  So that corpus indexation can be monitored

  @offline
  Scenario: Offline ingest steps are wired
    Given the offline harness is ready
    Then the offline harness reports ready

  @live @ingest
  Scenario: Ingest health returns success
    Given the ingest service is available
    When I GET "/health" on ingest
    Then the response status is 200

  @live @ingest
  Scenario: Ingest ready is healthy or degraded
    Given the ingest service is available
    When I GET "/ready" on ingest
    Then the response status is one of 200, 503

  @live @ingest
  Scenario: Unknown ingest id returns 404
    Given the ingest service is available
    When I GET "/ingest/status/zzzzzzzzzzzzzzzzzzzzzzzzzz" on ingest
    Then the response status is 404

  @live @ingest
  Scenario: Tiny document upload is accepted
    Given the ingest service is available
    When I upload a tiny text document to ingest
    Then the response status is 202
    And the JSON body has fields:
      | field          |
      | ingest_id      |
      | correlation_id |
    When I GET the last ingest job status
    Then the response status is 200
    And the ingest status is terminal or in-flight
