# Security

T-KEIR runs as an in-process document analysis pipeline (`tkeir-pipeline`). Task configuration files no longer expose HTTP `network` or `runtime` sections.

## Input and output paths

- Restrict read access on input directories and write access on output directories to trusted users.
- Pipeline output JSON may contain extracted document text; treat output directories with the same confidentiality level as source documents.

## External services

Some optional features contact external systems when enabled in configuration:

- **PDF OCR (`llm` mode)** — sends rendered page images to an OpenAI-compatible API when `ocr.llm-api-key` or `OPENAI_API_KEY` is set.
- **Annotation resource downloads** — tokenizer resource preparation may fetch remote lists when `download.url` is present in annotation configuration.

Review those settings before running in production environments.

## API gateway

If you expose pipeline results or wrap T-KEIR behind HTTP, use your organization's API gateway for authentication, rate limiting, and TLS termination.
