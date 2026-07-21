# Ontology-driven templates (Phase C)

> Phase C — fill versioned templates from the fused per-`user_space` knowledge
> graph. Writer/reviewer agents ground freeform slots; unfillable slots are
> reported, never hallucinated.

## Quick start

```bash
make compose TEMPLATE=synthesis_note TOPIC=Acme
# → .tkeir-compose/synthesis_note.md
# → .tkeir-compose/synthesis_note.json
```

Offline demo Turtle is used by default (`COMPOSE_DEMO=1`). Point at parent
ontologies with `COMPOSE_TURTLE_DIR=/path/to/ttl`.

## Templates

| Name | Path |
|------|------|
| `synthesis_note` | `tkeir/configs/templates/synthesis_note.yaml` |
| `entity_profile` | `tkeir/configs/templates/entity_profile.yaml` |
| `nato_synthesis_note` | `tkeir/configs/templates/nato_synthesis_note.yaml` |

Slot types: `entity`, `svo_pattern`, `keyword`, `sparql`, `freeform_grounded`.

Seed the fused knowledge graph with the NATO C2SIM ontologies from Zero-to-Hero §3.4:

```bash
COMPOSE_TURTLE_DIR=workspace/corpus_nato/ontologies \
make compose TEMPLATE=nato_synthesis_note TOPIC="CWIX 2023"
```

**Checkpoint:** `.tkeir-compose/nato_synthesis_note.json` has non-empty
`citations_map`; ungrounded slots appear in `unfilled` (never hallucinated).

## Agents (YAML)

| Agent | Role in Phase C |
|-------|-----------------|
| `analyst` | KG-focused research (tools: search, ontology_query, document_get) |
| `writer` | Single-shot grounded prose for freeform slots |
| `reviewer` | Drops fills lacking chunk/document provenance |

Full multi-agent orchestration of these roles is **Phase D**.

## Layout

```text
tkeir/thot/compose/
  kg.py              # fused graph + SPARQL (rdflib; swappable backend)
  template_models.py
  registry.py
  composer.py
  writers.py
  exporters.py       # markdown (+ docx/pdf stubs)
  demo_data.py
```

## Checkpoint

Every **filled** slot in the JSON export lists `chunk_ids` under
`citations_map`. Slots that cannot be grounded appear in `unfilled`.

See also [Agents](agents.md) and [MCP server](mcp.md).
