#!/usr/bin/env python3
"""Title: Generate configs

Generate functional test service configs without Jinja placeholders.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import os

import yaml

DIR = os.path.dirname(os.path.abspath(__file__))
RES = os.path.abspath(
    os.path.join(DIR, "../../../tkeir/resources/modeling/tokenizer/en")
)
LOGGER = {"logging-level": "error"}

CONFIGS = {
    "converter.yaml": {
        "logger": LOGGER,
        "converter": {
            "settings": {"output": {"zip": True}},
        },
    },
    "tokenizer.yaml": {
        "logger": LOGGER,
        "tokenizers": {
            "segmenters": [
                {
                    "language": "en",
                    "resources-base-path": RES,
                    "normalization-rules": "tokenizer-rules.json",
                    "annotation-resources-reference": (
                        "annotation-resources.json"
                    ),
                }
            ],
        },
    },
    "mstagger.yaml": {
        "logger": LOGGER,
        "morphosyntax": {
            "taggers": [
                {
                    "language": "en",
                    "resources-base-path": RES,
                    "pre-sentencizer": True,
                    "pre-tagging-with-concept": True,
                    "add-concept-in-knowledge-graph": True,
                }
            ],
        },
    },
    "nertagger.yaml": {
        "logger": LOGGER,
        "named-entities": {
            "label": [
                {
                    "language": "en",
                    "resources-base-path": RES,
                    "ner-rules": "ner-rules.json",
                    "use-pre-label": True,
                }
            ],
        },
    },
    "syntactic-tagger.yaml": {
        "logger": LOGGER,
        "syntax": {
            "taggers": [
                {
                    "language": "en",
                    "resources-base-path": RES,
                    "syntactic-rules": "syntactic-rules.json",
                }
            ],
        },
    },
    "keywords.yaml": {
        "logger": LOGGER,
        "keywords": {
            "extractors": [
                {
                    "language": "en",
                    "prunning": 10,
                    "resources-base-path": RES,
                    "keywords-rules": "tokenizer-rules.json",
                }
            ],
        },
    },
    "golden-chunking.yaml": {
        "logger": LOGGER,
        "golden-chunking": {
            "chunkers": [
                {
                    "language": "en",
                    "target-min-tokens": 300,
                    "target-max-tokens": 500,
                    "high-ner-density-max-tokens": 250,
                    "ner-density-threshold": 3,
                }
            ],
        },
    },
    "document-ontology.yaml": {
        "logger": LOGGER,
        "document-ontology": {
            "builders": [
                {
                    "language": "en",
                    "include-title-triples": True,
                    "include-content-triples": True,
                    "max-repair-attempts": 2,
                }
            ],
        },
    },
    "chunk-questions.yaml": {
        "logger": LOGGER,
        "chunk-questions": {
            "generators": [
                {
                    "language": "en",
                    "min-questions": 3,
                    "max-questions": 5,
                    "enable-multilingual": True,
                }
            ],
        },
    },
}

if __name__ == "__main__":
    for name, data in CONFIGS.items():
        with open(os.path.join(DIR, name), "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, default_flow_style=False, sort_keys=False)
