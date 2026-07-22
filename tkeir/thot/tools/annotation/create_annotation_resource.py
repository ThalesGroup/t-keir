"""Title: Create annotation resource

Create annotation MWE trie from lexicon configuration.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import json
import logging
import traceback

from thot import __author__
from thot.core.ThotLogger import ThotLogger
from thot.tools.annotation import __date_annotation__, __version_annotation__
from thot.tools.annotation.AnnotationConfiguration import (
    AnnotationConfiguration,
)
from thot.tools.annotation.AnnotationResources import AnnotationResources


def main() -> int:
    """Build an annotation MWE trie from a JSON entries file.

    Returns:
        Process exit code (``0`` on success, ``1`` on failure).

    Example:
        >>> from thot.tools.annotation.create_annotation_resource import main
        >>> main()  # doctest: +SKIP
    """
    print("Resource Annotation")
    print("===================")
    print("Version: " + __version_annotation__)
    print("Author:  " + __author__)
    print("Date:    " + __date_annotation__)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--entries-file",
        type=str,
        default=None,
        help="file containing dataset",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="tkeir_mwe.pkl",
        help="tokenizer multi word expression",
    )
    try:
        args = parser.parse_args()
    except Exception as error:
        logging.error("Exception raised: %s", error)
        return 1

    if not args.entries_file:
        print("--entries-file is required")
        return 1

    try:
        with open(args.entries_file, encoding="utf-8") as config_f:
            a_config = json.load(config_f)
        annot_config = AnnotationConfiguration()
        annot_modeling = AnnotationResources()
        ThotLogger.loads(a_config, logger_name="annotation")
        annot_config.loads(a_config)
        annot_modeling.createModel(annot_config.configuration, args.output)
    except Exception as error:
        print(
            "An error occured. Exception"
            + str(error)
            + ", trace:"
            + str(traceback.format_exc())
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
