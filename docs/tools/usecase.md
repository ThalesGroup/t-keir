# Create a usecase pack

A **usecase** is a folder under `datasets/<name>/` that bundles corpus,
business ontology, agent/workflow YAML, Keycloak personas, and HMI presets.
The shipped references are [`datasets/osint/`](../../datasets/osint/) and
[`datasets/enterprise/`](../../datasets/enterprise/). Select a pack with
Makefile `USECASE=` or `USECASE=<name> ./start_services.sh` (default **osint**).

Restricted or private corpora stay **out of git**. Add the pack directory to
`.gitignore` and do **not** add unit tests that require that pack. This guide
is the contract the runtime uses.

## 1. Layout

Copy the OSINT skeleton, then rename personas and templates:

```text
datasets/<name>/
  README.md
  keycloak.json                 # roles + users (synced by make keycloak-up)
  hmi.json                      # HMI personas, wiki presets, demo accounts
  agent_orchestrator.yaml       # default_report_form + template maps
  business_ontology.yaml        # dual-hybrid expansion / annotation
  <name>.json                   # {dataset, records} corpus (or corpus.jsonl)
  agents/
    <persona>_analyser.yaml
    <persona>_reviewer.yaml
    <persona>_writer.yaml
    <persona>_prompt.yaml       # OKF wiki merge system (Reporter)
    wiki_writer.yaml
  workflows/
    persona_<persona>.yaml      # analyse → review → write → compose
    llm_wiki.yaml
  templates/                    # optional; searched before tkeir/configs/templates/
    <report>.yaml
  userdata/                     # optional personal notes for demo users
```

`<name>` must match `USECASE` / `TKEIR_USECASE` (lowercase, no spaces).

## 2. Corpus

Ingest uses `POST /ingest/json-records` with `dataset_path` under `datasets/`.

**From markdown or a mixed-format tree** (see [Corpus](corpus.md)):

```bash
make corpus CORPUS_INPUT=./notes CORPUS_OUTPUT=./datasets/my_pack/my_pack.json CORPUS_NAME=my_pack
make corpus CORPUS_INPUT=./raw-files \
  CORPUS_MARKDOWN_DIR=./datasets/my_pack/markdown \
  CORPUS_OUTPUT=./datasets/my_pack/my_pack.json \
  CORPUS_NAME=my_pack
```

**Existing JSON** must be `{ "dataset": {…}, "records": [ { "doc_id", "title", "text", … } ] }`.
Each record becomes one markdown document; extra fields become ontology concepts.

Admin indexes the **shared / global** corpus (`index_target: global`). Query
users stay on the personal `user` index plus global search.

```bash
make ingest USECASE=my_pack
make datasets-ingest USECASE=my_pack          # json-records, default 100 hits
make datasets-ingest USECASE=my_pack JSON_RECORDS_LIMIT=all
```

`datasets-ingest` with `USECASE=osint` still runs the OSINT+Enterprise demo
client. Any other pack name uses json-records on
`datasets/<usecase>/<usecase>.json` (override with `JSON_RECORDS_PATH=`).

## 3. Business ontology

Commit `business_ontology.yaml` with a `concepts:` list (`concept_id`,
`preferred_label`, `synonyms`, `broader` / `narrower`). Ingest and RAG load
`datasets/<TKEIR_BUSINESS_ONTOLOGY_DATASET>/business_ontology.yaml`. Makefile
sets that env to `$(USECASE)`.

Add the folder id to the HMI picker in
`tkeir-hmi/lib/business-ontology-datasets.ts` if operators should select it
manually; `NEXT_PUBLIC_TKEIR_USECASE` already defaults the picker to the
active pack name.

## 4. Agents, wiki, and compose templates

Mirror OSINT: each query persona needs `_analyser`, `_reviewer`, `_writer`,
and `_prompt`. The prompt’s `wiki_merge_system_prompt` defines the wiki
sections. For a four-section query report:

1. Short answer  
2. Detailed answer — inline `[S1]`, `[S2]`, … matching the sources list  
3. Keywords  
4. Sources — numbered, **append-only** (later wiki folds add `[S(n+1)]`, never
   renumber)

Put the compose YAML in `datasets/<name>/templates/<report>.yaml` (preferred
for private packs) or `tkeir/configs/templates/`. `agent_orchestrator.yaml`
maps `report_form` aliases → template stems and slot hints.

