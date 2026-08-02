Feature: Agent service contracts
  As a persona user
  I want the agent API to list packs and validate run creation
  So that the HMI can start governed agent/workflow runs safely

  @offline
  Scenario: Offline agent harness is wired
    Given the offline harness is ready
    Then the offline harness reports ready

  @live @agent
  Scenario: Agent health identifies the service
    Given the agent service is available
    When I GET "/health" on agent
    Then the response status is 200
    And the JSON field "service" equals "tkeir-agent"

  @live @agent
  Scenario: Agent catalogue is listable
    Given the agent service is available
    When I GET "/agent/agents" on agent
    Then the response status is 200
    And the JSON field "agents" is a list
    When I GET "/agent/workflows" on agent
    Then the response status is 200
    And the JSON field "workflows" is a list

  @live @agent
  Scenario: Create run rejects a missing goal
    Given the agent service is available
    When I POST "/agent/runs" on agent with JSON:
      """
      {"agent": "researcher"}
      """
    Then the response status is one of 400, 422

  @live @agent
  Scenario: Create run rejects an unknown agent
    Given the agent service is available
    When I POST "/agent/runs" on agent with JSON:
      """
      {"agent": "no-such-agent-xyz", "goal": "probe"}
      """
    Then the response status is 404

  @live @agent
  Scenario: Cancel missing run returns 404
    Given the agent service is available
    When I POST "/agent/runs/no-such-run/cancel" on agent with JSON:
      """
      {}
      """
    Then the response status is 404
