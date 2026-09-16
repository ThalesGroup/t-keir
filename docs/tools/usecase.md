# Create a usecase pack

A **usecase** is a folder under `datasets/<name>/` that bundles corpus,
business ontology, agent/workflow YAML, Keycloak personas, and HMI presets.
It is **not** a copy of `tkeir/configs/` (those YAML files are product-wide —
[Configuration](../configuration/index.md)). A pack answers: *who logs in, what
they search, which report form they get, which ontology expands queries*.

The shipped reference is **OSINT** ([`datasets/osint/`](../../datasets/osint/)).
Enterprise ([`datasets/enterprise/`](../../datasets/enterprise/)) is a second
pack with the same contract. Select a pack with Makefile `USECASE=` or
`USECASE=<name> ./start_services.sh` (default **osint**).

This page walks the OSINT tree file-by-file, then shows how to clone it.

Restricted or private corpora stay **out of git**. Add the pack directory to
`.gitignore` and do **not** add unit tests that require that pack.

---

## 1. What OSINT actually wires

`USECASE=osint` (the default) does four things at once:

| Env / artefact | Value | Effect |
|----------------|-------|--------|
| `TKEIR_USECASE` / `TKEIR_AGENT_USECASE` | `osint` | Agent registry prefers `datasets/osint/agents/` and `…/workflows/` |
| `TKEIR_BUSINESS_ONTOLOGY_DATASET` | `osint` | Ingest/RAG load `datasets/osint/business_ontology.yaml` |
| `make keycloak-up` | `datasets/osint/keycloak.json` | Creates `analyst`, `moc-watch`, `humint`, `commander`, `c2-admin` |
| `make hmi-up` | copies `hmi.json` → `tkeir-hmi/public/usecase.json` | Persona switcher, Reporter presets, login table |

Product YAML (`tkeir/configs/rag.yaml`, pipeline, OTAN templates) stays shared.
The pack **selects** which of those templates and which personas apply.

```text
datasets/osint/
  keycloak.json                 # users + roles (sync)
  hmi.json                      # HMI personas + Reporter presets
  agent_orchestrator.yaml       # report_form → template + slot hints
  business_ontology.yaml        # query expansion / annotation concepts
  c2_middle_east_multi_source_1000_v3_en.json   # json-records corpus
  agents/                       # persona analyser/reviewer/writer + *_prompt
  workflows/                    # persona_* + llm_wiki + otan_c2_brief
  userdata/                     # optional personal notes for demo users
  ontologies/                   # C2SIM OWL (upload at ingest; not auto-scanned)
  README_agents.md              # pack-local agent index
```

`<name>` must match `USECASE` / `TKEIR_USECASE` (lowercase, no spaces).

---

## 2. OSINT as the worked example

### 2.1 Corpus

OSINT ships versioned json-records, for example
`c2_middle_east_multi_source_1000_v3_en.json`: `{ "dataset": {…}, "records": [
{ "doc_id", "title", "text", … } ] }`. Each record becomes one markdown
document; extra fields become ontology concepts.

Admin indexes the **shared / global** corpus (`index_target: global`). Query
users search `user` + global.

```bash
make datasets-ingest USECASE=osint          # demo client (OSINT + enterprise)
# any other pack name:
make datasets-ingest USECASE=my_pack        # datasets/my_pack/my_pack.json
```

Build JSON from files: [Corpus](corpus.md).

```bash
make corpus CORPUS_INPUT=./notes \
  CORPUS_OUTPUT=./datasets/my_pack/my_pack.json CORPUS_NAME=my_pack
```

### 2.2 Business ontology

`datasets/osint/business_ontology.yaml` is a `concepts:` list
(`concept_id`, `preferred_label`, `synonyms`, `broader` / `narrower`). Dual-hybrid
uses it for query expansion and index-time concepts when
`dual_hybrid.business_ontology` is on ([rag.yaml](../configuration/rag.yaml.md)).

OSINT’s spine is C4ISR (situational awareness, intelligence, operations) with
maritime / AIS children grounded in the corpus field values. **Your pack**
should use concept ids that actually appear in *your* records — copy the YAML
shape, not the ship names.

Add the folder id to `tkeir-hmi/lib/business-ontology-datasets.ts` if operators
must pick it manually. `NEXT_PUBLIC_TKEIR_USECASE` already defaults the picker
to the active pack name.

