# Data model and schemas

Class diagrams and storage ERDs derived from `tkeir/thot/*/models.py`,
JSON schemas under `tkeir/thot/*/schemas/`, and Vespa schemas in
`vespa/vespa_app/schemas/`.

## Core domain — ActionRecord

Source: `thot/action/models.py`, schema `thot/action/schemas/action.v1.json`.

```mermaid
classDiagram
  class ActionRecord {
    +str schema_id
    +str action_id
    +str correlation_id
    +ActorInfo actor
    +list~DelegationHop~ delegation_chain
    +IntentInfo intent
    +ActionContext context
    +DecisionInfo decision
    +ExecutionInfo execution
    +ResultInfo result
    +BudgetConsumed budget
    +dict ext
  }
  class ActorInfo {
    +Literal type
    +str id
    +str spiffe_id
    +str session_id
  }
  class IntentInfo {
    +str declared
    +Literal scope_source
    +str mandate_ref
  }
  class ActionContext {
    +str env
    +str service
    +ContextVersions versions
    +str request_hash
  }
  class DecisionInfo {
    +Literal policy_result
    +list rules_fired
  }
  class ExecutionInfo {
    +str started_at
    +str ended_at
    +Literal status
  }
  class ResultInfo {
    +list chunk_ids
    +list document_ids
    +str error
  }
  ActionRecord --> ActorInfo
  ActionRecord --> IntentInfo
  ActionRecord --> ActionContext
  ActionRecord --> DecisionInfo
  ActionRecord --> ExecutionInfo
  ActionRecord --> ResultInfo
```

## Agent / workflow models

Source: `thot/agent/models.py`.

```mermaid
classDiagram
  class RunState {
    +str run_id
    +str agent
    +str workflow
    +str goal
    +str user_space
    +str spiffe_id
    +str correlation_id
    +Literal status
    +BudgetLimits budgets
    +BudgetUsage usage
    +GroundedFindings result
    +list~Handoff~ handoffs
  }
  class AgentSpec {
    +str name
    +int version
    +str system_prompt
    +list tools
    +BudgetLimits budgets
  }
  class StepRecord {
    +int step_index
    +ToolCall tool_call
    +Literal status
    +str action_id
  }
  class WorkflowSpec {
    +str name
    +list~WorkflowStep~ steps
  }
  class BudgetLimits {
    +int llm_tokens
    +int tool_calls
    +int wall_seconds
  }
  RunState --> BudgetLimits
  RunState --> StepRecord
  AgentSpec --> BudgetLimits
  WorkflowSpec --> RunState : drives
```

## Ingest models

Source: `thot/tools/ingest/models.py`, schema `thot/tools/ingest/schemas/ingest.manifest.v1.json`.

```mermaid
classDiagram
  class IngestManifest {
    +str ingest_id
    +str doc_id
    +SourceInfo source
    +str pipeline_config_sha256
    +EmbedderInfo embedder
    +LineageInfo lineage
  }
  class IngestJob {
    +str ingest_id
    +IngestJobStatus status
    +str correlation_id
  }
  class DocumentIngestRequest {
    +bytes/content source
    +dict metadata
  }
  IngestJob --> IngestManifest
  DocumentIngestRequest --> IngestJob : creates
```

## Governor models

Source: `thot/governor/models.py`.

```mermaid
classDiagram
  class RuntimeFlags {
    +KillSwitchState kill
  }
  class KillSwitchState {
    +bool all
    +bool ingest
    +bool index
    +bool inference
    +bool agents
    +bool hmi_write
  }
  class ApprovalItem {
    +str approval_id
    +str correlation_id
    +str actor_id
    +str intent
    +str reason
  }
  class BudgetSnapshot {
    +str actor_id
    +float consumed
    +float limit
  }
  RuntimeFlags --> KillSwitchState
```

## Vespa storage ERD

Schemas: `vespa/vespa_app/schemas/doc_base.sd`, `global.sd`, `user.sd`.
`user` uses streaming groups (`userspace_id` / `streaming.groupname`);
`global` is index-mode (shared catalog).

```mermaid
erDiagram
  DOC_BASE ||--|| GLOBAL : inherits
  DOC_BASE ||--|| USER : inherits
  DOC_BASE {
    string source_ref
    string chunk_text
    tensor sparse_vector
    array_string ontology_concepts
  }
  GLOBAL {
    tensor dense_vector_hnsw
  }
  USER {
    string userspace_id
    tensor dense_vector
  }
```

`dense_vector` is declared on each child (not in `doc_base`): Vespa forbids
overriding parent fields, and `global` needs HNSW while `user` needs
attribute-only streaming NN.

Passages are indexed by `thot.tools.ingest.index_passages` (BGE-M3 dense + sparse). Retrieval is
`PassageRetrievalPipeline` (`global` / `user` / `both` / `auto`).

Parent documents carry optional `document_ontology.json_ld` produced by
`thot.tasks.document_ontology` (see [Document ontology](../tools/document_ontology.md)).

Checkpoint: field names above match the `.sd` files and Pydantic models in
`thot/*/models.py`.
