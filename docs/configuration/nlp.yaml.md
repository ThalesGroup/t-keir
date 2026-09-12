# NLP pipeline YAML — field effects

Paths under `tkeir/configs/`. Selected by [`pipeline.yaml`](pipeline.yaml.md).
CLI: `tkeir-pipeline -c tkeir/configs/pipeline.yaml …`.

Every file below has a top-level **`logger.logging-level`**: `debug` | `info` |
`warning` | `error` | `critical`. It only changes process log verbosity for
that task. It does not change tagging quality.

Language lists are **per-task tables**. The pipeline still runs language
detection first; the row whose `language` matches the document is used. The
shipped files only list `en`. Other detected languages reuse English **rules /
MWE pickles** while spaCy still tags with the language-specific model (see
[Tokenizer](../tools/tokenizer.md)).

---

## `converter.yaml`

Path: `tkeir/configs/converter.yaml`  
Loaded by: `thot.tasks.converters.ConverterConfiguration`  
Effect: first pipeline step — raw bytes → T-KEIR JSON (`title`, `content[]`).

```yaml
logger:
  logging-level: info
converter:
  settings:
    output:
      zip: true
    ocr:
      enabled: true
      mode: tesseract
      languages: eng+fra+deu+spa+ita+nld+por+pol+ara
      min-image-pixels: 65536
      min-page-text-chars: 40
      render-dpi: 200
      analyze-images: true
      captions: true
      max-embedded-images: 256
      max-pdf-images-per-page: 32
```

| Field | Default (parser) | Effect if you change it |
|-------|------------------|-------------------------|
| `settings.output.zip` | `false` | **Parsed and stored.** Not used by the current converter write path (reserved). Leave as shipped. |
| `ocr.enabled` | `true` | `false` skips Tesseract/LLM OCR. Scanned PDFs and images lose text; only the PDF text layer (if any) remains. |
| `ocr.mode` | `tesseract` | `tesseract` needs the Tesseract binary + tessdata (`make install-tesseract` / `make install-converter-models`). `llm` uses a vision LLM (`ocr.llm-*` or `OPENAI_API_KEY`) instead. |
| `ocr.languages` | `eng+fra+…+ara` | Tesseract `-l` pack list. Missing packs → empty OCR for that script. Must match files under `tkeir/resources/modeling/tesseract/`. |
| `ocr.min-image-pixels` | `65536` (256×256) | Embedded PDF images smaller than this (width×height) are skipped. Lower → more tiny icons/OCR noise; higher → miss small diagrams. |
| `ocr.min-page-text-chars` | `40` | If a PDF page already has this many text-layer characters, the page is **not** rasterized for OCR. Lower → OCR on text PDFs (slow, duplicates). Higher → miss sparse scanned pages. |
| `ocr.render-dpi` | `200` | Rasterization DPI for OCR. Higher → better small type, more RAM/time. |
| `ocr.analyze-images` | `true` | `true` writes Markdown image-analysis blocks (scene, EXIF/GPS, OCR). `false` keeps file metadata only — no per-image sections in `content`. |
| `ocr.captions` | follows `enabled` | `true` runs local BLIP (`resources/modeling/net/blip-image-captioning-base/`) when the model is present. Alias: `blip`. `false` skips captions even if OCR is on. |
| `ocr.max-embedded-images` | `256` | Cap on images extracted from Office/HTML. Extra images are dropped. |
| `ocr.max-pdf-images-per-page` | `32` | Cap on images OCR’d per PDF page. |
| `ocr.llm-model` / `llm-base-url` / `llm-api-key` / `llm-prompt` | unset | Only when `mode: llm`. Override model, endpoint, key, and vision prompt. |

Host setup: [Converter](../tools/converter.md).

---

## `tokenizer.yaml` / `tokenizer-mwe.yaml`

Path: `tkeir/configs/tokenizer.yaml`  
Loaded by: tokenizer task via `pipeline.configs.tokenizer`.

`tokenizer-mwe.yaml` is the **same schema** with `logging-level: error`. The
unified pipeline **does not** reference it (`pipeline.yaml` points at
`tokenizer.yaml`). Keep it only if you run the tokenizer CLI with `-c`
explicitly.

| Field | Default | Effect |
|-------|---------|--------|
| `tokenizers.segmenters[].language` | `en` | Which detected language this row applies to. |
| `resources-base-path` | `resources/modeling/tokenizer/en` | Directory for rules JSON and (language-specific) MWE extras. Gazetteers also load from `tokenizer/any/`. Relative to the T-KEIR resources root. |
| `use-mwe` | `true` | `true` loads the MWE trie (`tkeir_mwe.pkl`) so multi-word names (cities, orgs, …) stay one token and can pre-tag concepts. `false` splits compounds; NER/syntax see weaker MWEs. Rebuild pickles with `make init-models`. |
| `mwe` | `tkeir_mwe.pkl` | Filename of the pickle (required when `use-mwe` is true). Resolved under `any/` then the language directory. |
| `normalization-rules` | `tokenizer-rules.json` | Typos / word-mapping JSON in `resources-base-path`. `parsers` in that JSON is **not implemented**. Wrong mappings silently rewrite tokens before all later tasks. |
| `annotation-resources-reference` | `annotation-resources.json` | Manifest used when compiling tries (`tkeir-create-annotation-resource`). Changing it without rebuilding pickles has **no runtime effect**. |

