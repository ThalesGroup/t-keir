# Tokenizer

The tokenizer segments **title** and **content** fields of a T-KEIR document.
Tokenizer resources are compiled with `tkeir-create-annotation-resource`
(`thot/tools/annotation/create_annotation_resource.py`).

## Languages

Language detection (`langdetect`) runs after conversion. Tagging uses spaCy
pipelines shipped under `tkeir/resources/modeling/spacy/` (`make
install-spacy-models` / `make setup`):

| Language | Model |
|----------|--------|
| English | `en_core_web_sm` / `en_core_web_md` |
| French | `fr_core_news_sm` / `fr_core_news_md` |
| German, Spanish, Italian, Portuguese, Dutch, Polish, Danish, Swedish | `*_core_news_sm` |
| Other / fallback NER | `xx_ent_wiki_sm` |
| Arabic | `spacy.blank("ar")` (no Explosion 3.6 trained pipeline). Surface forms are kept when lemmas are empty so hybrid indexing still matches Arabic text. |

Tokenizer lexical resources:

- `resources/modeling/tokenizer/any/` — language-agnostic gazetteers (GeoNames
  cities/countries, rivers, mountains, lakes, and regions) compiled into
  `tkeir_mwe.pkl` (`make init-models`). Hydro/relief/region lists are seeded
  with multilingual exonyms, then expanded from Natural Earth 10m and GeoNames
  admin-1 (`make geo-gazetteers` / `scripts/build_geo_gazetteers.py`).
- `resources/modeling/tokenizer/<lang>/` — language-specific rules and
  stopwords (`en` today; other languages fall back to `en` for rules while
  spaCy still tags in the detected language)

See [Converter](converter.md) for OCR languages (Tesseract `eng+…+ara`).

## Tokenizer configuration

Example of Configuration:

```yaml title="tokenizer.yaml"
--8<-- "./configs/tokenizer.yaml"
```

Tokenizer configuration contains a top-level `logger` section and tokenizer-specific `segmenters` settings.

**Every key and its effect:** [NLP pipeline YAML](../configuration/nlp.yaml.md#tokenizeryaml--tokenizer-mweyaml).

- **language** :the language of tokenizer
- **resources-base-path**: path to resources (see `tkeir-create-annotation-resource`)
- **use-mwe** (optional): set to `true` to enable MWE compound-word detection and concept pre-tagging (on by default; the pickle is loaded from `tokenizer/any/` then the language directory)
- **mwe** : the file containing MWE entries (required when `use-mwe` is `true`; default `tkeir_mwe.pkl`)
- **normalization-rules** : the file containing normalization rules
- **annotation-resources-reference** : reference to annotation file, needs on tokenizer init

Tokenizer accepts a rule file to select parser (not yet implemented), common typos fixing and word mapping (for example map english words to us words).
The normalization rule is a simple json file with the following fields:

- **parsers** (NOT YET IMPLEMENTED) : the available parser (for exemple pyvalem to parse chemestry formulas)
- **normalization/word-mapping**: mapping words
- **normalization/typos** : typos fixing

```json title="tokenizer-rules.json"
--8<-- "./resources/modeling/tokenizer/en/tokenizer-rules.json"
```

### Configure tokenizer logger

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

## Tokenizer usage

To create these resources simply run

```shell
tkeir-create-annotation-resource --entries-file=...
```

Run tokenization through the unified pipeline:

```shell
tkeir-pipeline -c tkeir/configs/pipeline.yaml -i <INPUT FILE OR DIR> -o <OUTPUT DIR> -t raw --tasks tokenizer
```


## Tokenizer Tests

The converter service come with unit and functional testing.

### Tokenizer Unit tests

Unittest allows to test Tokenizer classes only.

```shell
python3 -m pytest tests/unittests/TestTokenizerConfiguration.py
python3 -m pytest tests/unittests/TestTokenizerMultilingual.py
```

### Tokenizer Functional tests

```shell
python3 -m pytest tests/functional_tests/TestPipeline.py
```
