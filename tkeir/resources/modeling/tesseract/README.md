# Local Tesseract traineddata

Language packs downloaded by `make install-converter-models` / `make setup`
live here (tessdata_fast). Runtime OCR (`PdfImageOcr`, universal converter)
passes `--tessdata-dir` to this folder.

| File | Language |
|------|----------|
| `eng.traineddata` | English |
| `fra.traineddata` | French |
| `deu.traineddata` | German |
| `spa.traineddata` | Spanish |
| `ita.traineddata` | Italian |
| `nld.traineddata` | Dutch |
| `por.traineddata` | Portuguese |
| `pol.traineddata` | Polish |
| `ara.traineddata` | Arabic |
| `osd.traineddata` | Orientation / script detection |

Override the directory with `TKEIR_TESSDATA_DIR`. Re-download with
`make install-converter-models FORCE_CONVERTER_MODELS=1`.
