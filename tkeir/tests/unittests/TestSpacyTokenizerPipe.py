"""Regression tests for SpacyTokenizerPipe without MWE."""

from spacy.tokens import Doc

from thot.core.SpacyModelLoader import load_spacy_model
from thot.tasks.tokenizer.Tokenizer import SpacyTokenizerPipe


def test_call_returns_doc_when_mwe_disabled():
    nlp, _ = load_spacy_model("en", size="sm")
    config = {
        "segmenters": [
            {
                "language": "en",
                "resources-base-path": "resources/modeling/tokenizer/en",
            }
        ]
    }
    pipe = SpacyTokenizerPipe(nlp=nlp, config=config)
    assert pipe._mwes is None

    doc = Doc(nlp.vocab, words=["Hello", "world", "."])
    result = pipe(doc)

    assert result is not None
    assert [token.text for token in result] == ["Hello", "world", "."]
