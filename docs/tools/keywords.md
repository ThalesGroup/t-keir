# Keywords extractor

The keywords extractor runs RAKE over morphosyntax fields and is invoked by the unified
pipeline (`tkeir-pipeline`).

## Keywords extractor configuration

Example of Configuration:


```yaml title="keywords.yaml"
--8<-- "./configs/keywords.yaml"
```

Keywords extractor configuration contains a top-level `logger` section and keywords-specific `extractors` settings.
The extractor allows to define validation rules for keywords:

- **language** :the language of tokenizer
- **resources-base-path**: path to resources (see `tkeir-create-annotation-resource`)
- **keywords-rules** : validation rules
- **prunning** : max number of words in keyword sequence
- **min-keyword-length** : minimum number of characters for an extracted keyword label (default: 3)

Keywords rules allows to filter and validate rules according to their POS Tags.

Example of Configuration:

```json title="keywords-rules.json"
--8<-- "./resources/modeling/tokenizer/en/keywords-rules.json"
```


The validation rule:

- **possible-pos-in-syntagm**: the list of the accepted POS tags in the syntagm associated to Named entity
- **at-least**: the minimal POS Tag

### Configure Keywords extractor logger

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

## Keywords extractor usage

```shell
tkeir-pipeline -c tkeir/configs/pipeline.yaml -i <INPUT FILE OR DIR> -o <OUTPUT DIR> -t raw --tasks keywords
```

## Keywords extractor Tests

The keywords extractor comes with unit and functional testing.

### Keywords Unit tests

```shell
python3 -m pytest tests/unittests/TestKeywordsConfiguration.py
python3 -m pytest tests/unittests/TestKeywordsExtractor.py
```

### Keywords extractor Functional tests

```shell
python3 -m pytest tests/functional_tests/TestPipeline.py
```
