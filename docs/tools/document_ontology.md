# Document ontology

Pipeline task that builds an RDF **document ontology** from analyzed T-KEIR
content (KG / NER / keywords / SVO), optionally **links it to external
reference ontologies**, validates with SHACL, and stores JSON-LD on the
document for Vespa (`document_ontology.json_ld`).

Config: `tkeir/configs/document-ontology.yaml`.  
Implementation: `thot.tasks.document_ontology`.

---

## Document ontology vs external ontology

| Graph | What it is | Namespace / origin |
|-------|------------|--------------------|
| **Document ontology** | Per-document RDF built from *this* text (entities, classes, SVO triples, keywords) | `http://tkeir.local/…` via `OntologyBuilder` |
| **External (reference) ontology** | Pre-existing domain / standards graph (OWL, TTL, RDF, JSON-LD) | e.g. C2SIM, customer OWL — **not** invented by the pipeline |

External ontologies are **not** substituted for the document graph. They are
used in two complementary ways:

1. **Upstream reinforcement** — labels become `concept` NER spans so analysis
   (syntax / KG) already sees domain vocabulary.
2. **Downstream derivation (merge by linking)** — after the document RDF exists,
   matching classes/individuals get bridging triples (`rdfs:subClassOf`,
   extra `rdf:type`, `owl:sameAs`), optionally plus copied axioms.

```text
  External ontology files (bundled and/or ingest-uploaded bytes)
           │
           ├──────────────────────────────┐
           ▼                              ▼
   OntologyLexicon                 OntologyDerivation
   (label phrases)                 (RDF linking)
           │                              │
           ▼                              ▼
   NER + syntax / SVO / kg     document RDF ←── build + align
           │                              │
           └──────────────┬───────────────┘
                          ▼
                 SHACL self-heal → json_ld (Vespa)
```

---

## End-to-end merge flow

### Phase A — Build the document ontology (no external merge yet)

`DocumentOntologyBuilder.build()`:

1. **Vocabulary alignment** — cluster synonymous labels from the document
   (`OntologyAlignment` / TF-IDF).
2. **`build_document_graph`** — SVO, NER, keywords → RDF under the T-KEIR
   namespace (classes, individuals, properties, metrics).
3. **Graph alignment** — rewrite synonymous class/property URIs to a canonical
   vocabulary inside the document graph.

At this point the graph is **document-only**. External URIs are not yet present
unless they already appeared as literal labels in the text.

### Phase B — Derive / merge from external ontologies

If `derive-from` is enabled **or** the document carries staged ontology paths
(`ontologies` / `derive_from_ontologies`):

1. **Resolve paths** — `derivation_paths_for_document()` merges:
   - config `derive-from.paths` (relative → `tkeir/resources/ontologies/`, or
     absolute / ingest-staged paths), and
   - per-document paths stamped by ingest after uploading ontology **bytes**.
2. **Load & union references** — `load_reference_graph()` parses each file
   (TTL / OWL / RDF / JSON-LD) into one **reference** `rdflib.Graph`.
3. **Extract concepts** — labeled `owl:Class` / individuals / properties
   (`extract_reference_concepts`).
4. **Match & link** — `derive_document_graph()` compares document labels to
   reference labels and **adds linking triples into the document graph**
   (the reference graph is not wholesale copied unless configured).
5. Continue with SHACL induction / self-heal and JSON-LD serialization.

**Important:** default merge is **bridge triples**, not a full ontology union.
The document graph keeps its T-KEIR URIs; external URIs appear as *targets* of
`subClassOf` / `type` / `sameAs` (and optionally as subjects/objects of copied
axioms).

---

## How matching works

Label similarity (`_score_labels` in `OntologyDerivation`):

| Score | Condition |
|------:|-----------|
| `1.0` | Exact match after normalize (lowercase, collapse whitespace) |
| `0.92` | One normalized label **contains** the other |
| `≥ 0.95` | Same lemma bag after CamelCase / plural stripping (e.g. `GroundUnits` ↔ `Ground Unit`) |
| Jaccard | Otherwise: lemma-set Jaccard over both labels |

A match is accepted only if score ≥ `similarity-threshold` (default **0.8**).
For each document node, the **best** reference concept of the allowed kind wins.

Links written into the **document** graph:

| Document side | Reference side | Triple added |
|---------------|----------------|--------------|
| Document class (TKEIR `rdf:type` object) | Reference class | `docClass rdfs:subClassOf refClass` |
| Labeled individual | Reference class | `docIndividual rdf:type refClass` (extra type) |
| Labeled individual | Reference individual | `docIndividual owl:sameAs refIndividual` |

