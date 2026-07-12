# Converter

The converter turns raw text or office/PDF/HTML inputs into T-KEIR JSON documents.
It is the first step of the unified pipeline (`tkeir-pipeline`).

## Converter configuration

Example of Configuration:

```json title="converter.json"
--8<-- "./configs/converter.json"
```


Converter is a pipeline task that converts document formats into T-KEIR JSON. Configuration contains a top-level `logger` section and converter-specific `settings` (output and OCR options).

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

Documents are converted with [Microsoft MarkItDown](https://github.com/microsoft/markitdown). Supported types include `email`, `pdf`, `docx`, `html`, `pptx`, `xlsx`, `csv`, and other formats handled by MarkItDown. Plain text uses the dedicated `raw` datatype. Existing T-KEIR JSON documents can be passed through with the `tkeir` datatype.

### Input datatype (`-t` / `--type`)

| Value | When to use |
|---|---|
| `auto` | **Default.** Detect from file extension and magic bytes (PDF, Office, email, …). |
| `raw` | Plain UTF-8 text only (`.txt`, `.md`, …). Do **not** use for PDFs — binary bytes would be decoded as garbage text. |
| `pdf`, `docx`, … | Force a specific MarkItDown converter type. |

The pipeline CLI and `make pipeline` default to `PIPELINE_TYPE=auto`.

MarkItDown extracts only the PDF **text layer** by default. Text inside embedded images (diagrams, scans) is recovered when OCR is enabled in `converter.json`:

```json
"ocr": {
  "enabled": true,
  "mode": "tesseract",
  "min-image-pixels": 10000,
  "min-page-text-chars": 40,
  "render-dpi": 200
}
```

- **tesseract** mode (default): requires the [Tesseract](https://github.com/tesseract-ocr/tesseract) binary on `PATH`.
- **llm** mode: set `"mode": "llm"` and provide `OPENAI_API_KEY` (or `ocr.llm-api-key`) for vision-based extraction from images and scanned pages.

Run conversion through the unified pipeline:

```shell
tkeir-pipeline -c tkeir/configs/pipeline.json -i <INPUT FILE OR DIR> -o <OUTPUT DIR> -t raw --tasks converter
```

Or run the full pipeline (converter is the first step by default):

```shell
tkeir-pipeline -c tkeir/configs/pipeline.json -i <INPUT FILE OR DIR> -o <OUTPUT DIR> -t auto
```

## Converter Tests

The converter service come with unit and functional testing.

### Converter Unit tests

Unittest allows to test Converters classes only.

```shell
python3 -m pytest tkeir/tests/unittests/TestConverterConfiguration.py
python3 -m pytest tkeir/tests/unittests/TestConverter.py
python3 -m pytest tkeir/tests/unittests/TestMarkItDownConverter.py
python3 -m pytest tkeir/tests/unittests/TestRawConverter.py
```

### Converter Functional tests

```shell
python3 -m pytest tkeir/tests/functional_tests/TestPipeline.py
```
