# Corpus tools (source tree / markdown → ingest JSON)

Build a record-oriented corpus JSON from a directory of markdown files, or
from a **heterogeneous source tree** (PDF, Office, HTML, images, ZIP, JSON,
CSV, …). Mixed-format directories are converted with
[UniversalConverter](converter.md) into a **parallel markdown-only tree**
that mirrors the original layout; that tree is then compiled to the shape
consumed by `POST /ingest/json-records`:

`{"dataset": {…}, "records": [{…}, …]}`.

Each record **must** have `doc_id`, `title`, and `text`. Extra fields
(classification, location, `source_format`, `file_type`, …) are optional and
become ontology concepts at ingest.

This is the **generation** path for demo and custom corpora (OSINT sitreps,
enterprise notes, geomaps dumps, your own file tree).

Package: `tkeir/thot/tools/corpus/` (`tkeir-corpus` CLI).

Related: [Ingestion](../deployment/ingest.md), [Converter](converter.md)
(markdown vs raw `content` split), [Datasets](datasets.md).

## Quick start

```bash
# 1. A folder of .md files
mkdir -p /tmp/notes
cat > /tmp/notes/suez.md <<'EOF'
# OSINT Report - Suez Gulf Approach

Cautious calm around Suez Gulf Approach.
EOF

# 2. Compile to ingest JSON
make corpus \
  CORPUS_INPUT=/tmp/notes \
  CORPUS_OUTPUT=./datasets/notes.json \
  CORPUS_NAME=notes

# same:
tkeir-corpus -i /tmp/notes -o ./datasets/notes.json --name notes
# or:
uv run --project tkeir --python 3.11 python -m thot.tools.corpus \
  -i /tmp/notes -o ./datasets/notes.json --name notes
```

Expected log line: `Wrote 1 records → …/datasets/notes.json`.

**Heterogeneous files** (PDF, Office, HTML, images, ZIP, JSON, CSV, mixed with markdown) — same CLI; conversion is automatic:

```bash
tkeir-corpus \
  -i /path/to/mixed-files \
  -m /path/to/mixed-files-markdown \
  -o ./datasets/mixed.json \
  --name mixed
```

```bash
make corpus \
  CORPUS_INPUT=/path/to/mixed-files \
  CORPUS_MARKDOWN_DIR=/path/to/mixed-files-markdown \
  CORPUS_OUTPUT=./datasets/mixed.json \
  CORPUS_NAME=mixed
```

