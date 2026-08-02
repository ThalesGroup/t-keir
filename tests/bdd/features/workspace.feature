Feature: My files workspace API
  As an analyst
  I want personal workspace tree/upload/status endpoints
  So that My files can store documents before indexing

  @offline
  Scenario: Offline workspace harness is wired
    Given the offline harness is ready
    Then the offline harness reports ready

  @live @ingest
  Scenario: Workspace tree lists the user root
    Given the ingest service is available
    When I GET "/workspace/tree" on ingest
    Then the response status is 200
    And the JSON body has fields:
      | field      |
      | user_space |
      | entries    |
    And the JSON field "entries" is a list

  @live @ingest
  Scenario: Workspace mkdir creates a directory
    Given the ingest service is available
    When I POST "/workspace/mkdir" on ingest with JSON:
      """
      {"path": "bdd-smoke"}
      """
    Then the response status is 200
    And the JSON field "kind" equals "directory"

  @live @ingest
  Scenario: Workspace upload stores a file without indexing
    Given the ingest service is available
    When I upload workspace file "bdd-smoke/note.md" without indexing
    Then the response status is one of 200, 202

  @live @ingest
  Scenario: Workspace status accepts selected paths
    Given the ingest service is available
    When I POST "/workspace/status" on ingest with JSON:
      """
      {"paths": ["bdd-smoke/note.md", "missing-file.md"]}
      """
    Then the response status is 200
    And the JSON body has fields:
      | field |
      | total |
      | done  |
      | files |

  @live @ingest
  Scenario: Workspace rejects path traversal
    Given the ingest service is available
    When I GET "/workspace/file?path=../etc/passwd" on ingest
    Then the response status is 400
