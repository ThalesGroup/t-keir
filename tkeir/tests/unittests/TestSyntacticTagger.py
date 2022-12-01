# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

from thot.core.ThotLogger import ThotLogger, LogUserContext
from thot.tasks.syntax.SyntacticTaggerConfiguration import SyntacticTaggerConfiguration
from thot.tasks.syntax.SyntacticTagger import SyntacticTagger
import os
import json
import unittest

dir_path = os.path.dirname(os.path.realpath(__file__))
test_file_path = os.path.abspath(os.path.join(dir_path, "../data/test-outputs-ner"))


class TestSyntacticTagger(unittest.TestCase):

    tagger_config = {
        "logger": {"logging-level": "debug"},
        "syntax": {
            "taggers": [
                {
                    "language": "en",
                    "resources-base-path": "/home/tkeir_svc/tkeir/app/projects/default/configs",
                    "syntactic-rules": "syntactic-rules.json",
                }
            ],
            "network": {
                "host": "0.0.0.0",
                "port": 8080,
                "associate-environment": {"host": "HOST_ENVNAME", "port": "PORT_ENVNAME"},
            },
            "runtime": {
                "request-max-size": 100000000,
                "request-buffer-queue-size": 100,
                "keep-alive": True,
                "keep-alive-timeout": 5,
                "graceful-shutown-timeout": 15.0,
                "request-timeout": 60,
                "response-timeout": 60,
                "workers": 1,
            },
            "serialize": {
                "input": {"path": "/tmp", "keep-service-info": True},
                "output": {"path": "/tmp", "keep-service-info": True},
            },
        },
    }

    def test_tagger_mail(self):
        config = SyntacticTaggerConfiguration()
        res_path = os.path.abspath(os.path.join(dir_path, "../../app/projects/template/configs/"))
        TestSyntacticTagger.tagger_config["syntax"]["taggers"][0]["resources-base-path"] = res_path
        config.loads(TestSyntacticTagger.tagger_config)
        ThotLogger.loads(config.logger_config.configuration)

        with open(os.path.join(test_file_path, "mail3.txt.converted.tokenized.ms.ner.json")) as f:
            tkeir_doc = json.load(f)
            f.close()
            test = dict()
            test["title_deps"] = [
                    {
                    "text": "Lackawanna",
                    "lemma": "Lackawanna",
                    "pos": "PROPN",
                    "head": 1,
                    "dep": "compound",
                    "lefts": [],
                    "rights": []
                    },
                    {
                    "text": "Letter",
                    "lemma": "Letter",
                    "pos": "PROPN",
                    "head": 1,
                    "dep": "ROOT",
                    "lefts": [
                        0
                    ],
                    "rights": [
                        2
                    ]
                    },
                    {
                    "text": "of",
                    "lemma": "of",
                    "pos": "ADP",
                    "head": 1,
                    "dep": "prep",
                    "lefts": [],
                    "rights": [
                        3
                    ]
                    },
                    {
                    "text": "Credit",
                    "lemma": "Credit",
                    "pos": "PROPN",
                    "head": 2,
                    "dep": "pobj",
                    "lefts": [],
                    "rights": []
                    }
                    ]

            test["kg"] = [
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:instanceof",
                        "label_content": "",
                        "lemma_content": "rel:instanceof",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "john.enerson@enron.com",
                        "label_content": "",
                        "lemma_content": "john.enerson@enron.com",
                        "positions": [-1],
                    },
                    "value": {"content": "email", "label_content": "", "lemma_content": "email", "positions": [-1]},
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:instanceof",
                        "label_content": "",
                        "lemma_content": "rel:instanceof",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "John Enerso",
                        "label_content": "",
                        "lemma_content": "John Enerso",
                        "positions": [-1],
                    },
                    "value": {"content": "person", "label_content": "", "lemma_content": "person", "positions": [-1]},
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:mailto",
                        "label_content": "",
                        "lemma_content": "rel:mailto",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "john.enerson@enron.com",
                        "label_content": "",
                        "lemma_content": "john.enerson@enron.com",
                        "positions": [-1],
                    },
                    "value": {
                        "content": "richard.sanders@enron.com",
                        "label_content": "",
                        "lemma_content": "richard.sanders@enron.com",
                        "positions": [-1],
                    },
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:mailto",
                        "label_content": "",
                        "lemma_content": "rel:mailto",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "John Enerso",
                        "label_content": "",
                        "lemma_content": "John Enerso",
                        "positions": [-1],
                    },
                    "value": {
                        "content": "Richard B Sander",
                        "label_content": "",
                        "lemma_content": "Richard B Sander",
                        "positions": [-1],
                    },
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:instanceof",
                        "label_content": "",
                        "lemma_content": "rel:instanceof",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "Richard B Sander",
                        "label_content": "",
                        "lemma_content": "Richard B Sander",
                        "positions": [-1],
                    },
                    "value": {"content": "person", "label_content": "", "lemma_content": "person", "positions": [-1]},
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:mailcc",
                        "label_content": "",
                        "lemma_content": "rel:mailcc",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "john.enerson@enron.com",
                        "label_content": "",
                        "lemma_content": "john.enerson@enron.com",
                        "positions": [-1],
                    },
                    "value": {
                        "content": "richard.lydecker@enron.com",
                        "label_content": "",
                        "lemma_content": "richard.lydecker@enron.com",
                        "positions": [-1],
                    },
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:mailcc",
                        "label_content": "",
                        "lemma_content": "rel:mailcc",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "john.enerson@enron.com",
                        "label_content": "",
                        "lemma_content": "john.enerson@enron.com",
                        "positions": [-1],
                    },
                    "value": {
                        "content": "randy.petersen@enron.com",
                        "label_content": "",
                        "lemma_content": "randy.petersen@enron.com",
                        "positions": [-1],
                    },
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:mailcc",
                        "label_content": "",
                        "lemma_content": "rel:mailcc",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "john.enerson@enron.com",
                        "label_content": "",
                        "lemma_content": "john.enerson@enron.com",
                        "positions": [-1],
                    },
                    "value": {
                        "content": "dan.lyons@enron.com",
                        "label_content": "",
                        "lemma_content": "dan.lyons@enron.com",
                        "positions": [-1],
                    },
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:mailcc",
                        "label_content": "",
                        "lemma_content": "rel:mailcc",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "John Enerso",
                        "label_content": "",
                        "lemma_content": "John Enerso",
                        "positions": [-1],
                    },
                    "value": {
                        "content": "Richard Lydecker",
                        "label_content": "",
                        "lemma_content": "Richard Lydecker",
                        "positions": [-1],
                    },
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:mailcc",
                        "label_content": "",
                        "lemma_content": "rel:mailcc",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "John Enerso",
                        "label_content": "",
                        "lemma_content": "John Enerso",
                        "positions": [-1],
                    },
                    "value": {
                        "content": "Randy Petersen",
                        "label_content": "",
                        "lemma_content": "Randy Petersen",
                        "positions": [-1],
                    },
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:mailcc",
                        "label_content": "",
                        "lemma_content": "rel:mailcc",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "John Enerso",
                        "label_content": "",
                        "lemma_content": "John Enerso",
                        "positions": [-1],
                    },
                    "value": {"content": "Dan Lyon", "label_content": "", "lemma_content": "Dan Lyon", "positions": [-1]},
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:instanceof",
                        "label_content": "",
                        "lemma_content": "rel:instanceof",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "Richard Lydecker",
                        "label_content": "",
                        "lemma_content": "Richard Lydecker",
                        "positions": [-1],
                    },
                    "value": {"content": "person", "label_content": "", "lemma_content": "person", "positions": [-1]},
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:instanceof",
                        "label_content": "",
                        "lemma_content": "rel:instanceof",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "Randy Petersen",
                        "label_content": "",
                        "lemma_content": "Randy Petersen",
                        "positions": [-1],
                    },
                    "value": {"content": "person", "label_content": "", "lemma_content": "person", "positions": [-1]},
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:instanceof",
                        "label_content": "",
                        "lemma_content": "rel:instanceof",
                        "positions": [-1],
                    },
                    "subject": {"content": "Dan Lyon", "label_content": "", "lemma_content": "Dan Lyon", "positions": [-1]},
                    "value": {"content": "person", "label_content": "", "lemma_content": "person", "positions": [-1]},
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:mailbcc",
                        "label_content": "",
                        "lemma_content": "rel:mailbcc",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "john.enerson@enron.com",
                        "label_content": "",
                        "lemma_content": "john.enerson@enron.com",
                        "positions": [-1],
                    },
                    "value": {
                        "content": "richard.lydecker@enron.com",
                        "label_content": "",
                        "lemma_content": "richard.lydecker@enron.com",
                        "positions": [-1],
                    },
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:mailbcc",
                        "label_content": "",
                        "lemma_content": "rel:mailbcc",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "john.enerson@enron.com",
                        "label_content": "",
                        "lemma_content": "john.enerson@enron.com",
                        "positions": [-1],
                    },
                    "value": {
                        "content": "randy.petersen@enron.com",
                        "label_content": "",
                        "lemma_content": "randy.petersen@enron.com",
                        "positions": [-1],
                    },
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:mailbcc",
                        "label_content": "",
                        "lemma_content": "rel:mailbcc",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "john.enerson@enron.com",
                        "label_content": "",
                        "lemma_content": "john.enerson@enron.com",
                        "positions": [-1],
                    },
                    "value": {
                        "content": "dan.lyons@enron.com",
                        "label_content": "",
                        "lemma_content": "dan.lyons@enron.com",
                        "positions": [-1],
                    },
                    "weight": 0.0,
                },
                {
                    "automatically_fill": True,
                    "confidence": 1.0,
                    "field_type": "mail-header",
                    "property": {
                        "content": "rel:instanceof",
                        "label_content": "",
                        "lemma_content": "rel:instanceof",
                        "positions": [-1],
                    },
                    "subject": {
                        "content": "Tue, 30 Jan 2001 02:35:00 -0800",
                        "label_content": "",
                        "lemma_content": "Tue, 30 Jan 2001 02:35:00 -0800",
                        "positions": [-1],
                    },
                    "value": {"content": "date", "label_content": "", "lemma_content": "date", "positions": [-1]},
                    "weight": 0.0,
                },
                {
                    "subject": {
                        "content": ["amount"],
                        "lemma_content": ["amount"],
                        "pos": ["NOUN"],
                        "positions": [26],
                        "label": "pattern_syntagm_or_prep_group",
                    },
                    "property": {
                        "content": ["is", "increased"],
                        "lemma_content": ["be", "increase"],
                        "pos": ["VERB", "VERB"],
                        "positions": [27, 28],
                        "label": "pattern_verb_phrase",
                    },
                    "value": {
                        "content": ["4.5", "million"],
                        "lemma_content": ["4.5", "million"],
                        "pos": ["NUM", "NUM"],
                        "positions": [30, 31],
                        "label": "money",
                    },
                    "automatically_fill": True,
                    "confidence": 0.0,
                    "weight": 0.0,
                    "field_type": "content",
                },
                {
                    "subject": {
                        "content": ["Completion", "Date"],
                        "lemma_content": ["completion", "Date"],
                        "pos": ["NOUN", "PROPN"],
                        "positions": [44, 45],
                        "label": "pattern_syntagm_or_prep_group",
                    },
                    "property": {
                        "content": ["is", "defined", "in"],
                        "lemma_content": ["be", "define", "in"],
                        "pos": ["VERB", "VERB", "ADP"],
                        "positions": [46, 47, 48],
                        "label": "pattern_verb_phrase",
                    },
                    "value": {
                        "content": ["Indenture"],
                        "lemma_content": ["Indenture"],
                        "pos": ["PROPN"],
                        "positions": [54],
                        "label": "organization",
                    },
                    "automatically_fill": True,
                    "confidence": 0.0,
                    "weight": 0.0,
                    "field_type": "content",
                },
                {
                    "subject": {
                        "content": ["definition"],
                        "lemma_content": ["definition"],
                        "pos": ["NOUN"],
                        "positions": [59],
                        "label": "pattern_syntagm_or_prep_group",
                    },
                    "property": {
                        "content": ["is", "exactly"],
                        "lemma_content": ["be", "exactly"],
                        "pos": ["VERB", "ADV"],
                        "positions": [60, 61],
                        "label": "pattern_verb_phrase",
                    },
                    "value": {
                        "content": ["same"],
                        "lemma_content": ["same"],
                        "pos": ["ADJ"],
                        "positions": [63],
                        "label": "pattern_syntagm_or_prep_group",
                    },
                    "automatically_fill": True,
                    "confidence": 0.0,
                    "weight": 0.0,
                    "field_type": "content",
                },
                {
                    "subject": {
                        "content": ["Approval", "of", "these", "specifications"],
                        "lemma_content": ["approval", "of", "these", "specification"],
                        "pos": ["NOUN", "ADP", "DET", "NOUN"],
                        "positions": [113, 114, 115, 116],
                        "label": "pattern_syntagm_or_prep_group",
                    },
                    "property": {
                        "content": ["must", "be", "made", "by"],
                        "lemma_content": ["must", "be", "make", "by"],
                        "pos": ["AUX", "VERB", "VERB", "ADP"],
                        "positions": [117, 118, 119, 120],
                        "label": "pattern_verb_phrase",
                    },
                    "value": {
                        "content": ["independent", "engineer"],
                        "lemma_content": ["independent", "engineer"],
                        "pos": ["ADJ", "NOUN"],
                        "positions": [122, 123],
                        "label": "pattern_syntagm_or_prep_group",
                    },
                    "automatically_fill": True,
                    "confidence": 0.0,
                    "weight": 0.0,
                    "field_type": "content",
                },
                {
                    "subject": {
                        "content": ["Approval"],
                        "lemma_content": ["approval"],
                        "pos": ["NOUN"],
                        "positions": [113],
                        "label": "dep_subject",
                    },
                    "property": {
                        "content": ["must", "be", "made"],
                        "lemma_content": ["must", "be", "make"],
                        "pos": ["AUX", "VERB", "VERB"],
                        "positions": [117, 118, 119],
                        "label": "dep_verb",
                    },
                    "value": {
                        "content": ["engineer"],
                        "lemma_content": ["engineer"],
                        "pos": ["NOUN"],
                        "positions": [123],
                        "label": "dep_object",
                    },
                    "automatically_fill": True,
                    "confidence": 0.0,
                    "weight": 0.0,
                    "field_type": "content",
                },
                {
                    "subject": {
                        "content": ["approach"],
                        "lemma_content": ["approach"],
                        "pos": ["NOUN"],
                        "positions": [135],
                        "label": "pattern_syntagm_or_prep_group",
                    },
                    "property": {
                        "content": ["regarding"],
                        "lemma_content": ["regard"],
                        "pos": ["VERB"],
                        "positions": [136],
                        "label": "pattern_verb_phrase",
                    },
                    "value": {
                        "content": ["completion"],
                        "lemma_content": ["completion"],
                        "pos": ["NOUN"],
                        "positions": [137],
                        "label": "pattern_syntagm_or_prep_group",
                    },
                    "automatically_fill": True,
                    "confidence": 0.0,
                    "weight": 0.0,
                    "field_type": "content",
                },
                {
                    "subject": {
                        "content": ["LC"],
                        "lemma_content": ["LC"],
                        "pos": ["PROPN"],
                        "positions": [166],
                        "label": "pattern_syntagm_or_prep_group",
                    },
                    "property": {
                        "content": ["expires", "on"],
                        "lemma_content": ["expire", "on"],
                        "pos": ["VERB", "ADP"],
                        "positions": [167, 168],
                        "label": "pattern_verb_phrase",
                    },
                    "value": {
                        "content": ["June", "30"],
                        "lemma_content": ["June", "30"],
                        "pos": ["PROPN", "NUM"],
                        "positions": [169, 170],
                        "label": "date",
                    },
                    "automatically_fill": True,
                    "confidence": 0.0,
                    "weight": 0.0,
                    "field_type": "content",
                },
                {
                    "subject": {
                        "content": ["LC"],
                        "lemma_content": ["LC"],
                        "pos": ["PROPN"],
                        "positions": [166],
                        "label": "pattern_syntagm_or_prep_group",
                    },
                    "property": {
                        "content": ["expires", "on"],
                        "lemma_content": ["expire", "on"],
                        "pos": ["VERB", "ADP"],
                        "positions": [167, 168],
                        "label": "pattern_verb_phrase",
                    },
                    "value": {
                        "content": ["June", "30"],
                        "lemma_content": ["June", "30"],
                        "pos": ["PROPN", "NUM"],
                        "positions": [169, 170],
                        "label": "date",
                    },
                    "automatically_fill": True,
                    "confidence": 0.0,
                    "weight": 0.0,
                    "field_type": "content",
                },
            ]
            cid = "autogenerated-" + str("xxx")
            log_context = LogUserContext(cid)
            tagger = SyntacticTagger(config=config, call_context=log_context)
            tkeir_doc = tagger.tag(tkeir_doc)
            self.assertEqual(test["title_deps"], tkeir_doc["title_deps"])


