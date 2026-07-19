# Named entity tagger

The named-entity tagger extracts entities from `title_tokens` and `content_tokens`.
It runs inside the unified pipeline (`tkeir-pipeline`).

## NER tagger configuration

Example of Configuration:

```json title="ner.json"
--8<-- "./configs/nertagger.yaml"
```

NER tagger configuration contains a top-level `logger` section and named-entity-specific `label` settings.
The label configuration allows to define validation rules file:

- **language** :the language of tokenizer
- **resources-base-path**: path to resources (see `tkeir-create-annotation-resource`)
- **ner-rules** : rules to filter labels

NER Rules allows to filter and validate rules according to their POS Tags.

Example of Configuration:


```json title="ner-rules.json"
--8<-- "./resources/modeling/tokenizer/en/ner-rules.json"
```

The validation rule is a set of triple:

- **label**: label of named entity to validat
- **possible-pos-in-syntagm**: the list of the accepted POS tags in the syntagm associated to Named entity
- **at-least**: the minimal POS Tag

### Configure NER tagger logger

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

## NER tagger usage

```shell
tkeir-pipeline -c tkeir/configs/pipeline.yaml -i <INPUT FILE OR DIR> -o <OUTPUT DIR> -t raw --tasks ner
```

## NER Tagger Tests

The NER tagger comes with unit and functional testing.

### NERTagger Unit tests

```shell
python3 -m pytest tkeir/tests/unittests/TestNERTaggerConfiguration.py
```
### NER Tagger Functional tests

```shell
python3 -m pytest tkeir/tests/functional_tests/TestPipeline.py
```
