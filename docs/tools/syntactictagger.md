# Syntactic tagger

The syntactic tagger builds dependency parses and knowledge-graph triples from
`title_morphosyntax` and `content_morphosyntax`. It runs inside the unified pipeline
(`tkeir-pipeline`).

## Syntactic tagger configuration

Example of Configuration:


```yaml title="syntactic-tagger.yaml"
--8<-- "./configs/syntactic-tagger.yaml"
```

Syntactic tagger configuration contains a top-level `logger` section and syntax-specific `taggers` settings.

Syntactic Rules allows to define rule for triple Subject, Predicate, Object extraction

Example of Configuration:


```yaml title="syntactic-tagger.yaml"
--8<-- "./resources/modeling/tokenizer/en/syntactic-rules.json"
```

The rules allows to extract triple based on sequence matcher of spacy

The syntax of the field is:

- **\<name of rule>** :

  - **rule** : matcher rule or triple rule
  - **type** : subject, object, predicate of triple

### Configure Syntactic tagger logger

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

## Syntactic tagger usage

```shell
tkeir-pipeline -c tkeir/configs/pipeline.yaml -i <INPUT FILE OR DIR> -o <OUTPUT DIR> -t raw --tasks syntax
```

## Syntactic tagger Tests

The syntactic tagger comes with unit and functional testing.

### Syntactic Tagger Unit tests

```shell
python3 -m pytest tkeir/tests/unittests/TestSyntacticTaggerConfiguration.py
python3 -m pytest tkeir/tests/unittests/TestSyntacticTagger.py
```

### Syntactic tagger Functional tests

```shell
python3 -m pytest tkeir/tests/functional_tests/TestPipeline.py
```
