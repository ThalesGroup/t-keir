# Operation and Management

This section describes how to run and check the T-KEIR pipeline locally.

## Run the pipeline

From the repository root:

```shell
tkeir-pipeline -c tkeir/configs/pipeline.yaml -i <INPUT FILE OR DIR> -o <OUTPUT DIR> -t auto
```

Use `-t raw` for plain text only. `make pipeline` defaults to `PIPELINE_TYPE=auto`.

Run a subset of tasks:

```shell
tkeir-pipeline -c tkeir/configs/pipeline.yaml -i <INPUT> -o <OUTPUT> -t raw --tasks tokenizer,morphosyntax
```

## Validate configuration

Task configuration files under `tkeir/configs/` contain only `logger` settings and task-specific options. They no longer require `network` or `runtime` sections.

Load and test configuration parsing:

```shell
python3 -m pytest tests/unittests/TestPipelineConfiguration.py
```

## Observability

T-KEIR records counters through **OpenTelemetry** (`thot.core.ThotMetrics`). Metrics are exposed in Prometheus exposition format for scraping by Prometheus, Grafana, or any OTLP-compatible collector.

The RAG API (`tkeir-rag`) exposes:

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness — Vespa reachable |
| `GET /ready` | Readiness — Vespa + configured `PROVIDER` |
| `GET /metrics` | Prometheus exposition |

Every HTTP response includes `X-Correlation-Id` (W3C trace-id). Non-probe
requests emit an observe-mode [ActionRecord](regularity-component/action-identiy.md) into the
in-process sink (audit store lands in a later profile).

Structured JSON logs (fields `ts`, `level`, `service`, `version`,
`correlation_id`, `action_id`, `actor`, `msg`) are configured for the RAG
service via `thot.core.StructuredLogging`. Set `TKEIR_SERVICE` to override the
service name.

Logger error events increment the `logger_errors` counter automatically. Custom counters can be created with `ThotMetrics.create_counter()` and `ThotMetrics.increment_counter()`.

```python
from thot.core.ThotMetrics import ThotMetrics

ThotMetrics.create_counter(
    short_name="pipeline-run",
    function_name="pipeline_run_total",
    counter_description="Pipeline run count",
)
ThotMetrics.increment_counter(
    short_name="pipeline-run",
    method="POST",
    path="/api/pipeline/run",
    status=200,
)
payload = ThotMetrics.generateMetricsResponse()
```

Set `OTEL_EXPORTER_OTLP_ENDPOINT` when exporting metrics to an OTLP collector in addition to the in-process Prometheus reader.

## Tools lifecycle and release

Releases are tagged on the GitHub repository when important features and bug fixes are completed.
