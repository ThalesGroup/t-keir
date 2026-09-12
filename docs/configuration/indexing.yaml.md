# Indexing YAML — field effects

These files run **after** NLP in the unified pipeline. They decide how a
document is sliced for Vespa, how RDF is built, and whether synthetic
questions are attached to chunks.

Selected by [`pipeline.yaml`](pipeline.yaml.md) keys `chunking`, `ontology`,
`chunk-questions`.

---

## `golden-chunking.yaml`

Path: `tkeir/configs/golden-chunking.yaml`  
Loaded by: `GoldenChunker` → `ChunkSettings`.  
Writes `golden_chunks[]` (token ranges + text). Vespa indexes those chunks
on the **global** / **user** schemas.

| Field | Default | Effect |
|-------|---------|--------|
| `golden-chunking.chunkers[].language` | `en` | Language row. |
| `target-min-tokens` | `300` | Soft lower bound. Smaller chunks → more hits, weaker context for RAG. |
| `target-max-tokens` | `500` | Soft upper bound for a normal chunk. Larger → fewer chunks, more diluted dense vectors. |
| `high-ner-density-max-tokens` | `250` | When a window has ≥ `ner-density-threshold` entities, cap length here so entity-dense SITREPs are not merged into one 500-token blob. |
| `ner-density-threshold` | `3` | Entity count that triggers the shorter cap. Lower → more “dense” splits; higher → keep long narrative chunks. |

Requires `content_morphosyntax`, `content_ner`, and `content_deps` on the
document. Changing these values **does not** rewrite already-indexed Vespa
documents — re-ingest / reindex.

See [Vespa RAG](../tools/vespa_rag.md).

---

## `document-ontology.yaml`

Path: `tkeir/configs/document-ontology.yaml`  
Loaded by: `DocumentOntologyBuilder`.  
Writes `document_ontology.json_ld` (and optional derivation reports) on the
parent document. Search fuse, SPARQL, compose, and the HMI graph all read this.

| Field | Default | Effect |
|-------|---------|--------|
| `document-ontology.builders[].language` | `en` | Language row. |
| `include-title-triples` | `true` | `false` omits SVO from the **title** in the RDF hypergraph. |
| `include-content-triples` | `true` | `false` omits body SVO — graph becomes keywords/NER only. |
| `min-keyword-length` | `3` | Keywords shorter than this never become RDF concepts. Keep aligned with `keywords.yaml`. |
| `max-repair-attempts` | `2` | SHACL self-heal loops. `0` leaves violating graphs as-is. |
| `max-violations-to-repair` | `48` | If more SHACL violations exist, healing stops early (partial graph). |
| `max-heal-triples` | `12000` | Cap on triples considered during heal. Huge docs truncate repair. |
| `max-heal-seconds` | `8` | Wall-clock cap for heal. Timeout → unrepaired violations remain. |
| `alignment.enabled` | `true` | Cluster near-duplicate concept labels inside **this** document (`similarity-threshold`, `min-cluster-size`). `false` keeps duplicate surface forms as separate nodes. |
| `alignment.similarity-threshold` | `0.85` | Lower → more aggressive merging (risk of collapsing distinct entities). |
| `alignment.min-cluster-size` | `2` | Clusters smaller than this are not merged. |
| `save-alignment` | `false` | `true` stores alignment diagnostics on the document (larger JSON). |
| `derive-from.enabled` | `false` | `true` links the document graph to **reference** ontologies in `derive-from.paths`. Prefer per-ingest `ontology_file` uploads; keep this `false` in the shipped file. |
| `derive-from.paths` | `[]` | Relative names resolve only under `tkeir/resources/ontologies/` (plus `TKEIR_ONTOLOGY_ROOT`). Absolute paths allowed. **Not** `datasets/osint/ontologies/` unless uploaded. |
| `derive-from.similarity-threshold` | `0.8` | Label match threshold vs reference classes/individuals. |
| `derive-from.match-classes` / `match-individuals` | `true` | Which reference nodes are alignment candidates. |
| `derive-from.add-subclass-links` / `add-type-links` / `add-same-as-links` | `true` | Which RDF edges to emit when a match fires. |
| `derive-from.include-matched-axioms` | `false` | `true` copies extra axioms from the reference graph (heavier JSON-LD). |
| `derive-from.save-report` | `false` | Persist match details when derivation ran. |
| `save-derivation` | `false` | Store `document_ontology.derivation` even when the nested `save-report` is off. |

Narrative and hypergraph shape: [Document ontology](../tools/document_ontology.md).

---

## `chunk-questions.yaml`

Path: `tkeir/configs/chunk-questions.yaml`  
Loaded by: `ChunkQuestionGenerator`.  
Attaches synthetic questions to `golden_chunks` **in the pipeline JSON**.
They are **NLP artefacts for eval / tooling**; they are **not** Vespa-indexed
fields used by `/search`.

| Field | Default | Effect |
|-------|---------|--------|
| `chunk-questions.generators[].language` | `en` | Language row. |
| `min-questions` | `3` | Lower bound of generated questions per chunk. |
| `max-questions` | `5` | Upper bound. Higher → more synthetic queries, slower pipeline. |
| `enable-multilingual` | `true` | When true, generation may emit non-English questions for non-English chunks. `false` stays on the document language / English templates. |

Requires `golden_chunks` from the chunking step.

---

## Related

- NLP fields: [NLP pipeline YAML](nlp.yaml.md)  
- Retrieval after index: [rag.yaml](rag.yaml.md)