Collector `topics.yaml` already has `topics.osint.business_ontology_dataset:
osint`. A new pack needs a matching topic row:
[Collector YAML](../configuration/collector.yaml.md#topicsyaml).

### 2.3 Keycloak (`keycloak.json`)

OSINT roles: `c2-j2-analyst`, `c2-moc-watch`, `c2-j2x-humint`,
`c2-ctf-commander`, `c2-admin` (the last **composites** `tkeir-admin` +
`tkeir-user` so it can index global data). Users: `analyst` / `moc-watch` /
`humint` / `commander` / `c2-admin` (passwords equal usernames in the demo).

| Field | Effect |
|-------|--------|
| `roles[].name` | Realm role. Must match `hmi.json` `personas[].roles` and `pageRoles`. |
| `roles[].composites` | Extra platform roles. **Admin** packs must include `tkeir-admin` (OSINT: `c2-admin`). |
| `users[].username` / `password` | Login gate. Listed in `hmi.json` `demoAccounts`. |
| `users[].email` | Becomes Vespa `user_space` when signed in. |
| `users[].clearance` | Shown in the HMI; governor/audit metadata. |
| `users[].roles` | Assigned realm roles. Operators need `tkeir-user` plus the pack role. |
| `verify` | Smoke user for `make keycloak-up` health check. |

Plain JSON — the sync script does not use PyYAML.

```bash
make keycloak-up USECASE=osint
```

Sync is idempotent. Platform accounts `demo-user` / `demo-admin` /
`demo-auditor` are always created. `make down` purges usernames listed in
**every** `datasets/*/keycloak.json` plus the platform demos.

Do not bake private personas into `deploy/keycloak/realm-tkeir.json`; first
boot imports that file once, then the sync script applies the pack.

### 2.4 HMI (`hmi.json`)

`make hmi-up` copies `datasets/$(USECASE)/hmi.json` →
`tkeir-hmi/public/usecase.json` (gitignored). Missing file falls back to OSINT
defaults.

OSINT maps five personas to five Reporter presets (INTSUM, SITREP, SPOTREP,
commander brief, admin INTSUM).

| Field | Effect |
|-------|--------|
| `personas[].id` | Switcher id (`analyst`, `moc-watch`, …). |
| `personas[].label` | Display name. |
| `personas[].roles` | Keycloak roles that activate this persona. Admin includes `tkeir-admin`. |
| `workflowPresets[].role` | Which login role gets this Reporter default. |
| `workflowPresets[].personaId` | Must match a `personas[].id`. |
| `workflowPresets[].reportForm` | Alias (`intsum`, `sitrep`, …) resolved by `agent_orchestrator.yaml`. |
| `workflowPresets[].goal` / `topic` | Prefills the Reporter form. |
| `workflowPresets[].workflow` | Agent workflow stem (`persona_j2_analyst`). Must exist under `workflows/`. |
| `workflowPresets[].wikiPrompt` | `*_prompt` agent name for OKF wiki merge (`j2_analyst_prompt`). |
| `workflowPresets[].answerTemplate` | Compose template stem (`otan_intsum`). |
| `pageRoles` | Who may open Search / Agents / Audit. |
| `adminRoles` | Who may open `/admin`. |
| `ingestRoles` | Who sees global ingest. |
| `shareRoles` | Who may share docs to another persona’s space. |
| `demoAccounts` | Login-gate table (must match Keycloak users). |

```bash
make hmi-up USECASE=osint
```

### 2.5 Agent orchestrator (`agent_orchestrator.yaml`)

OSINT `name: osint`, `default_report_form: intsum`.

| Field | Effect |
|-------|--------|
| `name` | Pack id (informational; selection is `USECASE`). |
| `default_report_form` | Used when the HMI omits `report_form`. |
| `report_form_templates` | Maps aliases (`intsum` → `otan_intsum`) to compose YAML stems under `tkeir/configs/templates/` or `datasets/<pack>/templates/`. Wrong stem → compose cannot load the template. |
| `report_form_slot_hints` | Injected into writer/analyser goals as `{report_form_slots}`. This is how OSINT writers know INTSUM sections 1–5. |

### 2.6 Agents and workflows

Naming contract (OSINT J2 analyst):

| File | `name:` | Role |
|------|---------|------|
| `agents/j2_analyst_analyser.yaml` | `j2_analyst_analyser` | Tool loop: search / rag / ontology → grounded findings |
| `agents/j2_analyst_reviewer.yaml` | `j2_analyst_reviewer` | No tools; drop uncited claims |
| `agents/j2_analyst_writer.yaml` | `j2_analyst_writer` | Slot-tagged claims for compose |
| `agents/j2_analyst_prompt.yaml` | `j2_analyst_prompt` | **Not** a tool agent — `wiki_merge_system_prompt` + `wiki_structured_facts_seed` for Reporter Phase 2 |
| `workflows/persona_j2_analyst.yaml` | `persona_j2_analyst` | analyse → review → write → `compose.template: otan_intsum` |
| `agents/wiki_writer.yaml` | `wiki_writer` | Shared wiki writer |
| `workflows/llm_wiki.yaml` | `llm_wiki` | OKF iterative wiki builtin |

YAML keys: [Agents, workflows, and templates](../configuration/agents.yaml.md).
Pack-local index: [`datasets/osint/README_agents.md`](../../datasets/osint/README_agents.md).

Workflow `goal_template` placeholders used by OSINT:

- `{goal}` `{topic}` `{report_form}` `{report_form_slots}`
- `{wiki_markdown}` `{has_llm_wiki}` `{bundle_id}` `{prior_findings_json}`

If Reporter Phase 3 sends an edited LLM wiki, OSINT analysers treat it as the
**primary** fact base and only search to fill gaps. New packs should keep that
split or writers will re-research from scratch and ignore the wiki.

Wiki sources list is **append-only**: later folds add `[S(n+1)]`, never
renumber.

Colliding stems (`wiki_writer`, `llm_wiki`, `persona_admin`) resolve to the
active `USECASE` pack first.

### 2.7 Templates

OSINT reuses **product** templates `otan_intsum`, `otan_sitrep`,
`otan_spotrep`, `otan_commander_brief` in `tkeir/configs/templates/`. A private
pack should copy those YAML files into `datasets/<name>/templates/` and rename
slots rather than editing the OTAN files in place.

### 2.8 Optional userdata

`datasets/osint/userdata/` holds per-demo-user notes (markdown/JSON) ingested
into that user’s streaming index. Skip if the pack is global-corpus only.

---

## 3. Clone OSINT into a new pack

Example pack name: `maritime` (replace everywhere).

```bash
cp -R datasets/osint datasets/maritime
# then rename files/ids inside — do not leave c2-* roles if you do not need NATO C2
```

Minimum edits:

1. **`keycloak.json`** — new role names and users (keep one composite
   `tkeir-admin` user for global ingest).
2. **`hmi.json`** — `personas`, `workflowPresets`, `demoAccounts`, role lists
   aligned with Keycloak.
3. **`agent_orchestrator.yaml`** — `name: maritime`, `report_form_templates`
   pointing at *your* template stems.
4. **`business_ontology.yaml`** — concepts from *your* corpus, not RED SEA EAGLE.
5. **Corpus** — `datasets/maritime/maritime.json` (or set `JSON_RECORDS_PATH=`).
6. **Agents** — rename `j2_analyst_*` → `maritime_watch_*` (file stem **and**
   YAML `name:`). Update `workflows/persona_*.yaml` `steps[].agent`.
7. **`tkeir/configs/collector/topics.yaml`** — add `topics.maritime` with
   `business_ontology_dataset: maritime` (or workspace overlay).
8. **HMI picker** — add `maritime` in `tkeir-hmi/lib/business-ontology-datasets.ts`
   if it must appear in the ontology dropdown.

Four-section query report (same as OSINT wiki contract):

1. Short answer  
2. Detailed answer — inline `[S1]`, `[S2]`, … matching the sources list  
3. Keywords  
4. Sources — numbered, append-only  

---

## 4. Run it

```bash
export USECASE=maritime          # or pass USECASE= on each make
make bootstrap
make keycloak-up
make ingest
make rag
make agent
make hmi-up
make datasets-ingest             # json-records for non-osint packs
```

One-shot hybrid demo (tmux): the same env selects Keycloak, agents, RAG
ontology, and HMI presets.

```bash
USECASE=osint ./start_services.sh
USECASE=enterprise ./start_services.sh
USECASE=maritime ./start_services.sh
```

Equivalent env (set automatically by Make and `start_services.sh`):
`TKEIR_USECASE`, `TKEIR_AGENT_USECASE`, `TKEIR_BUSINESS_ONTOLOGY_DATASET`.

Compose: the same variables in `deploy/compose/.env`. Agent images only
embed the **shipped** OSINT (and enterprise orchestrator) packs; mount
`datasets/<name>/` or copy agents into the image for a private pack.

---

## 5. Checklist (copy OSINT, then tick)

- [ ] Folder `datasets/<name>/` with `name` = `USECASE`
- [ ] `keycloak.json` users login; admin has `tkeir-admin`
- [ ] `hmi.json` personas / presets / `demoAccounts` match Keycloak
- [ ] `agent_orchestrator.yaml` aliases resolve to real template stems
- [ ] Each query persona has `_analyser`, `_reviewer`, `_writer`, `_prompt`
- [ ] `workflows/persona_<id>.yaml` `name:` matches `workflowPresets[].workflow`
- [ ] `business_ontology.yaml` concept ids appear in the corpus
- [ ] Corpus JSON is `{dataset, records}` and ingest uses `index_target: global` for the admin
- [ ] Collector `topics.<name>` exists if you collect web docs into this pack
- [ ] `USECASE=<name> ./start_services.sh` — login as pack user, Search hits, Reporter compose succeeds

---

## 6. What not to version

- Large or classified JSON corpora  
- The whole `datasets/<private>/` tree if the project is restricted  
- Unit tests that `parametrize` that pack name or assert on its agent stems  
- Keycloak users in `realm-tkeir.json` for that pack  

Keep this document, the OSINT pack, and the generic `USECASE=` wiring in the
public tree.

---

## Related

| Topic | Page |
|-------|------|
| Product YAML field effects | [Configuration](../configuration/index.md) |
| Agent / workflow / template keys | [Agents YAML](../configuration/agents.yaml.md) |
| Runtime agents | [Agents](agents.md) |
| Datasets & C2SIM OWL | [Datasets](datasets.md) |
| Demo launcher | [start_services.sh](../deployment/start_services.md) |
