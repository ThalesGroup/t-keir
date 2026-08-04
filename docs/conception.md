# Conception

This page is the architectural and algorithmic reference for T-KEIR **2.0.0**:
what each component does, which external libraries it relies on, and which
algorithms were designed or substantially adapted inside the product.

Related pages:

| Topic | Page |
|-------|------|
| Pipeline CLI overview | [Tools overview](tools/tools_overview.md) |
| Per-tool config fields | [tools/](tools/tools_overview.md) |
| Vespa RAG | [Vespa RAG](tools/vespa_rag.md) |
| Deployment | [Deployment](deployment/index.md) |
| Zero to Hero | [zero_to_hero.md](zero_to_hero.md) |

---

## 1. End-to-end architecture

```text
                  ┌─────────────────────────────────────────────────┐
                  │                 Ingest client                    │
                  │  document bytes + ontology bytes (multipart)     │
                  └───────────────────────┬─────────────────────────┘
                                          │ POST /ingest/document
                                          ▼
┌──────────────┐  pipeline   ┌────────────────┐  index   ┌──────────┐
│ tkeir-ingest │ ──────────► │ PipelineRunner │ ───────► │  Vespa   │
│  (FastAPI)   │             │  (in-process)  │          │ streaming│
└──────────────┘             └────────┬───────┘          └────┬─────┘
                                      │                       │
         converter → lang → tokenizer → MS → NER → syntax     │
         → keywords → chunking → ontology → chunk-questions   │
                                                              │
         ┌────────────┐  ┌──────────┐  ┌─────────┐  ┌─────────▼──────┐
         │ tkeir-rag  │  │ tkeir-mcp│  │tkeir-hmi│  │ tkeir-agent    │
         │ hybrid RAG │  │ tools    │  │ Next.js │  │ loops/workflows│
         └─────┬──────┘  └────┬─────┘  └────┬────┘  └───────┬────────┘
               │              │             │               │
               └──────────────┴──────┬──────┴───────────────┘
                                     ▼
                          governor + audit (ActionRecord)
```

**Design principles**

1. **In-process NLP** — one `PipelineRunner` enriches a single JSON document;
   no micro-service hop between tokenizer and ontology.
2. **Client/server separation for content** — ingest never reads client
   filesystem paths for documents or domain ontologies; bytes are uploaded.
3. **Bundled vs domain ontologies** — generic graphs may live under
   `tkeir/resources/ontologies/`; corpus/customer graphs are uploaded per request.
4. **Streaming tenancy** — Vespa groups map to Keycloak principals / `dev@tkeir`.
5. **Governed actions** — ingest, RAG, MCP, and agents share correlation IDs,
   budgets, and kill scopes via `tkeir-governor` / `tkeir-audit`.

---

## 2. Data preparation

Data preparation consists in:

- transforming documents into a format adapted to the tools,
- building terminological and structured resources (gazetteers, MWE tries,
  optional bundled ontologies),
- constructing evaluation data (queries ↔ relevant documents).

### 2.1 Construction of terminological lists

Linguistic resources feed analysis tools so they can extract **domain-typed**
phrases as well as **generic** entities (cities, organizations, licenses, …).

| Artifact | Location | Role |
|----------|----------|------|
| Annotation resource catalog | `resources/modeling/tokenizer/<lang>/annotation-resources.json` | Declares gazetteer files, POS/NER labels, ASCII folding |
| Compiled MWE trie | `resources/modeling/tokenizer/<lang>/tkeir_mwe.pkl` | Runtime multi-word expression store |
| NER / syntactic / keyword rules | `ner-rules.json`, `syntactic-rules.json`, `keywords-rules.json` | Pattern and validation overlays |
| Bundled generic ontologies | `resources/ontologies/` | Optional `derive-from` defaults (product-neutral only) |

Build the trie with `make init-models` / `tkeir-create-annotation-resource`
(`thot.tools.annotation`). Implementation: **`DictionaryTrie`**
(`thot.core.DictionaryTrie`) — nested-dict trie with leaf metadata (label,
weight, POS).

