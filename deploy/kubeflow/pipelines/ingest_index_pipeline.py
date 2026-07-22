"""Title: Kubeflow Pipelines — ingest → pipeline → index skeleton (P4).

This module is intentionally lightweight: it defines the pipeline graph as
Python that can be compiled with the KFP SDK when Kubeflow is installed.
Without KFP, `make kubeflow-run-ingest` prints the planned steps.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PipelineStep:
    name: str
    command: list[str]
    artifacts: list[str] = field(default_factory=list)


def ingest_index_pipeline(
    *,
    source_uri: str,
    pipeline_config: str = "configs/pipeline.yaml",
) -> list[PipelineStep]:
    """Return ordered steps for fixture ingest + index."""
    return [
        PipelineStep(
            name="fetch",
            command=["tkeir-ingest", "fetch", source_uri],
            artifacts=["raw.sha256"],
        ),
        PipelineStep(
            name="pipeline",
            command=["tkeir-pipeline", "--config", pipeline_config],
            artifacts=["pipeline.json"],
        ),
        PipelineStep(
            name="index",
            command=["tkeir-index-documents", "--input", "pipeline.json"],
            artifacts=["vespa.feed.json"],
        ),
        PipelineStep(
            name="verify",
            command=["curl", "-fsS", "http://tkeir-api:8090/health"],
            artifacts=["health.json"],
        ),
    ]


def main() -> None:
    import json
    import sys

    uri = sys.argv[1] if len(sys.argv) > 1 else "file:///fixtures"
    steps = ingest_index_pipeline(source_uri=uri)
    print(json.dumps([step.__dict__ for step in steps], indent=2))


if __name__ == "__main__":
    main()
