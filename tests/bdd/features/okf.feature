Feature: OKF bundle API
  As an analyst
  I want OKF bundles to be listable and missing ids to 404
  So that wiki/export workflows have a stable contract

  @offline
  Scenario: Offline OKF harness is wired
    Given the offline harness is ready
    Then the offline harness reports ready

  @live @okf
  Scenario: OKF lists bundles for the caller
    Given the OKF service is available
    When I GET "/okf/bundles" on okf
    Then the response status is 200

  @live @okf
  Scenario: Missing OKF bundle returns 404
    Given the OKF service is available
    When I GET "/okf/bundles/no-such-bundle-id" on okf
    Then the response status is 404