**Example resource entry** (`annotation-resources.json`):

```json
{
  "name": "geoname-country",
  "path": "countryInfo.txt",
  "pos": "PROPN",
  "add-ascii-folding": true,
  "label": "location.country",
  "type": "named-entity",
  "weight": 10
}
```

Libraries used at build/runtime for resources: **fold-to-ascii** (diacritic
folding), **pandas** (tabular gazetteers), **emoji** (emoji handling in text
paths).

### 2.2 Preparation of the evaluation data

Evaluation pairs (queries ↔ relevant documents) measure retrieval quality.
T-KEIR ships a BEIR harness (`tkeir-beir-eval`, optional `beir` dependency).
See [Evaluation](evaluation.md) and the [BEIR evaluation report](evaluation_report.md).

---

## 3. Document analysis pipeline

Pipeline stages (order fixed in `PipelineTasks.TASK_ORDER`):

**converter → language detection → resource selection → tokenizer →
morphosyntax → NER → syntax → keywords → (golden-chunking) → (document-ontology) →
(chunk-questions)**

Orchestration: `thot.tasks.pipeline.PipelineRunner` + `PipelineConfiguration`
(`configs/pipeline.yaml`). CLI: `tkeir-pipeline`.

Shared utilities across stages:

| Utility | Module | Role |
|---------|--------|------|
| Process-wide spaCy cache | `SpacyModelLoader` | Avoid OOM from duplicate `md` model loads |
| Inject pre-tokens into spaCy | `ThotTokenizerToSpacy` | Downstream tags respect T-KEIR segmentation |
| Task metadata | `TaskInfo` | Host/OS/version stamps in `tasks-info` |
| Preserve ingest extras | `_preserve_pipeline_extras` | Keep `ontologies`, `source_doc_id`, `user_space` across converter |

---

### 3.1 Converter

**Purpose.** Normalize heterogeneous sources (raw text, PDF, Office, HTML,
email, …) into a T-KEIR document (`content`, `title`, `source_doc_id`,
`conversion-info`).

| | |
|--|--|
| **Modules** | `thot.tasks.converters.Converter`, `MarkItDownConverter`, `RawTextConverter`, `PdfImageOcr`, `InputFormat` |
| **Config** | `configs/converter.yaml` |
| **Libraries** | **markitdown** (Office/HTML/…), **pymupdf** (PDF), **pytesseract** + **pillow** (OCR), optional vision via `UnifiedLLMWrapper` |

**Algorithms / custom logic**

- **Input format auto-detect** (`InputFormat`) — sniff by extension and magic
  bytes; supports `auto` datatype for CLI/ingest.
- **MarkItDown conversion path** — delegate rich formats, then normalize to
  T-KEIR JSON fields.
- **PDF OCR orchestration** (`PdfImageOcr`) — decide when page text is too
  sparse; run Tesseract and/or LLM vision; merge regions into `content`.
- **`source_doc_id` stamping** — converter and ingest ensure a stable id for
  Vespa (ingest also stamps ids for pre-converted corpus JSON).

---

### 3.2 Language detection & resource selection

**Purpose.** Choose processing language and tokenizer resource directory
(`en` / `fr`).

| | |
|--|--|
| **Modules** | `LanguageDetector`, `ResourceSelector` |
| **Libraries** | **langdetect** |

**Algorithms / custom logic**

- Short-text fallback to default language; code normalization (`en-US` → `en`).
- `ResourceSelector` maps language → `resources/modeling/tokenizer/<lang>`;
  missing languages fall back to `en`/`fr` processing language while recording
  selection metadata on the document.

---

### 3.3 Tokenization

**Purpose.** Segment text into linguistic units (sentences, words, multi-word
expressions). Writes `content_tokens` / `title_tokens`.

| | |
|--|--|
| **Modules** | `Tokenizer`, `SentenceSegmenter`, `DictionaryTrie`, `SpacyTokenizerPipe` |
| **Config** | `configs/tokenizer.yaml` (+ optional MWE) |
| **Libraries** | **spaCy**, **pysbd** (sentence boundaries), **fold-to-ascii** |

