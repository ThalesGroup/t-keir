"""Test converter
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""

import base64
import json
import os

import pytest

from thot.tasks.converters.Converter import Converter
from thot.tasks.converters.ConverterConfiguration import ConverterConfiguration


class TestConverter:
    def test_listType(self):
        assert set(Converter().listTypes()) == set(
            [
                "csv",
                "docx",
                "email",
                "epub",
                "htm",
                "html",
                "ipynb",
                "msg",
                "pdf",
                "ppt",
                "pptx",
                "raw",
                "rss",
                "rtf",
                "tkeir",
                "xls",
                "xlsx",
                "xml",
            ]
        )

    def test_convert_raw(self):
        data = base64.b64encode(b"Hello converter").decode()
        document = Converter().convert(
            data_type="raw", data=data, source="file://sample.txt"
        )
        assert document["content"] == ["Hello converter"]
        assert document["source_doc_id"] == "file://sample.txt"
        assert document["error"] is False

    def test_convert_tkeir_fills_defaults(self):
        payload = {"content": ["Body only"]}
        data = base64.b64encode(json.dumps(payload).encode()).decode()
        document = Converter().convert(
            data_type="tkeir", data=data, source="file://doc.json"
        )
        assert document["title"] == ""
        assert document["content"] == ["Body only"]
        assert document["data_source"] == ""
        assert document["source_doc_id"] == ""
        assert document["kg"] == []

    def test_convert_tkeir_preserves_fields(self):
        payload = {
            "title": "Title",
            "content": ["Body"],
            "data_source": "test",
            "source_doc_id": "id-1",
            "kg": [{"subject": {"content": "x"}}],
        }
        data = base64.b64encode(json.dumps(payload).encode()).decode()
        document = Converter().convert(
            data_type="tkeir", data=data, source="file://doc.json"
        )
        assert document["title"] == "Title"
        assert document["content"] == ["Body"]
        assert document["data_source"] == "test"
        assert document["source_doc_id"] == "id-1"
        assert len(document["kg"]) == 1

    def test_convert_email_with_config(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        config_path = os.path.abspath(
            os.path.join(dir_path, "../fixtures/configs/converter.yaml")
        )
        mail_path = os.path.abspath(
            os.path.join(dir_path, "../fixtures/test-raw/mail/mail1.txt")
        )
        config = ConverterConfiguration()
        with open(config_path, encoding="utf-8") as handle:
            config.load(config_f=handle)
        with open(mail_path, "rb") as handle:
            data = base64.b64encode(handle.read()).decode()
        document = Converter(config=config).convert(
            data_type="email", data=data, source="file://mail1.txt"
        )
        assert document["content"]
        assert not document["error"]

    def test_convert_rejects_unknown_type(self):
        data = base64.b64encode(b"hello").decode()
        with pytest.raises(ValueError, match="not managed"):
            Converter().convert(data_type="unknown", data=data)

    def test_convert_requires_data(self):
        with pytest.raises(ValueError, match="mandatory"):
            Converter().convert(data_type="raw", data=None)

    def test_convert_rejects_binary_raw(self):
        data = base64.b64encode(b"%PDF-1.4\nbinary").decode()
        with pytest.raises(ValueError, match="Binary documents cannot"):
            Converter().convert(data_type="raw", data=data)

    def test_convert_rejects_empty_document(self):
        payload = {"title": "", "content": ""}
        data = base64.b64encode(json.dumps(payload).encode()).decode()
        with pytest.raises(ValueError, match="empty"):
            Converter().convert(data_type="tkeir", data=data)

    def test_convert_adds_tags_to_kg(self):
        data = base64.b64encode(b"Tagged content").decode()
        document = Converter().convert(
            data_type="raw",
            data=data,
            source="file://tagged.txt",
            tags=["Alpha", "Beta"],
        )
        assert len(document["kg"]) == 2
        assert document["kg"][0]["subject"]["content"] == "Alpha"
        assert document["kg"][1]["subject"]["content"] == "Beta"

    def test_run(self):
        data = base64.b64encode(b"Run path").decode()
        document = Converter().run(
            {
                "datatype": "raw",
                "data": data,
                "source": "file://run.txt",
            }
        )
        assert document["content"] == ["Run path"]
