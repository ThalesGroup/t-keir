"""Tests for raw text converter."""

import os

from thot.tasks.converters.RawTextConverter import RawTextConverter


class TestRawConverter:
    def test_converter(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        mail_path = os.path.join(
            dir_path, "../fixtures/test-raw/mail/mail1.txt"
        )
        with open(mail_path, "rb") as handle:
            data = handle.read()
        document = RawTextConverter.convert(data, "file://mail1.txt")
        assert document["source_doc_id"] == "file://mail1.txt"
        assert document["content"]
        assert document["error"] is False