#### Segmentation principles

Segmentation is delicate: regular expressions and strategies group compound
words. Rules cover cases such as:

- `.` not always end-of-sentence (English decimals),
- `-` at word edges vs mid-word hyphenation,
- punctuation detachment policies encoded in tokenizer rules JSON.

#### Multi-word expressions (MWE) — Trie

Detached compounds (e.g. “hot dog”) are semantic units. T-KEIR compiles
phrase lists into a **Trie** (`DictionaryTrie`):

1. Offline: gazetteers → `tkeir_mwe.pkl`.
2. Online: walk the trie over tokens; merge matches; attach POS / NER labels
   and weights from leaf metadata.
3. Options: ASCII folding, POS override, named-entity label, weight for
   conflict resolution.

#### Normalization and typo rules

Configurable rewrite lists under `resources/modeling/tokenizer/<lang>/`
(referenced from annotation resources) normalize spelling variants before
downstream tagging.

#### Layout-aware sentence segmentation

`SentenceSegmenter` combines **pysbd** with heuristics that merge/split around
tables, footnotes, and layout noise so morphosyntax sees coherent sentences.

---

### 3.4 Morphosyntax

**Purpose.** Assign POS tags and lemmas to pre-tokenized units. Writes
`content_morphosyntax` / `title_morphosyntax`.

| | |
|--|--|
| **Modules** | `MorphoSyntacticTagger` |
| **Config** | `configs/mstagger.yaml` |
| **Libraries** | **spaCy** (`en_core_web_md` / `fr_core_news_md` via `SpacyModelLoader`) |

**Algorithms / custom logic**

- Feed T-KEIR tokens through **`ThotTokenizerToSpacy`** so spaCy does not
  re-segment MWEs.
- Force morphosyntactic labels from segmentation/MWE (terminology often missed
  by the stock tagger).
- Optional concept pre-tagging that seeds early KG hints.

---

### 3.5 Named entity recognition (NER)

**Purpose.** Label textual spans as typed entities (person, location,
organization, …). Writes `content_ner` / `title_ner`.

| | |
|--|--|
| **Modules** | `NERTagger`, `SpacyNERFromMWE`; optional `OntologyLexicon` |
| **Config** | `configs/nertagger.yaml`; `ner-rules.json` |
| **Libraries** | **spaCy** (statistical NER + `entity_ruler`) |

**Algorithms / custom logic**

1. **Statistical spaCy NER** on morphosyntax-aware docs.
2. **Entity ruler patterns** from `ner-rules.json` (rule-based overlays).
3. **`SpacyNERFromMWE`** — walk MWE trie leaves; keep highest-weight label when
   multiple gazetteers fire.
4. **Label remapping** — spaCy labels → T-KEIR vocabulary (`PERSON` → `person`).
5. **POS validation rules** — discard impossible spans (e.g. city tagged as
   verb-only syntagm) using `ner-pos-validation`.
6. **OntologyLexicon reinforcement** — when the document carries uploaded /
   staged reference ontologies, greedy longest-match of ontology labels into
   token sequences as `concept` spans (no mutation of the shared spaCy model).
7. Merge non-overlapping lexicon/ontology spans with statistical NER.

---

### 3.6 Syntax & SVO knowledge-graph triples

**Purpose.** Recover dependencies and extract (Subject, Verb, Object) triples
that seed the document knowledge graph. Writes `content_deps` and extends
`kg`.

| | |
|--|--|
| **Modules** | `SyntacticTagger` |
| **Config** | `configs/syntactic-tagger.yaml`; `syntactic-rules.json` |
| **Libraries** | **spaCy** (`Matcher`), **numpy** |

**Algorithms / custom logic**

- Remove pure `SPACE` tokens before matching (`remove_tokens_on_match`).
- Apply morphosyntax attributes onto spaCy docs.
- Load **JSON syntactic rules** (phrase / verbal / prepositional patterns)
  into spaCy `Matcher`.
- **Custom SVO extraction** combining matcher spans with dependency paths
  (`nsubj`, `dobj`, auxiliaries, negation).
