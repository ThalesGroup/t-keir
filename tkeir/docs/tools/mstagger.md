# Morphosyntactic tagger

The morphosyntactic tagger annotates `title_tokens` and `content_tokens` in a T-KEIR
document. It is invoked by the unified pipeline (`tkeir-pipeline`), not as a standalone
REST service. Tagging uses spaCy models configured per language.

## Morphosyntactic tagger configuration

Example of Configuration:

```json title="mstagger.json"
--8<-- "./configs/mstagger.json"
```

Morphosyntactic tagger configuration contains a top-level `logger` section and morphosyntax-specific `taggers` settings.
The segmenter configuration is a table containing path to Multiple Word Expression entries (MWE):

- **language** :the language of tokenizer
- **resources-base-path**: path to resources (see `tkeir-create-annotation-resource`)
- **mwe** : the file containing MWE entries

### Configure Morphosyntactic tagger logger

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

## Morphosyntactic tagger usage

```shell
tkeir-pipeline -c tkeir/configs/pipeline.json -i <INPUT FILE OR DIR> -o <OUTPUT DIR> -t raw --tasks morphosyntax
```

## Morphosyntactic Tagger Tests

The Morphosyntactic tagger comes with unit and functional testing.

### Morphosyntactic Tagger Unit tests

```shell
python3 -m pytest tkeir/tests/unittests/TestMorphoSyntacticTaggerConfiguration.py
python3 -m pytest tkeir/tests/unittests/TestMorphoSyntacticTagger.py
```

### Morphosyntactic Tagger Functional tests

```shell
python3 -m pytest tkeir/tests/functional_tests/TestPipeline.py
```
