# Converter

The converter turns raw text, markdown, office/PDF/HTML, images, archives, and
JSON into T-KEIR JSON documents. It is the first step of the unified pipeline
(`tkeir-pipeline`).

A **universal converter** classifies the file (extension + magic bytes) and
extracts Markdown for types MarkItDown does not cover well (images, ZIP,
legacy `.doc`, SVG, unknown binary). For known Office/PDF types, MarkItDown
runs first with the universal extractor as fallback.

`content` is a **list of text blocks**. Raw prose is split on blank-line
paragraphs. Markdown (detected from ATX headings, fenced code, or links) is
split on section / subsection headings; subsection blocks keep a
`Parent / Child` breadcrumb so tokenizer, NER, and golden-chunking follow the
outline instead of one undifferentiated blob. JSON-record ingest still
serializes each record to markdown (title + body + `## Information`); the
converter then applies the same split. Building that JSON from a markdown
directory or a mixed-format source tree: [Corpus tools](corpus.md).

Multilingual OCR uses Tesseract language packs under
`tkeir/resources/modeling/tesseract/` (`eng+fra+deu+spa+ita+nld+por+pol+ara`).
Optional image captions use BLIP from
`tkeir/resources/modeling/net/blip-image-captioning-base/`. Both are
downloaded by `make install-converter-models` / `make setup`.

## Converter configuration

Example of Configuration:

```yaml title="converter.yaml"
--8<-- "./configs/converter.yaml"
```


Converter is a pipeline task that converts document formats into T-KEIR JSON. Configuration contains a top-level `logger` section and converter-specific `settings` (output and OCR options).

**Every key and its effect:** [NLP pipeline YAML](../configuration/nlp.yaml.md#converteryaml).

### Configure converter logger

Logger is configuration at top level of json in *logger* field.

Example of Configuration:

```json title="logger configuration"
--8<-- "./docs/configuration/examples/loggerconfiguration.json"
```

The logger fields is:

- **logging-level**

  It can be set to the following values:

  - **debug** for the debug level and developper information
  - **info** for the level of information
  - **warning** to display only warning and errors
  - **error** to display only error
  - **critical** to display only error

## Converter usage

Documents are converted with a **universal converter** (office, PDF, HTML,
images, ZIP, JSON, markdown, SVG) and, for known MarkItDown types, Microsoft
[MarkItDown](https://github.com/microsoft/markitdown) first with a universal
fallback. Plain text uses the dedicated `raw` datatype. Existing T-KEIR JSON
documents can be passed through with the `tkeir` datatype.

### Input datatype (`-t` / `--type`)

| Value | When to use |
|---|---|
| `auto` | **Default.** Detect from file extension and magic bytes (PDF, Office, image, ZIP, email, …). Unrecognized binary is converted as `unknown` (preview stub) instead of failing ingest. |
| `raw` | Plain UTF-8 text only (`.txt`, …). Do **not** use for PDFs — binary bytes would be decoded as garbage text. |
| `pdf`, `docx`, … | Force a specific MarkItDown converter type. |
| `image`, `zip`, `json`, `md`, `doc`, `svg` | Universal extractor. Images (and pictures inside PDF/Office) become **Markdown**: scene class, visual stats, EXIF/GPS, Tesseract OCR, optional BLIP caption. |

The pipeline CLI and `make pipeline` default to `PIPELINE_TYPE=auto`.

MarkItDown extracts only the PDF **text layer** by default. Text inside embedded images (diagrams, scans) is recovered when OCR is enabled in `converter.yaml`:

```json
"ocr": {
  "enabled": true,
  "mode": "tesseract",
  "languages": "eng+fra+deu+spa+ita+nld+por+pol+ara",
  "min-image-pixels": 10000,
  "min-page-text-chars": 40,
  "render-dpi": 200,
  "analyze-images": true
}
```

- **tesseract** mode (default): requires the [Tesseract](https://github.com/tesseract-ocr/tesseract) binary on `PATH` (`make install-tesseract`) and language packs in `resources/modeling/tesseract/` (`make install-converter-models`).
- **llm** mode: set `"mode": "llm"` and provide `OPENAI_API_KEY` (or `ocr.llm-api-key`) for vision-based extraction from images and scanned pages.
- **analyze-images** (default true): the converter analyses rasters and writes Markdown (`## Image analysis` / `## Embedded image …` with scene, stats, EXIF, OCR text, BLIP caption when the local model is present). Standalone images, and pictures **in reading order** inside PDF/DOCX/PPTX/XLSX (next to the surrounding text, not dumped at the end of the file). Set `false` to keep only file metadata.

Host setup:

```bash
make install-tesseract
make install-converter-models   # tessdata + BLIP (skips files already present)
# FORCE_CONVERTER_MODELS=1 make install-converter-models
```

Run conversion through the unified pipeline:

```shell
tkeir-pipeline -c tkeir/configs/pipeline.yaml -i <INPUT FILE OR DIR> -o <OUTPUT DIR> -t raw --tasks converter
```

Or run the full pipeline (converter is the first step by default):

```shell
tkeir-pipeline -c tkeir/configs/pipeline.yaml -i <INPUT FILE OR DIR> -o <OUTPUT DIR> -t auto
```

## Converter Tests

The converter service come with unit and functional testing.

### Converter Unit tests

Unittest allows to test Converters classes only.

```shell
python3 -m pytest tests/unittests/TestConverterConfiguration.py
python3 -m pytest tests/unittests/TestConverter.py
python3 -m pytest tests/unittests/TestUniversalConverter.py
python3 -m pytest tests/unittests/TestMarkItDownConverter.py
python3 -m pytest tests/unittests/TestRawConverter.py
```

### Converter Functional tests

```shell
python3 -m pytest tests/functional_tests/TestPipeline.py
```