Optional `include-matched-axioms: true` copies reference triples that mention
matched URIs (subject or object) into the document graph — a deeper merge when
you need neighborhood axioms (labels, hierarchy edges, etc.) next to the
bridges.

Report fields land under `document_ontology.derivation`
(`status`, `matches`, `subclass_links`, `type_links`, `same_as_links`, `paths`,
and full `details` when `save-derivation` / `save-report` is on).

---

## Upstream use: external ontology → NER / syntax (before document ontology)

Before the ontology task runs, the same file paths on the document feed
`OntologyLexicon`:

1. Load reference graphs and collect `rdfs:label` phrases (classes /
   individuals / properties).
2. Greedy longest-match over `title_tokens` / `content_tokens`.
3. Emit NER-style spans with label **`concept`**.
4. **NER** merges them with statistical / MWE entities; **syntax** merges them
   again so SVO extraction can treat ontology terms as first-class entities.

That improves the **document** KG that `OntologyBuilder` later turns into RDF,
so derive-from matching has richer, more coherent labels to align.

```text
ontology labels  →  concept spans  →  better SVO / kg  →  richer document RDF
                                                              ↓
                                              derive-from links to same ontology
```

---

## Where external ontologies come from

**Sources (application-independent):**

| Source | Where |
|--------|--------|
| Bundled generic graphs | `tkeir/resources/ontologies/` (relative names in config) |
| Absolute paths | Operator-mounted files, or ingest-staged uploads under `INGEST_ROOT` |
| Per-request (preferred for domain/corpus) | Client uploads file **bytes** — server never opens client paths |

Corpus demo ontologies (`datasets/osint/ontologies/`) are **not**
searched by the server; upload them with the document.

Relative `derive-from.paths` resolve only via `default_search_roots()`
(`tkeir/resources/ontologies/`, optional `TKEIR_ONTOLOGY_ROOT`). Absolute paths
(e.g. `${INGEST_ROOT}/uploaded_ontologies/{id}/…`) resolve directly.

### Config (bundled / mounted)

```yaml
document-ontology:
  builders:
    - derive-from:
        enabled: true
        paths:
          - example-domain.ttl   # → tkeir/resources/ontologies/example-domain.ttl
        similarity-threshold: 0.8
        match-classes: true
        match-individuals: true
        add-subclass-links: true
        add-type-links: true
        add-same-as-links: true
        include-matched-axioms: false
      save-derivation: true
```

Default ship config keeps `enabled: false` and empty `paths`; prefer per-request
uploads for domain graphs.

### Per-document upload (ingest)

```bash
curl -F "file=@doc.txt" \
  -F "ontology_file=@/client/path/domain.ttl" \
  -F "ontology_file=@/client/path/reference.owl" \
  http://localhost:8091/ingest/document
```

JSON equivalent: `ontologies: [{filename, content_base64}, ...]`.

Ingest stages bytes under `INGEST_ROOT/uploaded_ontologies/{id}/`, stamps
**server-local** paths on the document (`ontologies` /
`derive_from_ontologies`), and passes those to NER / syntax / document-ontology.
Client path strings in metadata are rejected (HTTP 400) — only staged uploads
count for derive-from at ingest time.

`make datasets-ingest` reads `--ontology-dir` on the **client** and uploads each
file’s bytes with OSINT documents. The ingest service stays corpus-agnostic.

Per-document paths **enable derivation even when** config `derive-from.enabled`
is `false` (builder flips settings on when paths are present).

---

## What is *not* merged

- External ontologies are **not** used as a drop-in replacement for the document
  graph.
- By default the full reference TBox/ABox is **not** copied into Vespa — only
  bridge triples (unless `include-matched-axioms`).
- Workspace / corpus directories are **not** auto-discovered on the server.
- Client filesystem paths are **not** opened by ingest or the ontology task.

---

## Modules

| Module | Role in merge / use |
|--------|---------------------|
| `OntologyLexicon` | External labels → `concept` NER spans (upstream) |
| `OntologyBuilder` | Text analysis → document RDF |
| `OntologyAlignment` | Intra-document synonym clustering |
| `OntologyDerivation` | Load references, score labels, write bridge triples |
| `DocumentOntologyBuilder` | Orchestrates build → align → derive → SHACL → JSON-LD |
| `ontology_upload` (ingest) | Client bytes → staged paths on the document |

See also [Conception § document ontology](../conception.md#39-document-ontology)
and [Ingest — external ontologies](../deployment/ingest.md).
