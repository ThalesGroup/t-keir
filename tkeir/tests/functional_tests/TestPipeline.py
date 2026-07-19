"""Functional tests for unified pipeline CLI."""

import json
import os
import tempfile
from unittest.mock import patch

from thot.tools import pipeline as pipeline_cli


class TestPipelineFunctional:
    @patch("thot.tools.pipeline.detect_input_format", return_value="raw")
    @patch("thot.tools.pipeline.PipelineRunner")
    @patch("thot.tools.pipeline.PipelineConfiguration")
    def test_cli_processes_raw_file(
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
            mock_runner = mock_runner_cls.return_value
            mock_runner.run.return_value = {
                "content": ["English pipeline text for testing purposes."],
                "language-detection": {"language": "en", "confidence": 0.9},
                "keywords": [],
            }

            config_path = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    "../fixtures/configs/pipeline.yaml",
                )
            )
            if not os.path.isfile(config_path):
                config_path = os.path.abspath(
                    os.path.join(
                        os.path.dirname(__file__),
                        "../../configs/pipeline.yaml",
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
            with open(output_file, encoding="utf-8") as handle:
                payload = json.load(handle)
            assert "language-detection" in payload