Workflow `persona_<id>` should `compose.template` that same stem. Reporter
Phase 3 sends `wiki_markdown` into the analyser; keep `[Sn]` cross-references
in the detailed slot.

Colliding stems (`wiki_writer`, `llm_wiki`, `persona_admin`) resolve to the
active `USECASE` pack first.

## 5. Keycloak

`datasets/<name>/keycloak.json` (plain JSON — the sync script does not use
PyYAML):

```json
{
  "roles": [
    {
      "name": "my-admin",
      "description": "Corpus administrator",
      "composites": ["tkeir-admin", "tkeir-user", "tkeir-operator"]
    },
    { "name": "my-operator", "description": "Query / wiki / reports" }
  ],
  "users": [
    {
      "username": "my-admin",
      "email": "my-admin@tkeir",
      "firstName": "My",
      "lastName": "Admin",
      "clearance": "UNCLASSIFIED",
      "password": "my-admin",
      "roles": ["my-admin", "tkeir-admin"]
    },
    {
      "username": "operator",
      "email": "operator@tkeir",
      "firstName": "My",
      "lastName": "Operator",
      "clearance": "UNCLASSIFIED",
      "password": "operator",
      "roles": ["my-operator", "tkeir-user"]
    }
  ],
  "verify": {
    "username": "operator",
    "password": "operator",
    "role": "my-operator",
    "clearance": "UNCLASSIFIED"
  }
}
```

- **Admin** (index global data): composite including `tkeir-admin` (same idea
  as OSINT `c2-admin`).
- **Operator / analyst** (query + wiki): `tkeir-user` plus a pack role.

```bash
make keycloak-up USECASE=my_pack
```

Sync is idempotent. Platform accounts `demo-user` / `demo-admin` /
`demo-auditor` are always created. `make down` purges usernames listed in
**every** `datasets/*/keycloak.json` plus the platform demos.

Do not bake private personas into `deploy/keycloak/realm-tkeir.json`; first
boot imports that file once, then the sync script applies the pack.

## 6. HMI (`hmi.json`)

`make hmi-up` copies `datasets/$(USECASE)/hmi.json` →
`tkeir-hmi/public/usecase.json` (gitignored). Fields:

| Field | Purpose |
|-------|---------|
| `personas` | Switcher entries (`id`, `label`, `roles`) |
| `workflowPresets` | Reporter / Agents: `workflow`, `wikiPrompt`, `answerTemplate`, `reportForm`, default `goal` / `topic` |
| `pageRoles` | Search, Agents, Audit (`RequireRole`) |
| `adminRoles` | `/admin` |
| `ingestRoles` | Global ingest sidebar |
| `shareRoles` | Share-to-other-persona |
| `demoAccounts` | Login gate table |

See [`datasets/osint/hmi.json`](../../datasets/osint/hmi.json). Missing file
falls back to OSINT defaults.

```bash
make hmi-up USECASE=my_pack
```

## 7. Run the stack

```bash
export USECASE=my_pack          # or pass USECASE= on each make
make bootstrap
make keycloak-up
make ingest
make rag
make agent
make hmi-up
make datasets-ingest            # json-records for non-osint packs
```

One-shot hybrid demo (tmux): the same env selects Keycloak, agents, RAG
ontology, and HMI presets.

```bash
USECASE=osint ./start_services.sh
USECASE=enterprise ./start_services.sh
USECASE=my_pack ./start_services.sh
```

Equivalent env (set automatically by Make and `start_services.sh`):
`TKEIR_USECASE`, `TKEIR_AGENT_USECASE`, `TKEIR_BUSINESS_ONTOLOGY_DATASET`.

Compose: the same variables in `deploy/compose/.env`. Agent images only
embed the **shipped** OSINT (and enterprise orchestrator) packs; mount
`datasets/<name>/` or copy agents into the image for a private pack.

## 8. What not to version

- Large or classified JSON corpora  
- The whole `datasets/<private>/` tree if the project is restricted  
- Unit tests that `parametrize` that pack name or assert on its agent stems  
- Keycloak users in `realm-tkeir.json` for that pack  

Keep this document, the OSINT pack, and the generic `USECASE=` wiring in the
public tree.
