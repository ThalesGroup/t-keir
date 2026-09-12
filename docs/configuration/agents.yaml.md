# Agents, workflows, and templates — field effects

Product-neutral YAML lives under `tkeir/configs/`. **Usecase packs** add more
files under `datasets/<usecase>/` (OSINT is the reference:
[Create a usecase pack](../tools/usecase.md)).

Discovery order for colliding stems (`wiki_writer`, `persona_admin`, …):
**active `USECASE` pack first**, then other `datasets/*/`, then
`tkeir/configs/`.

---

## Agent YAML (`tkeir/configs/agents/*.yaml`)

Loaded by `thot.agent.registry` into `AgentSpec`. Example:
`analyst.yaml`, `researcher.yaml`, `writer.yaml`, `reviewer.yaml`,
`okf_wiki_prompt.yaml`.

| Field | Default | Effect |
|-------|---------|--------|
| `name` | required | Registry key. HMI / `POST /agent/runs` `{ "agent": "<name>" }` and workflow `steps[].agent` must match this string. |
| `version` | `1` | Integer recorded on the spec; not a compatibility gate. |
| `role` | `""` | Human label in logs / HMI. Not used for authz. |
| `system_prompt` | `""` | LLM system message for the ReAct loop. For `*_prompt` wiki agents this is **not** the merge prompt — see `wiki_merge_system_prompt`. |
| `model` | `${LLM_MODEL}` | Expanded from env. Wrong name → Ollama/vLLM errors on first token. |
| `tools` | `[]` | Allow-list. Unknown names fail at invoke. Empty = no tools (writer/reviewer/wiki-prompt). Typical: `search`, `rag_query`, `ontology_query`, `document_get`, plus OKF helpers (`okf_bundle_get`, `workspace_wiki_*`). |
| `budgets.llm_tokens` | `20000` | Hard stop when cumulative completion tokens exceed this. |
| `budgets.tool_calls` | `15` | Hard stop on tool invocations. |
| `budgets.wall_seconds` | `300` | Wall-clock cap for the agent phase. |
| `budgets.docs_written` | `0` | `0` means unlimited. Governor also enforces platform budgets. |
| `stop.max_steps` | `12` | Max reason→act iterations even if budgets remain. |
| `output_contract` | `grounded_findings_v1` | Expected final JSON (`findings[]` with `chunk_ids`). |
| `temperature` | `0.0` | Sampling temperature. Writers often `0.2`; analysts `0.1`. |
| `terminal_tools` | `[]` | If a listed tool returns `ok: true`, the loop ends without waiting for `final: true`. |
| `wiki_merge_system_prompt` | `""` | **OKF LLM Wiki fold** system prompt (Reporter Phase 2). Empty → generic OKF merge. Persona files (`j2_analyst_prompt`) put INTSUM/SITREP checklists here. |
| `wiki_structured_facts_seed` | `""` | Markdown injected into the wiki seed (`## Structured facts …`). Empty → Answer/Evidence/Sources only. |
| `wiki_information_priority_keys` | `[]` | Substrings that reorder compact `## Information` lines in the wiki prompt. Empty = file order. |

`okf_wiki_prompt.yaml` is **not** a tool-loop agent: the orchestrator reads
`wiki_*` only. Do not put `search` on it.

Runtime (governor, kill switch): [Agents](../tools/agents.md).

---

## Workflow YAML (`tkeir/configs/workflows/*.yaml`)

Loaded into `WorkflowSpec`. Example: `content_brief.yaml`,
`rag_with_wiki.yaml`, `okf_wiki_brief.yaml`.

| Field | Default | Effect |
|-------|---------|--------|
| `name` | required | `POST /agent/runs` `{ "workflow": "<name>" }` and HMI `workflowPresets[].workflow`. |
| `version` / `description` | `1` / `""` | Metadata. |
| `template` | `null` | Default compose template stem if a step omits `compose.template`. |
| `budgets.*` | see agents | Caps the **whole** workflow (sum of steps). |
| `external_tools` | `[]` | Extra MCP tool names allowed for outbound calls (`mcp-client.yaml` egress). Example: `echo_cite`. |
| `steps[]` | required | Sequential plan. |

### `steps[]`