- Append NER spans as match candidates so named entities participate in SVO.
- When ontologies were uploaded, merge ontology concept spans into NER before
  SVO so syntactic linking stays coherent with reference vocabularies.
- Emit KG triples with field provenance (`content` / `title`).

---

### 3.7 Keywords extraction

**Purpose.** Rank the most salient terms/phrases (word clouds, naïve summary).
Writes `keywords`; may synthesize a missing `title`.

| | |
|--|--|
| **Modules** | `KeywordsExtractor` (`NLTKRake`), `TitleGenerator`, `KeywordRules` |
| **Config** | `configs/keywords.yaml`; `keywords-rules.json` |
| **Libraries** | Uses morphosyntax fields; built-in RAKE (`NLTKRake`, no `nltk` package) |

**Algorithms / custom logic**

- **POS-aware RAKE** (adapted from Rose et al., 2010): candidate phrases are
  sequences between stop POS tags (determiners, conjunctions, …) and
  punctuation; degree/frequency scoring on **lemmas**.
- Validation rules filter noisy candidates.
- **TitleGenerator cascade** — early NER → top keywords → first content
  sentence → line heuristics, with boilerplate/navigation filters.

---

### 3.8 Golden chunking

**Purpose.** Build retrieval-oriented chunks with neighbor context for Vespa
indexing. Writes `golden_chunks`.

| | |
|--|--|
| **Modules** | `GoldenChunker`, `ChunkBuilder`; labels in `chunk_index_labels` |
| **Config** | `configs/golden-chunking.yaml` |
| **Libraries** | Pure Python over pipeline fields |

**Algorithms / custom logic (T-KEIR)**

- **NER-density adaptive windows** — shrink max tokens when entity density is
  high to keep chunks entity-focused.
- **Sentence-span packing** toward min/max token targets.
- **Primary entity ranking** by label priority with noise filters.
- **Implicit subject resolution** — pronouns / demonstratives linked to prior
  SVO subjects (`implicit_subjects` metadata).
- **Context summaries** before/after (`TOPIC`, `ACTIVE_ENTITIES`, …).
- Stable **chunk_id** hashes; search payload with `[CONTEXT_BEFORE]` /
  `[CONTEXT_AFTER]` markers for embedding text.

---

### 3.9 Document ontology

**Purpose.** Materialize a per-document RDF graph, optionally derive links from
reference ontologies, validate with SHACL (self-healing), serialize JSON-LD for
Vespa (`document_ontology` / `json_ld`).

| | |
|--|--|
| **Modules** | `DocumentOntologyBuilder`, `OntologyBuilder`, `OntologyAlignment`, `OntologyDerivation`, `OntologyLexicon`, `OntologyVocabulary`, `OntologyRepairer`, `SelfHealingLoop`, `ShaclValidator`, `ShaclShapes`, `ShaclInductor`, vectorizers |
| **Config** | `configs/document-ontology.yaml` |
| **Libraries** | **rdflib**, **pyshacl**, **scikit-learn** (TF-IDF, agglomerative clustering), **numpy** |

**Pipeline inside the task**

