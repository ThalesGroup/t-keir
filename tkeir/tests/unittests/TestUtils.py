"""Tests for thot.core.Utils helpers."""

import os
import time

import pytest

from thot.core.Utils import (
    ThotTokenizerToSpacy,
    apply_use_mwe_to_entries,
    check_pid,
    config_use_mwe,
    generate_id,
    is_email,
    is_numeric,
    load_json,
    mkdir_p,
    save_json,
    set_if_not_exists,
    str_to_uni,
    timelimit,
    type_to_bool,
)


def myrunfun(timewait):
    time.sleep(timewait)
    return 3


class TestUtils:
    def test_check_pid(self):
        assert not check_pid(123)
        assert check_pid(os.getpid())

    def test_timelimit(self):
        result = timelimit(50, myrunfun, args=(2,))
        assert result == 3
        try:
            timelimit(1, myrunfun, args=(5,))
            assert False, "expected timeout"
        except Exception:
            pass

    def test_mkdir_p(self):
        mkdir_p("/tmp/tkeir-test-utils")
        assert os.path.isdir("/tmp/tkeir-test-utils")

    def test_type_to_bool(self):
        assert type_to_bool("1")
        assert type_to_bool(1)
        assert type_to_bool("TrUe")
        assert not type_to_bool("0")
        assert not type_to_bool(0)
        assert not type_to_bool("fAlSe")
        with pytest.raises(ValueError):
            type_to_bool([])

    def test_is_numeric(self):
        assert is_numeric(1)
        assert is_numeric(1.0)
        assert not is_numeric("aaa&ze")

    def test_json_save_and_load(self):
        data = {"test-me": "test", "is-json": True}
        save_json(data, "/tmp/file.json")
        loaded_data = load_json("/tmp/file.json")
        assert data == loaded_data

    def test_json_save_and_load_zip(self):
        data = {"test-me": "test", "is-json": True}
        save_json(data, "/tmp/file.json.gz", zip_file=True)
        loaded_data = load_json("/tmp/file.json.gz", zip_file=True)
        assert data == loaded_data

    def test_load_json_falls_back_to_gzip(self):
        data = {"gzip": True}
        save_json(data, "/tmp/file-auto.json.gz", zip_file=True)
        loaded_data = load_json("/tmp/file-auto.json.gz", zip_file=False)
        assert loaded_data == data

    def test_set_if_not_exists(self):
        payload = {"keep": 1}
        set_if_not_exists(payload, "keep", 2)
        set_if_not_exists(payload, "add", 3)
        assert payload == {"keep": 1, "add": 3}

    def test_generate_id(self):
        generated = generate_id(prefix="test", length=8)
        assert generated.startswith("test-")
        assert "test-" in generated

    def test_is_email(self):
        assert is_email("user.name@example.com")
        assert not is_email("not-an-email")

    def test_str_to_uni(self):
        assert str_to_uni("") == ""
        assert str_to_uni("u0041") == "A"

    def test_config_use_mwe_helpers(self):
        assert not config_use_mwe(None)
        assert config_use_mwe({"use-mwe": True})
        entries = [{"language": "en"}]
        apply_use_mwe_to_entries(entries, True)
        assert entries[0]["use-mwe"] is True
        assert entries[0]["mwe"] == "tkeir_mwe.pkl"

    def test_type_to_bool_bool(self):
        assert type_to_bool(True)
        assert not type_to_bool(False)

    def test_thot_tokenizer_to_spacy(self):
        from spacy.lang.en import English

        nlp = English()
        tokenizer = ThotTokenizerToSpacy(nlp.vocab)
        nested = [
            [
                {"token": "Hello", "start_sentence": True},
                {"token": "world", "start_sentence": False},
            ]
        ]
        doc = tokenizer(nested)
        assert [token.text for token in doc] == ["Hello", "world"]
        assert doc[0].is_sent_start
        assert not doc[1].is_sent_start

    def test_thot_tokenizer_to_spacy_large_flat_list(self):
        from spacy.lang.en import English

        nlp = English()
        tokenizer = ThotTokenizerToSpacy(nlp.vocab)
        tokens = [
            {"token": f"word{i}", "start_sentence": i == 0}
            for i in range(50000)
        ]
        started = time.perf_counter()
        doc = tokenizer(tokens)
        elapsed = time.perf_counter() - started
        assert len(doc) == 50000
        assert elapsed < 2.0

    def test_thot_tokenizer_to_spacy_with_mwe_concepts(self):
        from spacy.lang.en import English

        nlp = English()
        tokenizer = ThotTokenizerToSpacy(nlp.vocab, use_mwe=True)
        token_entry = {
            "token": "Paris",
            "start_sentence": True,
            "mwe": {
                "data": {
                    "Paris": {
                        "data": [{"type": "concept", "label": "Paris"}],
                        "pos": "PROPN",
                    }
                }
            },
        }
        doc = tokenizer([token_entry], pre_tagging_with_concept=True)
        assert doc[0].text == "Paris"
        assert doc[0].tag_ == "NNP"
        assert doc[0]._.advanced_tag

    def test_is_numeric_string_digits(self):
        assert is_numeric("42")
        assert is_numeric("3.14")
        assert is_numeric(1 + 2j)