| Field | Default | Effect |
|-------|---------|--------|
| `id` | `""` | Handoff / blackboard key. Must be unique in the file. |
| `agent` | `null` | Run this `AgentSpec`. Mutually exclusive with a pure `compose` / `builtin` step. |
| `goal_template` | `{goal}` | Format string. Placeholders: `{goal}`, `{topic}`, `{report_form}`, `{report_form_slots}`, `{prior_findings_json}`, `{wiki_markdown}`, `{has_llm_wiki}`, `{bundle_id}`, … Missing keys become empty strings. |
| `tools` | `null` | If set, **overrides** the agent YAML allow-list for this step only. `[]` = no tools (reviewer). |
| `max_steps` | `null` | Overrides `stop.max_steps` for this step. |
| `compose.template` | `synthesis_note` | Ontology-driven fill of `tkeir/configs/templates/<stem>.yaml` or `datasets/<usecase>/templates/<stem>.yaml`. |
| `compose.topic_from` | `goal` | Which run param becomes the compose topic (`goal` vs `topic`). |
| `builtin` | `null` | Named engine builtin (OKF wiki upsert / iterative fold). Used by wiki workflows instead of an LLM agent. |
| `params_from` | `[]` | Copy listed run-param names into the step. |
| `output_key` | `null` | Store step output under this blackboard key for later `{placeholders}`. |

OSINT persona workflows (`datasets/osint/workflows/persona_j2_analyst.yaml`)
are analyse → review → write → compose. Copy that shape for a new pack.

---

## Template YAML (`tkeir/configs/templates/*.yaml`)

Loaded by `thot.compose`. Slot types: `entity`, `svo_pattern`, `keyword`,
`sparql`, `freeform_grounded`. Ungroundable slots go to `unfilled` — they are
never hallucinated.

| Field | Effect |
|-------|--------|
| `name` | Stem referenced by workflows / `agent_orchestrator.yaml` `report_form_templates`. |
| `version` | Integer metadata. |
| `title` / `description` | HMI / markdown heading. |
| `slots[].name` | Placeholder in `markdown_template` and writer `[slot]` tags. |
| `slots[].type` | How the composer fills the slot from the fused graph vs LLM. |
| `slots[].description` | Fed to the writer as a hint. |
| `slots[].label` | Optional display override. |
| `slots[].constraints.required` | Missing required slot → listed in `unfilled`, compose still succeeds. |
| `slots[].constraints.min_items` / `max_items` | Cardinality for list-like types. |
| `markdown_template` | Jinja-like markdown. Empty slots omit their `{% if %}` blocks. |

Shipped stems include `synthesis_note`, `entity_profile`, `nato_synthesis_note`,
and OTAN C2 forms (`otan_intsum`, `otan_sitrep`, `otan_spotrep`,
`otan_commander_brief`) used by the **OSINT** pack. A pack may override by
shipping the same stem under `datasets/<usecase>/templates/`.

See [Templates](../tools/templates.md).

---

## `rag-prompts.yaml`

Path: `tkeir/configs/rag-prompts.yaml`  
Loaded by the RAG app (`/rag/query`) and answer-generation eval. **Does not
change ranking** — only the generation strings.

Top-level keys are **language codes** (`en`, `fr`, …). Unknown request
language falls back to `en`.

| Field (per language) | Effect |
|----------------------|--------|
| `unavailable_answer` | Exact short-answer string when no passage supports a reply. Also the parser fallback. Changing it without updating eval goldens breaks “unavailable” detection. |
| `no_chunks_message` | Shown when retrieval returned nothing. |
| `system` | System prompt. May interpolate `{unavailable_answer}`. |
| `user` | Default user skeleton (`chunk_context_mode: chunk_excerpts` path). Placeholders: `{generation_guidance}`, `{query_analysis}`, `{fused_graph_triples_or_summary}`, `{focus_passages}`, `{chunk_excerpts}`, `{query_text}`, `{unavailable_answer}`. |
| `user_svo` | Used when `rag.yaml` → `prompt.chunk_context_mode` is `svo_ontology` (shipped default). Same placeholders. |

Keep `SHORT_ANSWER:` / `DETAILED_REPORT:` markers — `parse_structured_generation`
splits on them. Removing the markers yields an empty detailed report.

Companion: [rag.yaml](rag.yaml.md#rag-promptsyaml).

---

## Related

- Pack-level maps (`hmi.json`, `agent_orchestrator.yaml`): [Create a usecase pack](../tools/usecase.md)  
- Outbound MCP allow-list: [mcp.yaml](mcp.yaml.md)
