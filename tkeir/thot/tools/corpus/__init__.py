"""Title: Record-oriented corpus tools

Library to build ``{"dataset": {…}, "records": […]}`` JSON for
``POST /ingest/json-records``.

Records require ``doc_id``, ``title``, and ``text``. Source documents
are markdown files, or a mixed-format tree converted with
:class:`UniversalConverter` into a parallel markdown directory.

CLI: ``python -m thot.tools.corpus`` or ``tkeir-corpus``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.tools.corpus.builder import (
    build_dataset,
    corpus_from_markdown_dir,
    corpus_from_source_dir,
    write_record_corpus,
)
from thot.tools.corpus.convert_tree import (
    convert_source_tree,
)
from thot.tools.corpus.markdown_records import (
    markdown_file_to_record,
    parse_markdown_record,
)
from thot.tools.corpus.schema import (
    REQUIRED_RECORD_FIELDS,
    validate_record_corpus,
)

__all__ = [
    "REQUIRED_RECORD_FIELDS",
    "build_dataset",
    "convert_source_tree",
    "corpus_from_markdown_dir",
    "corpus_from_source_dir",
    "markdown_file_to_record",
    "parse_markdown_record",
    "validate_record_corpus",
    "write_record_corpus",
]
