# NLP

Short **P0 pipeline** demo (tokenizer → tagging → keywords → ontology) after
[Installation](installation.md) (`make setup` from the repository root). Part of
**[Zero to Hero](zero_to_hero.md)** (P0 → P4); this page is the NLP-only path
without Vespa indexing.

## Demo on fixtures

```bash
make quickstart
```

This runs `tkeir-pipeline` only (no Vespa indexing) on
`tests/fixtures/test-raw`:

- `raw/` — plain text
- `mail/` — email
- `raw-target/` — plain text

Output: `output/quickstart/`.

## Analyse your documents

Set a model cache if you use Hugging Face / transformer-backed steps
(not required for BGE-M3 — that lives under
`tkeir/resources/modeling/net/bge-m3` after `make setup`):

```bash
export TRANSFORMERS_CACHE=$PWD/.cache/models
```
Use **`-t auto`** for mixed or binary inputs (PDF, Office). Use **`-t raw`** for plain
text only.

Via Make:

```bash
make pipeline \
  PIPELINE_INPUT=/path/to/docs \
  PIPELINE_OUTPUT=$PWD/workspace/tmp/my-run \
  PIPELINE_TYPE=auto
```

Or directly (from `tkeir/` with the project venv):

```bash
cd tkeir
uv run --python 3.11 tkeir-pipeline \
  -c configs/pipeline.yaml \
  -i /path/to/docs \
  -o /path/to/out \
  -t auto
```

Pipeline stages: converter → language detection → resource selection → tokenizer →
morphosyntax → NER → syntax → keywords. Each stage adds fields to the output JSON.

JSON inputs that already contain `content` or `content_tokens` skip conversion and
start at language detection.

## Next

- [Zero to Hero §4](zero_to_hero.md#4-p0--vespa-rag--hmi) — bootstrap Vespa
  (`dev@tkeir`), RAG, HMI
- [Vespa RAG](tools/vespa_rag.md) — streaming mode and user space
- [HMI](hmi.md) — web UI on port 3000
- `make help` — all Makefile targets
