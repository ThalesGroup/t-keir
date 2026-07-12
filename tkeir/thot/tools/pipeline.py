# -*- coding: utf-8 -*-
"""Unified T-KEIR pipeline CLI."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import traceback

import thot.core.Constants as Constants
from thot.core.ThotLogger import LogUserContext, ThotLogger
from thot.tasks.converters.InputFormat import (
    AUTO_DATATYPE,
    detect_input_format,
)
from thot.tasks.pipeline.PipelineConfiguration import PipelineConfiguration
from thot.tasks.pipeline.PipelineRunner import PipelineRunner
from thot.tasks.pipeline.PipelineTasks import parse_tasks


def _is_tkeir_document(path: str) -> bool:
    """Return whether a JSON file is already a T-KEIR analyzed document.

    Args:
        path: Filesystem path to a candidate JSON file.

    Returns:
        ``True`` when the payload contains ``content`` or ``content_tokens``.

    Example:
        >>> import json, tempfile, os
        >>> from thot.tools.pipeline import _is_tkeir_document
        >>> with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        ...     json.dump({"content": ["hello"]}, handle)
        ...     path = handle.name
        >>> try:
        ...     _is_tkeir_document(path)
        ... finally:
        ...     os.unlink(path)
        True
    """
    if not path.endswith(".json"):
        return False
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    return isinstance(payload, dict) and (
        "content" in payload or "content_tokens" in payload
    )


def _process_file(
    runner: PipelineRunner,
    input_file: str,
    output_dir: str,
    datatype: str,
    call_context=None,
    tasks: list[str] | None = None,
):
    """Run the pipeline for one input file and write ``*.pipeline.json`` output.

    Args:
        runner: Configured pipeline runner instance.
        input_file: Path to a raw document or pre-converted T-KEIR JSON file.
        output_dir: Directory where pipeline output is written.
        datatype: Converter datatype hint for non-JSON inputs.
        call_context: Optional logging context propagated to the runner.
        tasks: Optional subset of pipeline tasks to execute.

    Returns:
        Absolute path to the written pipeline JSON file.

    Example:
        >>> from thot.tools.pipeline import _process_file
        >>> _process_file(None, "input.pdf", "/tmp/out", "auto")  # doctest: +SKIP
    """
    os.makedirs(output_dir, exist_ok=True)
    file_context = (
        LogUserContext(call_context["correlation-id"])
        if call_context
        else LogUserContext("pipeline-cli")
    )
    if call_context:
        file_context.update(call_context)
    file_context["input-file"] = os.path.abspath(input_file)
    if _is_tkeir_document(input_file):
        with open(input_file, encoding="utf-8") as handle:
            document = json.load(handle)
        file_context["source-file-size-bytes"] = os.path.getsize(input_file)
        result = runner.run_converted(
            document, call_context=file_context, tasks=tasks
        )
        output_name = os.path.basename(input_file)
        if not output_name.endswith(".pipeline.json"):
            output_name = output_name.replace(".json", ".pipeline.json")
    else:
        with open(input_file, "rb") as handle:
            raw_data = handle.read()
        file_context["source-file-size-bytes"] = len(raw_data)
        resolved_type = detect_input_format(input_file, raw_data, datatype)
        if datatype in (AUTO_DATATYPE, "", None) or resolved_type != datatype:
            ThotLogger.info(
                "Detected converter datatype '"
                + resolved_type
                + "' for "
                + os.path.basename(input_file),
                context=file_context,
            )
        encoded = base64.b64encode(raw_data).decode()
        payload = {
            "datatype": resolved_type,
            "data": encoded,
            "source": "file://" + os.path.abspath(input_file),
        }
        result = runner.run(payload, call_context=file_context, tasks=tasks)
        output_name = os.path.basename(input_file) + ".pipeline.json"

    output_path = os.path.join(output_dir, output_name)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
    ThotLogger.info("Wrote " + output_path, context=file_context)
    return output_path


def _collect_inputs(input_path: str) -> list:
    """Collect input files from a file path or directory tree.

    Args:
        input_path: Single file or directory passed to the pipeline CLI.

    Returns:
        Sorted list of absolute file paths.

    Example:
        >>> import tempfile, os
        >>> from thot.tools.pipeline import _collect_inputs
        >>> with tempfile.TemporaryDirectory() as temp_dir:
        ...     open(os.path.join(temp_dir, "b.txt"), "w").close()
        ...     open(os.path.join(temp_dir, "a.txt"), "w").close()
        ...     paths = _collect_inputs(temp_dir)
        ...     [os.path.basename(path) for path in paths]
        ['a.txt', 'b.txt']
    """
    if os.path.isfile(input_path):
        return [input_path]
    files = []
    for root, _, filenames in os.walk(input_path):
        for filename in filenames:
            files.append(os.path.join(root, filename))
    return sorted(files)


def main(args=None):
    """Parse CLI arguments and run the T-KEIR pipeline over input files.

    Args:
        args: Optional argument list for testing; defaults to ``sys.argv``.

    Example:
        >>> from thot.tools.pipeline import main
        >>> main(["-c", "cfg.json", "-i", "in", "-o", "out"])  # doctest: +SKIP
    """
    parser = argparse.ArgumentParser(
        description="Run the full T-KEIR NLP pipeline"
    )
    parser.add_argument(
        "-c", "--config", required=True, help="pipeline configuration file"
    )
    parser.add_argument(
        "-i", "--input", required=True, help="input file or directory"
    )
    parser.add_argument(
        "-o", "--output", required=True, help="output directory"
    )
    parser.add_argument(
        "-t",
        "--type",
        default=AUTO_DATATYPE,
        help=(
            "converter datatype for non-JSON inputs; use 'auto' to detect "
            "from extension and file content (default: auto). "
            "Examples: pdf, docx, email, raw"
        ),
    )
    parser.add_argument(
        "--tasks",
        help=(
            "Comma-separated pipeline tasks to run; dependencies are "
            "included automatically. Available: converter, tokenizer, "
            "morphosyntax, ner, syntax, keywords, chunking, ontology, "
            "chunk-questions. Default: all tasks."
        ),
    )
    parser.add_argument(
        "--use-mwe",
        action="store_true",
        help=(
            "Enable MWE compound-word detection and concept pre-tagging in "
            "tokenizer, morphosyntax, NER, and syntax (slower; disabled by "
            "default)."
        ),
    )
    parsed = parser.parse_args(args)
    tasks = parse_tasks(parsed.tasks)

    try:
        config = PipelineConfiguration()
        with open(parsed.config, encoding="utf-8") as handle:
            config.load(handle)
        if parsed.use_mwe:
            config.apply_use_mwe(True)
        ThotLogger.loads(
            config.logger_config.configuration, logger_name="pipeline"
        )
        runner = PipelineRunner(config)
        call_context = LogUserContext("pipeline-cli")
        processed = 0
        failed = 0
        for input_file in _collect_inputs(parsed.input):
            file_context = LogUserContext(call_context["correlation-id"])
            file_context.update(call_context)
            file_context["input-file"] = os.path.abspath(input_file)
            try:
                _process_file(
                    runner,
                    input_file,
                    parsed.output,
                    parsed.type,
                    call_context=file_context,
                    tasks=tasks,
                )
                processed += 1
            except Exception as error:
                failed += 1
                ThotLogger.error(
                    "Pipeline skipped "
                    + os.path.basename(input_file)
                    + " after converter/pipeline error: "
                    + Constants.exception_error_and_trace(
                        str(error), traceback.format_exc()
                    ),
                    context=file_context,
                )
        if failed and not processed:
            sys.exit(1)
    except Exception as error:
        ThotLogger.error(
            "Pipeline failed: "
            + Constants.exception_error_and_trace(
                str(error), traceback.format_exc()
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
