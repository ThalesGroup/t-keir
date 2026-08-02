# Tokenizer

The tokenizer segments **title** and **content** fields of a T-KEIR document.
Tokenizer resources are compiled with `tkeir-create-annotation-resource`
(`thot/tools/annotation/create_annotation_resource.py`).

## Tokenizer configuration

Example of Configuration:

```yaml title="tokenizer.yaml"
--8<-- "./configs/tokenizer.yaml"
```

Tokenizer configuration contains a top-level `logger` section and tokenizer-specific `segmenters` settings.
The segmenter configuration is a table containing path to Multiple Word Expression entries (MWE):

- **language** :the language of tokenizer
- **resources-base-path**: path to resources (see `tkeir-create-annotation-resource`)
- **use-mwe** (optional): set to `true` to enable MWE compound-word detection and concept pre-tagging (slower; disabled by default)
- **mwe** : the file containing MWE entries (required when `use-mwe` is `true`)
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