1. **Build** (`OntologyBuilder`) — SVO / NER / keywords → RDF **hypergraph**
   under `http://tkeir.local/ontology/`: Document → Chunk (`SubOntology`) →
   reified `Statement` + shared concepts (`mentionedIn` / `chunkSupport`);
   materialized SPO kept for reasoners. See
   [Document ontology — hypergraph](tools/document_ontology.md#hypergraph-shape-document--chunk--sub-ontology).
2. **Align** (`OntologyAlignment` + `label_vectorizer`) — CamelCase / lemma
   tokenization → TF-IDF → agglomerative clustering of synonymous classes /
   properties; rewrite to a canonical vocabulary.
3. **Triple-context clustering** (`triple_context_vectorizer`) — cluster
   individuals by SVO neighborhood bags.
4. **Derive-from** (`OntologyDerivation`) — load reference OWL/TTL (bundled
   under `resources/ontologies/` **or** absolute staged ingest uploads);
   **lemma Jaccard / containment** matching; emit `rdfs:subClassOf`, extra
   `rdf:type`, `owl:sameAs`; optional axiom copy.
5. **SHACL** — built-in / induced shapes; **`run_self_healing_validation`** +
   **OntologyRepairer** (e.g. Metric numeric literals) with capped repair
   attempts.
6. Serialize JSON-LD + incoherence / text-coverage reports for HMI and Vespa.

Relative `derive-from.paths` resolve **only** via
`default_search_roots()` → `tkeir/resources/ontologies/` (not workspace corpora).

---

### 3.10 Chunk questions

**Purpose.** Attach synthetic retrieval questions to golden chunks for
question-embedding search. Sets readiness flags on chunks.

| | |
|--|--|
| **Modules** | `ChunkQuestionGenerator`, `QuestionBuilder` |
| **Config** | `configs/chunk-questions.yaml` |
| **Libraries** | Template-based (no LLM required) |

**Algorithms / custom logic**

- EN/FR templates driven by SVO, entities, and chunk summaries.
- Deduplication and min/max caps per chunk.

---

## 4. Platform components

### 4.1 Ingest service (`tkeir-ingest`)

**Purpose.** Accept documents, run the pipeline asynchronously, optionally
index into Vespa, persist jobs/manifests/DLQ.

| | |
|--|--|
| **Modules** | `thot.tools.ingest.app`, `worker`, `store`, `manifest`, `fetch`, `ontology_upload`, `shutdown` |
| **Libraries** | **FastAPI**, **uvicorn**, **python-multipart**, **httpx** (Vespa) |
| **Config** | Environment (`INGEST_ROOT`, `INGEST_STOP_ON_FAILED`, auth, …) |

**Custom logic**

- Multipart **document + `ontology_file` bytes**; stage ontologies under
  `INGEST_ROOT/uploaded_ontologies/{id}/` (server never opens client paths).
- Idempotency key = `(content SHA, pipeline config SHA, embedder fingerprint)`.
- `ensure_source_doc_id` for pre-converted JSON corpora.
- `STOP_ON_FAILED` → SIGTERM after first failed job; `POST /ingest/stop` for
  clients.

---

### 4.2 Search / RAG API (`tkeir-rag`)

**Purpose.** Hybrid retrieval and grounded answers over Vespa `global` /
`user` passages.

| | |
|--|--|
| **Modules** | `thot.tools.search.app`, `passage_retrieval`, `vespa_client`, `query_analyzer`, `bge_m3`, `generation_prompt`, `rag_report`; indexing in `thot.tools.ingest.index_passages` |
| **Libraries** | **FastAPI**, Vespa HTTP API, **FlagEmbedding** (local `net/bge-m3`), **rdflib**, **sentence-transformers** / **torch** (optional CE), **httpx**, `UnifiedLLMWrapper` (Ollama / OpenAI / vLLM) |
| **Config** | `configs/rag.yaml` (`dual_hybrid:` block), `rag-prompts.yaml` |

**Custom logic**

- Index NLP `golden_chunks` → passages on `global` and/or `user` (dense 1024-d + sparse + BM25 + `ontology_concepts`).
- **`PassageRetrievalPipeline`** when `dual_hybrid.enabled` — modes `global` / `user` / `both` / `auto`; RRF + lexical + ontology + rerank fusion.
- **QueryAnalyzerTask** — NLP → YQL payload only (legacy single-arm when dual-hybrid off).
- **Generation prompts** — `generation_prompt` for KEY PASSAGES / SVO guidance.
- Tenant **`user_space`** from JWT / `dev@tkeir`.

---

### 4.3 HMI (`tkeir-hmi`)

**Purpose.** Operator UI for RAG, ontology views, admin/correlation, agent runs.

| | |
|--|--|
| **Stack** | **Next.js 15**, **React 19**, **Tailwind**, **Radix**, **next-auth** (Keycloak) |
| **Custom logic** | BFF proxies to RAG/governor/audit; correlation-id deep links |

---

### 4.4 Governor (`tkeir-governor`)

**Purpose.** Kill switches, budgets, approvals, action tokens for all services.
Full ops reference: [Governor deployment](deployment/governor.md).

| | |
|--|--|
| **Libraries** | **FastAPI**; local state store (`GOVERNOR_STATE_ROOT`) |
| **Custom logic** | `PolicyEvaluator` — intent→scope, write gates, observe vs enforce; shared with `AgentGuard` |

---

### 4.5 Audit (`tkeir-audit`)

**Purpose.** Persist ActionRecords; hot query store + WORM archive.
Full ops reference: [Audit store](deployment/audit.md).

| | |
|--|--|
| **Libraries** | **FastAPI**; optional **psycopg**; gzip filesystem |
| **Custom logic** | WORM JSONL.gz segments with SHA-256 sidecars; privacy subject keys |

---

### 4.6 MCP (`tkeir-mcp`)

**Purpose.** HTTP/stdio surface for **external** MCP clients (`search`,
`rag_query`, `ontology_query`, `document_get`). Agents do **not** call this
process; they use the same `McpHandlers` library in-process (see §4.7 and
[MCP docs](tools/mcp.md#who-uses-it-external-vs-agents)).

| | |
|--|--|
| **Libraries** | **FastAPI**; optional **mcp** SDK |
| **Custom logic** | Tool catalog; strip client `user_space` overrides; egress allow-list for outbound MCP used by agents |

---

### 4.7 Agents (`tkeir-agent`)

**Purpose.** Grounded, tool-using agents and sequential multi-agent workflows
over the caller’s Vespa `user_space`. Agents never invent citations: every
claim must carry `chunk_ids` / `document_ids` from tool observations.
Deliverables can be composed through ontology-driven templates and published
only through the governor ApprovalQueue (in enforce mode).

Deep dive: [Agents](tools/agents.md) · [Templates](tools/templates.md) ·
.

| | |
|--|--|
| **Modules** | `service`, `registry`, `workflows`, `loop`, `orchestrator`, `toolbox`, `safety`, `guard`, `runs`, `publish`, `spiffe`, `models` |
| **Libraries** | **FastAPI**, `UnifiedLLMWrapper` (Ollama / OpenAI / vLLM); optional **spiffe**; MCP handlers / outbound client |
| **Config** | `configs/agents/*.yaml`, `configs/workflows/*.yaml`, `configs/templates/*`, `configs/mcp-client.yaml` |
| **Store** | `AGENT_ROOT` (default `workspace/agent/`) — manifests, steps, blackboard, DLQ, publishes |

#### Design principles

1. **No third-party agent frameworks** — custom reason→act→observe loop and
   sequential orchestrator only.
2. **Same retrieval stack as MCP** — tools are allow-listed names executed via
   in-process `McpHandlers` (not via the `tkeir-mcp` HTTP service) plus
   optional egress-filtered outbound MCP tools.
3. **Tenant isolation** — `user_space` from JWT / `VESPA_USER_SPACE`; tool args
   cannot override it; results are checked to match the principal.
4. **Untrusted tool content** — observations wrapped in `<untrusted>`;
   injection / escalation heuristics in `safety.py`.
5. **Governed** — kill scope `agents`, per-run budgets, ActionRecords with
   `actor.spiffe_id` (
   [SPIRE / SPIFFE](deployment/spire.md)).

#### Agent YAML (`configs/agents/`)

Each file defines one role (`AgentSpec`):

| Field | Role |
|-------|------|
| `system_prompt` | Role + strict JSON reply contract |
| `tools` | Allow-list (empty for writer/reviewer) |
| `budgets` | `llm_tokens`, `tool_calls`, `wall_seconds` |
| `stop.max_steps` | Loop ceiling |
| `output_contract` | `grounded_findings_v1`, `grounded_prose_v1`, `review_verdict_v1` |
| `model` / `temperature` | Usually `${LLM_MODEL}` |

| Agent | Tools | Job |
|-------|-------|-----|
| `researcher` | search, rag_query, ontology_query, document_get | Corpus Q&A with citations |
| `analyst` | search, ontology_query, document_get | KG / ontology-oriented analysis |
| `writer` | — | Fill freeform template slots from evidence |
| `reviewer` | — | Accept/reject slots lacking provenance |

#### Workflow YAML (`configs/workflows/`)

Sequential plan (`WorkflowSpec`): ordered **agent** steps then optional
**compose** step. Shipped example `content_brief`:

```text
researcher (search/RAG/ontology + optional echo_cite)
    → Handoff + blackboard
analyst (ontology / KG)
    → Handoff
compose(template=synthesis_note, topic_from=params.topic)
    → compose_result (markdown + citations_map + unfilled)
```

Workflow fields: shared `budgets`, `external_tools`, per-step `goal_template`
(`{goal}`, `{topic}`, …), optional `tools` / `max_steps` overrides, and
`compose.template` pointing at [Templates](tools/templates.md).

#### Single-agent loop (`AgentLoop`)

```text
for step in 1..max_steps:
  guard (kill / budget / cancel)
  LLM(system_prompt + history + tool schemas)
  parse JSON → tool call | final
  if tool: validate allow-list → invoke → wrap <untrusted> → append observation
  if final: keep only findings with chunk_ids/document_ids → succeed
```

Claims without provenance become `unfilled` (never silently accepted).

#### Orchestrator

`Orchestrator.run` loads the workflow, runs each agent step through
`AgentLoop`, records `Handoff` objects, appends to `blackboard.json`, then
runs `thot.compose` for the deliverable. Status lifecycle:
`queued → running → succeeded|failed|blocked|killed|cancelled`.

#### Persistence

```text
AGENT_ROOT/runs/{run_id}/
  run.manifest.json # RunState
  blackboard.json
  steps/NNN.json # StepRecord
jobs/ dlq/ publishes/
```

#### Custom algorithms / policies (T-KEIR)

| Name | Where | Summary |
|------|-------|---------|
| Strict JSON tool/final protocol | `loop.parse_agent_message` | Single fenced object; no free-form tool APIs |
| Provenance filter | `_findings_from_final` | Drop uncited claims → `unfilled` |
| Tool allow-list + schema check | `toolbox.ToolRegistry` | Required args, no extras, tenant strip |
| Untrusted envelope | `safety.wrap_untrusted` | Isolate tool text from instructions |
| Injection / escalation refuse | `safety.detect_injection` | Heuristic redaction / refusal |
| Sequential handoff blackboard | `orchestrator` + `runs` | Explicit provenance between phases |
| Budget throttle / block | `guard.AgentGuard` | 80% / 100% of limits + ApprovalQueue |
| Approval-gated publish | `publish.py` | `origin=agent-generated` staging |

---

## 5. Library map (by concern)

| Concern | Libraries |
|---------|-----------|
| NLP tagging | **spaCy 3.6**, language models `en`/`fr`/`xx` |
| Sentence split | **pysbd** |
| Conversion / OCR | **markitdown**, **pymupdf**, **pytesseract**, **pillow** |
| Language ID | **langdetect** |
| RDF / SHACL | **rdflib**, **pyshacl** |
| Clustering / vectors | **scikit-learn**, **numpy**, **sentence-transformers**, **torch**, **transformers** |
| Search | Vespa (HTTP), **httpx** |
| APIs | **FastAPI**, **uvicorn**, **python-multipart** |
| Observability | **OpenTelemetry** → Prometheus |
| Templating | **Jinja2** |
| Text utils | **beautifulsoup4**, **emoji**, **fold-to-ascii**, **pandas** |
| HMI | **Next.js**, **React**, **next-auth** |
| Optional | **mcp**, **spiffe**, **beir** (eval), **psycopg** (audit) |

---

## 6. Catalog of T-KEIR-designed algorithms

| Name | Where | Summary |
|------|-------|---------|
| **MWE Trie** | `DictionaryTrie` | Nested-dict multi-word lexicon with labels/weights |
| **SpacyModelLoader cache** | `SpacyModelLoader` | Process-wide spaCy cache + model fallbacks |
| **ThotTokenizerToSpacy** | `Utils` | Inject pre-tokens into spaCy |
| **Layout SentenceSegmenter** | `SentenceSegmenter` | pysbd + layout merge heuristics |
| **SpacyNERFromMWE** | `NERTagger` | Gazetteer NER via trie walk + weight argmax |
| **OntologyLexicon match** | `OntologyLexicon` | Greedy ontology-label spans on tokens |
| **Custom SVO + rules** | `SyntacticTagger` | Dependency + JSON Matcher SVO extraction |
| **POS-aware RAKE** | `KeywordsExtractor` | RAKE on lemmas with POS stop sets |
| **TitleGenerator** | `TitleGenerator` | Cascaded title recovery |
| **GoldenChunker** | `ChunkBuilder` | Adaptive packing, anaphora, context payloads |
| **OntologyBuilder** | `OntologyBuilder` | Pipeline fields → RDF document graph |
| **Label TF-IDF + clustering** | `OntologyAlignment` | Synonym class/property merge |
| **Triple-context clustering** | `triple_context_vectorizer` | Entity clusters from SVO neighborhoods |
| **OntologyDerivation** | `OntologyDerivation` | Lemma Jaccard/containment → subclass/type/sameAs |
| **SHACL self-heal** | `run_self_healing_validation`, `OntologyRepairer` | Validate → repair → re-validate |
| **Synthetic questions** | `QuestionBuilder` | Template EN/FR chunk questions |
| **QueryAnalyzerTask** | `query_analyzer` | NLP-driven Vespa profile/YQL selection |
| **SVO-ontology RAG prompt** | `rag_report` / `app` | Passages + triples prompting |
| **User-space tenancy** | `user_space` | JWT → Vespa streaming group |
| **Ingest ontology staging** | `ontology_upload` | Client bytes → server-local derive-from paths |
| **WORM audit segments** | `worm_store` | Write-once hashed archives |
| **Governor PolicyEvaluator** | `policy` | Intent/scope/kill/budget matrix |
| **Agent grounded loop** | `loop`, `safety` | JSON tool/final protocol + uncited → unfilled |
| **Tool allow-list invoke** | `toolbox.ToolRegistry` | Schema check, tenant strip, `<untrusted>` wrap |
| **Sequential orchestrator** | `orchestrator`, `workflows` | YAML plan → handoffs → template compose |
| **Approval-gated publish** | `publish` | Stage `origin=agent-generated` via ApprovalQueue |
| **Pipeline task graph** | `PipelineTasks` | Dependency expansion + skip-if-present |

---

## 7. Configuration index

| Component | Config |
|-----------|--------|
| Pipeline umbrella | `configs/pipeline.yaml` |
| Converter | `configs/converter.yaml` |
| Tokenizer | `configs/tokenizer.yaml` |
| Morphosyntax | `configs/mstagger.yaml` |
| NER | `configs/nertagger.yaml` |
| Syntax | `configs/syntactic-tagger.yaml` |
| Keywords | `configs/keywords.yaml` |
| Golden chunking | `configs/golden-chunking.yaml` |
| Document ontology | `configs/document-ontology.yaml` |
| Chunk questions | `configs/chunk-questions.yaml` |
| RAG | `configs/rag.yaml`, `rag-prompts.yaml` |
| MCP | `configs/mcp.yaml`, `mcp-client.yaml` |
| Agents / workflows | `configs/agents/*`, `configs/workflows/*` |
| Ingest / governor / audit | Environment variables (see each `config.py`) |

---

## 8. Operational data flow (analysis → retrieval)

```text
Source bytes
  → Converter (+ OCR)
  → LanguageDetector → ResourceSelector
  → Tokenizer (regex + MWE Trie)
  → Morphosyntax (spaCy + forced MWE tags)
  → NER (spaCy + MWE + OntologyLexicon)
  → Syntax (Matcher + SVO → kg)
  → Keywords (POS-RAKE) + TitleGenerator
  → GoldenChunker
  → DocumentOntology (build → align → derive → SHACL heal)
  → ChunkQuestions
  → Vespa (parent + chunks + embeddings)
  → RAG / MCP / Agents / HMI
```
