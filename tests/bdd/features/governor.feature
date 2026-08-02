Feature: Governor runtime flags
  As an operator
  I want governor flags to be readable and kill scopes controllable
  So that emergency stops can protect ingest and inference

  @offline
  Scenario: Offline governor harness is wired
    Given the offline harness is ready
    Then the offline harness reports ready

  @live @governor
  Scenario: Governor flags are readable
    Given the governor service is available
    When I GET "/governor/flags" on governor
    Then the response status is 200
    And the JSON body has field "scopes"

  @live @governor
  Scenario: Governor kill toggle for ingest scope
    Given the governor service is available
    When I POST "/governor/kill" on governor with JSON:
      """
      {"scope": "ingest", "active": true, "reason": "bdd-smoke"}
      """
    Then the response status is one of 200, 401, 403
    When I POST "/governor/kill" on governor with JSON:
      """
      {"scope": "ingest", "active": false, "reason": "bdd-smoke-clear"}
      """
    Then the response status is one of 200, 401, 403