---

## `mstagger.yaml` (morphosyntax)

Path: `tkeir/configs/mstagger.yaml`  
Loaded by: `MorphoSyntacticTagger`. Writes `title_morphosyntax` /
`content_morphosyntax` (POS, lemma).

| Field | Default | Effect |
|-------|---------|--------|
| `morphosyntax.taggers[].language` | `en` | Runtime currently accepts **`en` or `fr` only** (`ValueError` otherwise). Other pipeline languages still need an `en`/`fr` row or they fail this step. |
| `resources-base-path` / `use-mwe` / `mwe` | see tokenizer | SpaCy tokenizer is replaced by `ThotTokenizerToSpacy` so POS runs on T-KEIR tokens. `use-mwe: false` here desynchronizes morphosyntax from the tokenizer. |
| `pre-sentencizer` | `true` | **Present in YAML; not read** by `MorphoSyntacticTagger` today. Reserved. |
| `pre-tagging-with-concept` | `false` | `true` attaches MWE concept labels onto tokens during POS. Slightly richer KG later; more concept noise. |
| `add-concept-in-knowledge-graph` | `false` | `true` emits `rel:has-concept` triples from those labels into the document KG before NER/syntax. |

English/French load spaCy **`md`** models (`en_core_web_md` / `fr_core_news_md`).

---

## `nertagger.yaml`

Path: `tkeir/configs/nertagger.yaml`  
Loaded by: `NERTagger`. Writes `title_ner` / `content_ner`.

| Field | Default | Effect |
|-------|---------|--------|
| `named-entities.label[].language` | `en` | Language row (same matching as tokenizer). |
| `resources-base-path` / `use-mwe` / `mwe` | see tokenizer | MWE gazetteers become extra NER spans (`SpacyNERFromMWE`) merged with statistical NER. `use-mwe: false` → gazetteer entities disappear. |
| `ner-rules` | `ner-rules.json` | POS filters: keep a span only if its syntagm POS tags match `possible-pos-in-syntagm` / `at-least`. Stricter rules drop valid names; looser rules keep junk. |
| `use-pre-label` | `true` | **Present in YAML; not read** by `NERTagger` today. Reserved. |

---

## `syntactic-tagger.yaml`

Path: `tkeir/configs/syntactic-tagger.yaml`  
Loaded by: syntactic tagger. Writes `title_deps` / `content_deps` and SVO
triples used by ontology, RAG `svo_ontology` prompts, and agents.

| Field | Default | Effect |
|-------|---------|--------|
| `syntax.taggers[].language` | `en` | Language row. |
| `resources-base-path` / `use-mwe` / `mwe` | see tokenizer | Same token identity as tokenizer/NER. |
| `syntactic-rules` | `syntactic-rules.json` | SpaCy matcher rules for subject / predicate / object. Editing a rule changes which SVO triples exist — retrieval and compose KG change even if NER did not. |

---

## `keywords.yaml`

Path: `tkeir/configs/keywords.yaml`  
Loaded by: `KeywordsExtractor` (RAKE). Writes keyword lists used by document
ontology and HMI export (`rag.yaml` → `ontology.min_keyword_length` should stay
aligned with `min-keyword-length`).

| Field | Default | Effect |
|-------|---------|--------|
| `keywords.extractors[].language` | `en` | Language row. |
| `prunning` | `5` (code) / `10` (shipped YAML) | Max **tokens** in a keyword phrase. Higher → longer keyphrases; noisier ontology keywords. |
| `min-keyword-length` | `3` | Drop labels shorter than this many **characters**. |
| `generate-title-when-missing` | `true` | **Present in YAML; not read** by `KeywordsExtractor` today. Reserved. |
| `title-max-length` | `120` | **Not read** today. Reserved. |
| `resources-base-path` | tokenizer en dir | Location of `keywords-rules.json`. |
| `keywords-rules` | `keywords-rules.json` | POS allow-list for RAKE candidates (`possible-pos-in-syntagm`, `at-least`). |

---

## Related

- Orchestrator: [pipeline.yaml](pipeline.yaml.md)  
- After NLP: [Indexing YAML](indexing.yaml.md) (chunks, document RDF, questions)  
- Query-time: [rag.yaml](rag.yaml.md)