Blank-text records are skipped by default (`--keep-empty` to fail instead). Add `--no-ocr` to skip Tesseract/BLIP, `--skip-unknown` to ignore unrecognized binaries. Re-runs skip sources whose markdown sidecar already exists unless you pass `--force`. Conversion is **multi-threaded** (`--workers 0`, default): the pool starts from CPU count and the mix of heavy files (PDF/Office/images) and grows while jobs keep finishing. Logs show **elapsed** time and an **ETA**, then a **summary** (counts by type, peak workers, throughput). `--workers 1` is sequential; `--workers N` pins a fixed pool. If `-m` is omitted, markdown is written next to the source as `<dirname>-markdown`. Details: [Mixed-format source tree](#mixed-format-source-tree).

## Mixed-format source tree

Point `-i` at any directory UniversalConverter can read. The tool:

1. Walks the tree (same hidden-dir skip as markdown mode)
2. Converts each file with `UniversalConverter.convert(..., "auto")`
3. Writes a **markdown-only replica** of the layout (`--markdown-dir`). Sources that already have a non-empty sidecar are **skipped** (re-run is cheap). Pass `--force` / `CORPUS_FORCE=1` to re-analyse.
4. Compiles that replica to `{dataset, records}` JSON as usual. Records with blank `text` are skipped by default (`--keep-empty` to fail instead).

Progress lines look like:

```text
[convert 12/80 | 15%] elapsed 1m 12s remaining ~6m 24s workers 6 | converted reports/a.pdf pdf (1.21s)
```

At the end of conversion (and again after markdown compile) a summary lists scanned / converted / skipped / errors, per-type counts, peak workers, elapsed time, and throughput.

Non-markdown files keep their original name and gain a `.md` suffix
(`reports/a.pdf` → `reports/a.pdf.md`) so stems cannot collide. Already-markdown
files keep their relative path. Archives stay **one file** (the ZIP is one
markdown document; members are not exploded into the output tree).

Each converted markdown file gets a `## Information` block:

| Extra | Meaning |
|---|---|
| `source_path` | Relative path of the **original** file |
| `source_format` | Original extension (`pdf`, `zip`, `txt`, …) — never the sidecar `.md` |
| `file_type` | UniversalConverter datatype (`pdf`, `raw`, `image`, `zip`, …) |

Those extras land on the JSON record. `doc_id` is the markdown relative stem
(`reports/a.pdf.md` → `reports/a.pdf`).

```bash
tkeir-corpus \
  -i /path/to/mixed-files \
  -m /path/to/mixed-files-markdown \
  -o ./datasets/mixed.json \
  --name mixed

make corpus \
  CORPUS_INPUT=/path/to/mixed-files \
  CORPUS_MARKDOWN_DIR=/path/to/mixed-files-markdown \
  CORPUS_OUTPUT=./datasets/mixed.json \
  CORPUS_NAME=mixed
```

Example with a named pack (OCR off for a fast dry run):

```bash
tkeir-corpus -i ./geomaps/data \
  -m ./datasets/geomaps/markdown \
  -o ./datasets/geomaps/geomaps.json \
  --name geomaps --skip-empty --no-ocr
```

If `--markdown-dir` is omitted and the input is not markdown-only, the markdown
tree is written next to the source as `<input>-markdown`. Markdown-only inputs
still compile in place (no extra tree) unless you pass `--convert`.

Use `--no-ocr` in tests or when tessdata/BLIP should not run. Default OCR
settings come from `tkeir/configs/converter.yaml`.

## Prerequisites

```bash
make install    # uv env in tkeir/ (registers tkeir-corpus)
```

No Vespa or ingest API is required to **build** the JSON. Those are only
needed to **index** it (see [Ingest the JSON](#ingest-the-json)).

## Markdown → record mapping

Each `.md` / `.markdown` file becomes one record. Hidden directories
(any path segment starting with `.`) are skipped. Recursion is on by default.

| Record field | Source |
|---|---|
| `doc_id` | YAML frontmatter `doc_id`, else relative path stem (`reports/a.md` → `reports/a`) |
| `title` | Frontmatter `title`, else first `#` heading, else the stem |
| `text` | Body after the H1 (`## Information` stripped out of the narrative) |
| extras | YAML frontmatter keys + `## Information` bullets |

`source`, `title`, and `text` inside `## Information` are ignored (they are
not copied as extras).

### Example 1 — heading + body (minimum)

`notes/suez.md`:

```markdown
# OSINT Report - Suez Gulf Approach

Cautious calm around Suez Gulf Approach.
```

Record:

```json
{
  "doc_id": "suez",
  "title": "OSINT Report - Suez Gulf Approach",
  "text": "Cautious calm around Suez Gulf Approach."
}
```

### Example 2 — YAML frontmatter (stable ids + C2 fields)

`notes/C2-0001.md`:

```markdown
---
doc_id: C2-202606-0001
classification: UNCLASSIFIED
domain: OSINT_SOCMINT
pir_ref: PIR-06
location:
  country: Egypt
  name: Suez Gulf Approach
tags:
  - maritime
  - suez
---
# OSINT Report - Suez Gulf Approach

Cautious calm around Suez Gulf Approach.
```

Record keeps `doc_id: C2-202606-0001` (not the filename), plus
`classification`, `domain`, `pir_ref`, `location`, `tags`.

### Example 3 — `## Information` bullets (ingest markdown round-trip)

This is the layout `record_to_markdown` writes when a JSON corpus is split
for ingest. `tkeir-corpus` can read it back.

```markdown
# OSINT Report - Suez

Cautious calm around Suez.

## Information

- **source:** `demo/C2-1`
- **doc_id:** C2-1
- **domain:** OSINT_SOCMINT
- **classification:** UNCLASSIFIED
- **location:**
  - **country:** Egypt
  - **mgrs:** 36RVT70864126
```

- `source` is dropped
- nested bullets become nested objects (`location.country`)
- scalars `true` / `false` / integers / floats are coerced

### Example 4 — markdown sections in `text`

If the body itself has headings, leave them in `text`. At ingest the converter
detects markdown and splits T-KEIR `content` per section (`Parent / Child` for
subsections). See [Converter](converter.md).

```markdown
# Sitrep

Intro paragraph.

## Ports

Suez Gulf Approach is watched.

### Traffic

AIS density remains low.
```

## CLI reference

| Flag | Default | Meaning |
|------|---------|---------|
| `-i` / `--input-dir` | required | Source directory (markdown and/or UniversalConverter formats) |
| `-o` / `--output` | required | Output JSON path |
| `-m` / `--markdown-dir` | `<input>-markdown` when converting | Write the converted markdown tree here |
| `--convert` | off | Force UniversalConverter even on markdown-only trees |
| `--skip-unknown` | off | Skip files classified as `unknown` |
| `--no-ocr` | off | Disable OCR / image analysis during conversion |
| `--workers` | `0` (adaptive) | Thread pool size. `0` sizes from CPU + heavy-file mix and grows with throughput; `1` sequential; `N` fixed |
| `--name` | directory name | `dataset.name` |
| `--version` | `1.0.0` | `dataset.version` |
| `--note` | unset | `dataset.note` |
| `--language` | `en` | `dataset.languages` (single primary entry) |
| `--dataset-json` | unset | JSON object merged into `dataset` (`name` / `record_count` still overwritten) |
| `--no-recursive` | off | Only the top of `--input-dir` |
| `--skip-empty` | on | Skip files whose narrative `text` is blank (default) |
| `--keep-empty` | off | Fail when a record has blank text instead of skipping it |
| `--force` | off | Re-convert even when the markdown sidecar already exists |

### Make wrapper

```bash
make corpus CORPUS_INPUT=./notes CORPUS_OUTPUT=./datasets/notes.json
make corpus CORPUS_INPUT=./notes CORPUS_OUTPUT=./datasets/notes.json CORPUS_NAME=osint-notes
make corpus CORPUS_INPUT=./data CORPUS_MARKDOWN_DIR=./data-md \
  CORPUS_OUTPUT=./datasets/notes.json CORPUS_NAME=notes
```

`CORPUS_INPUT` and `CORPUS_OUTPUT` are required. `CORPUS_NAME` maps to `--name`.
`CORPUS_MARKDOWN_DIR` maps to `--markdown-dir`. `CORPUS_CONVERT=1` adds `--convert`.
`CORPUS_WORKERS` maps to `--workers` (omit for adaptive threading).
`CORPUS_FORCE=1` maps to `--force` (re-analyse sources that already have `.md`).

### Nested files

```text
notes/
  suez.md                 → doc_id "suez"
  nested/bravo.md         → doc_id "nested/bravo"
```

Override with frontmatter `doc_id` when you need C2-style identifiers.

```bash
tkeir-corpus -i ./notes -o ./datasets/notes.json --name notes --skip-empty
```

### Extra dataset metadata

`extra.json`:

```json
{
  "classification_of_compilation": "UNCLASSIFIED",
  "note": "Simulated sitreps for the ontology smoke."
}
```

```bash
tkeir-corpus -i ./notes -o ./datasets/notes.json \
  --name notes --version 1.0.0 \
  --dataset-json extra.json
```

`dataset.name`, `version`, `generated_utc`, `record_count`, and `languages`
are always set by the tool after the merge.

## Output shape

```json
{
  "dataset": {
    "name": "notes",
    "version": "1.0.0",
    "generated_utc": "2026-09-09T12:00:00Z",
    "record_count": 1,
    "languages": ["en"]
  },
  "records": [
    {
      "doc_id": "suez",
      "title": "OSINT Report - Suez Gulf Approach",
      "text": "Cautious calm around Suez Gulf Approach."
    }
  ]
}
```

Validation rejects:

- missing `dataset.name`
- missing `doc_id` / `title` / `text` on a record
- duplicate `doc_id`
- empty input directory (or all-empty when `--skip-empty` drops every file)

## Python API

```python
from pathlib import Path
from thot.tools.corpus import (
    corpus_from_markdown_dir,
    corpus_from_source_dir,
    parse_markdown_record,
    write_record_corpus,
)

payload = corpus_from_markdown_dir(
    Path("notes"),
    name="notes",
    version="1.0.0",
    skip_empty=True,
)
write_record_corpus(payload, "datasets/notes.json")

mixed = corpus_from_source_dir(
    Path("data"),
    Path("data-markdown"),
    name="notes",
    ocr_config={"enabled": False},
)

record = parse_markdown_record(
    "# Hello\n\nWorld.\n",
    default_id="n1",
)
assert record == {"doc_id": "n1", "title": "Hello", "text": "World."}
```

## Ingest the JSON

Services: `make bootstrap` (Vespa) then `make ingest` (`:8091`) and `make rag`
(`:8090`). Prefer a small `limit` first.

If the file lives under `datasets/`:

```bash
curl -sS -X POST http://localhost:8091/ingest/json-records \
  -H 'content-type: application/json' \
  -d '{
    "dataset_path": "notes.json",
    "index_target": "global",
    "limit": 20,
    "business_ontology_dataset": "osint"
  }'
```

`dataset_path` is relative to `datasets/`. Alternatively upload the JSON as
multipart on the same endpoint (HMI: **Admin → Global corpus ingest**).

After jobs finish:

```bash
curl -sS -X POST http://localhost:8090/search \
  -H 'content-type: application/json' \
  -d '{"query":"Suez Gulf Approach","hits":5}'
```

At ingest, each record is turned back into markdown (`# title` + body +
`## Information`). The converter then:

1. Detects markdown vs raw prose on the record body (`metadata.text_format`)
2. Puts `title` on the T-KEIR document
3. Splits `content` on paragraphs or headings (subsection breadcrumb
   `Parent / Child`)
4. Keeps structured fields as ontology concept IDs

## Library map

| Module | Role |
|--------|------|
| `thot.tools.corpus.cli` | `tkeir-corpus` / `python -m thot.tools.corpus` |
| `thot.tools.corpus.builder` | Walk markdown or convert a source tree, write JSON |
| `thot.tools.corpus.convert_tree` | UniversalConverter → parallel markdown-only tree |
| `thot.tools.corpus.adaptive` | CPU / file-mix thread plan and growing limiter |
| `thot.tools.corpus.progress` | Elapsed / ETA progress lines and run summaries |
| `thot.tools.corpus.markdown_records` | Parse one file (frontmatter + Information) |
| `thot.tools.corpus.schema` | Validate `{dataset, records}` |
| `thot.tools.ingest.json_records` | Split records for NLP ingest |
