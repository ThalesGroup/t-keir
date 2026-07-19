"""Tests for pipeline CLI helpers."""

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from thot.tools import pipeline as pipeline_cli


class TestPipeline:
    def test_is_tkeir_document(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False
        ) as handle:
            json.dump({"content": ["hello"]}, handle)
            path = handle.name
        try:
            assert pipeline_cli._is_tkeir_document(path)
        finally:
            os.unlink(path)

    def test_collect_inputs_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = os.path.join(temp_dir, "a.txt")
            second = os.path.join(temp_dir, "b.txt")
            open(first, "w", encoding="utf-8").close()
            open(second, "w", encoding="utf-8").close()
            collected = pipeline_cli._collect_inputs(temp_dir)
            assert collected == sorted([first, second])

    @patch("thot.tools.pipeline.detect_input_format", return_value="raw")
    @patch("thot.tools.pipeline.PipelineRunner")
    @patch("thot.tools.pipeline.PipelineConfiguration")
    def test_main_passes_tasks_to_runner(
        self,
        mock_config_cls,
        mock_runner_cls,
        _mock_detect,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_file = os.path.join(temp_dir, "sample.txt")
            output_dir = os.path.join(temp_dir, "out")
            with open(input_file, "w", encoding="utf-8") as handle:
                handle.write("English pipeline text for testing purposes.")

            mock_config = mock_config_cls.return_value
            mock_config.logger_config.configuration = {
                "logger": {"logging-level": "error"}
            }
            mock_runner_cls.return_value.run.return_value = {
                "content": ["English pipeline text for testing purposes."],
            }
            config_path = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__), "../../configs/pipeline.yaml"
                )
            )

            pipeline_cli.main(
                [
                    "-c",
                    config_path,
                    "-i",
                    input_file,
                    "-o",
                    output_dir,
                    "--tasks",
                    "tokenizer",
                ]
            )
            _, kwargs = mock_runner_cls.return_value.run.call_args
            assert kwargs["tasks"] == ["tokenizer"]

    @patch("thot.tools.pipeline.detect_input_format", return_value="raw")
    @patch("thot.tools.pipeline.PipelineRunner")
    @patch("thot.tools.pipeline.PipelineConfiguration")
    def test_main_applies_use_mwe(
        self,
        mock_config_cls,
        mock_runner_cls,
        _mock_detect,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_file = os.path.join(temp_dir, "sample.txt")
            output_dir = os.path.join(temp_dir, "out")
            with open(input_file, "w", encoding="utf-8") as handle:
                handle.write("English pipeline text for testing purposes.")

            mock_config = mock_config_cls.return_value
            mock_config.logger_config.configuration = {
                "logger": {"logging-level": "error"}
            }
            mock_runner_cls.return_value.run.return_value = {
                "content": ["English pipeline text for testing purposes."],
            }
            config_path = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__), "../../configs/pipeline.yaml"
                )
            )

            pipeline_cli.main(
                [
                    "-c",
                    config_path,
                    "-i",
                    input_file,
                    "-o",
                    output_dir,
                    "--use-mwe",
                ]
            )
            mock_config.apply_use_mwe.assert_called_once_with(True)

    @patch("thot.tools.pipeline.detect_input_format", return_value="raw")
    @patch("thot.tools.pipeline.PipelineRunner")
    @patch("thot.tools.pipeline.PipelineConfiguration")
    def test_main_writes_pipeline_output(
        self, mock_config_cls, mock_runner_cls, _mock_detect
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_file = os.path.join(temp_dir, "sample.txt")
            output_dir = os.path.join(temp_dir, "out")
            with open(input_file, "w", encoding="utf-8") as handle:
                handle.write("English pipeline text for testing purposes.")

            mock_config = mock_config_cls.return_value
            mock_config.logger_config.configuration = {
                "logger": {"logging-level": "error"}
            }
            mock_runner_cls.return_value.run.return_value = {
                "content": ["English pipeline text for testing purposes."],
                "language-detection": {"language": "en", "confidence": 0.9},
            }
            config_path = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__), "../../configs/pipeline.yaml"
                )
            )

            pipeline_cli.main(
                [
                    "-c",
                    config_path,
                    "-i",
                    input_file,
                    "-o",
                    output_dir,
                    "-t",
                    "raw",
                ]
            )
            output_file = os.path.join(output_dir, "sample.txt.pipeline.json")
            assert os.path.isfile(output_file)

    def test_process_tkeir_json_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_file = os.path.join(temp_dir, "doc.json")
            output_dir = os.path.join(temp_dir, "out")
            with open(input_file, "w", encoding="utf-8") as handle:
                json.dump({"content": ["already converted"]}, handle)

            with patch(
                "thot.tools.pipeline.PipelineRunner"
            ) as mock_runner_cls:
                mock_runner_cls.return_value.run_converted.return_value = {
                    "content": ["already converted"],
                    "language-detection": {"language": "en"},
                }
                with patch("thot.tools.pipeline.PipelineConfiguration"):
                    config_path = os.path.abspath(
                        os.path.join(
                            os.path.dirname(__file__),
                            "../../configs/pipeline.yaml",
                        )
                    )
                    pipeline_cli.main(
                        ["-c", config_path, "-i", input_file, "-o", output_dir]
                    )
            assert os.path.isfile(
                os.path.join(output_dir, "doc.pipeline.json")
            )

    def test_process_file_detects_pdf_datatype(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_file = os.path.join(temp_dir, "sample.pdf")
            output_dir = os.path.join(temp_dir, "out")
            with open(input_file, "wb") as handle:
                handle.write(b"%PDF-1.4\n")

            with patch(
                "thot.tools.pipeline.PipelineRunner"
            ) as mock_runner_cls:
                mock_runner_cls.return_value.run.return_value = {
                    "content": ["converted"],
                }
                with patch("thot.tools.pipeline.PipelineConfiguration"):
                    pipeline_cli._process_file(
                        mock_runner_cls.return_value,
                        input_file,
                        output_dir,
                        pipeline_cli.AUTO_DATATYPE,
                    )
            payload = mock_runner_cls.return_value.run.call_args[0][0]
            assert payload["datatype"] == "pdf"

    def test_main_exits_on_error(self):
        with pytest.raises(SystemExit):
            pipeline_cli.main(
                [
                    "-c",
                    "/path/does/not/exist.json",
                    "-i",
                    "/path/does/not/exist",
                    "-o",
                    "/tmp",
                ]
            )

    @patch("thot.tools.pipeline.detect_input_format", return_value="raw")
    @patch("thot.tools.pipeline.PipelineRunner")
    @patch("thot.tools.pipeline.PipelineConfiguration")
    def test_main_continues_after_file_failure(
        self,
        mock_config_cls,
        mock_runner_cls,
        _mock_detect,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = os.path.join(temp_dir, "in")
            output_dir = os.path.join(temp_dir, "out")
            os.makedirs(input_dir)
            first = os.path.join(input_dir, "good.txt")
            second = os.path.join(input_dir, "bad.txt")
            with open(first, "w", encoding="utf-8") as handle:
                handle.write("Good document text for testing.")
            with open(second, "w", encoding="utf-8") as handle:
                handle.write("Bad document text for testing.")

            mock_config = mock_config_cls.return_value
            mock_config.logger_config.configuration = {
                "logger": {"logging-level": "error"}
            }
            runner = mock_runner_cls.return_value

            def _run_effect(payload, call_context=None, tasks=None):
                if payload["source"].endswith("bad.txt"):
                    raise ValueError("converter failed")
                return {"content": ["Good document text for testing."]}

            runner.run.side_effect = _run_effect
            config_path = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__), "../../configs/pipeline.yaml"
                )
            )

            pipeline_cli.main(
                [
                    "-c",
                    config_path,
                    "-i",
                    input_dir,
                    "-o",
                    output_dir,
                ]
            )

            assert runner.run.call_count == 2
            assert os.path.isfile(
                os.path.join(output_dir, "good.txt.pipeline.json")
            )
            assert not os.path.isfile(
                os.path.join(output_dir, "bad.txt.pipeline.json")
            )
