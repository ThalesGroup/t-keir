"""Run pipeline + optional Vespa indexing for ingest jobs."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from thot.action.correlation import current_correlation_id
from thot.action.models import new_action_id, utc_now_rfc3339
from thot.core.LlmWrapper import UnifiedLLMWrapper
from thot.core.ThotLogger import LogUserContext
from thot.core.TkeirPaths import configs_dir
from thot.governor.client import GovernorClient
from thot.ingest.config import IngestSettings, ingest_settings
from thot.ingest.fetch import FetchError, doc_id_from_content, fetch_bytes
from thot.ingest.manifest import (
    build_manifest,
    embedder_fingerprint,
    idempotency_key,
    pipeline_config_sha256,
)
from thot.ingest.models import (
    EmbedderInfo,
    IngestJob,
    IngestJobStatus,
    IngestManifest,
    LineageInfo,
    SourceInfo,
)
from thot.ingest.store import IngestStore
from thot.tasks.converters.InputFormat import (
    AUTO_DATATYPE,
    detect_input_format,
)
from thot.tasks.pipeline.PipelineConfiguration import PipelineConfiguration
from thot.tasks.pipeline.PipelineRunner import PipelineRunner
from thot.tools.search.index_documents import index_pipeline_document
from thot.tools.search.vespa_client import VespaClient

LOGGER = logging.getLogger(__name__)

PipelineFn = Callable[
    [PipelineRunner, bytes, str, str],
    dict[str, Any],
]
IndexFn = Callable[[dict[str, Any]], Awaitable[int]]


def _default_pipeline_config_path(settings: IngestSettings) -> Path:
    if settings.pipeline_config_path.is_file():
        return settings.pipeline_config_path
    return Path(configs_dir()) / "pipeline.yaml"


def _load_runner(config_path: Path) -> PipelineRunner:
    config = PipelineConfiguration()
    with config_path.open(encoding="utf-8") as handle:
        config.load(handle)
    return PipelineRunner(config)


def run_pipeline_on_bytes(
    runner: PipelineRunner,
    content: bytes,
    filename: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Execute the NLP pipeline on raw document bytes."""
    suffix = Path(filename).suffix or ".bin"
    call_context = LogUserContext(correlation_id)
    call_context["input-file"] = filename
    call_context["source-file-size-bytes"] = len(content)

    with tempfile.TemporaryDirectory(prefix="tkeir-ingest-") as temp_dir:
        input_path = Path(temp_dir) / f"source{suffix}"
        input_path.write_bytes(content)
        if input_path.suffix == ".json":
            with input_path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict) and (
                "content" in payload or "content_tokens" in payload
            ):
                return runner.run_converted(
                    payload,
                    call_context=call_context,
                )
        resolved_type = detect_input_format(
            str(input_path),
            content,
            AUTO_DATATYPE,
        )
        encoded = base64.b64encode(content).decode()
        payload = {
            "datatype": resolved_type,
            "data": encoded,
            "source": f"ingest://{filename}",
        }
        return runner.run(payload, call_context=call_context)


async def _default_index(
    document: dict[str, Any], *, user_space: str | None = None
) -> int:
    async with UnifiedLLMWrapper() as llm, VespaClient() as vespa:
        _, chunks = await index_pipeline_document(
            document,
            vespa=vespa,
            llm=llm,
            user_space=user_space,
        )
        return chunks


class IngestWorker:
    """Process ingest jobs with idempotency and DLQ semantics."""

    def __init__(
        self,
        store: IngestStore,
        *,
        settings: IngestSettings | None = None,
        pipeline_fn: PipelineFn | None = None,
        index_fn: IndexFn | None = None,
    ) -> None:
        self.store = store
        self.settings = settings or ingest_settings()
        self._pipeline_fn = pipeline_fn
        self._index_fn = index_fn

    def _embedder_info(self) -> EmbedderInfo:
        provider = os.getenv("PROVIDER", "ollama")
        model = os.getenv("EMBEDDING_MODEL", "bge-m3")
        digest = embedder_fingerprint(provider=provider, model=model)
        return EmbedderInfo(model=model, provider=provider, sha256=digest)

    async def process_source(
        self,
        *,
        ingest_id: str,
        correlation_id: str,
        source_uri: str,
        content: bytes | None = None,
        filename: str | None = None,
        content_type: str | None = None,
        batch_id: str | None = None,
        user_space: str | None = None,
    ) -> IngestJob:
        """Fetch (when needed), stage, pipeline, and optionally index."""
        from thot.tools.search.user_space import resolve_vespa_user_space

        existing_job = self.store.read_job(ingest_id)
        space = resolve_vespa_user_space(
            None,
            fallback=user_space
            or (existing_job.user_space if existing_job else None),
        )
        try:
            GovernorClient().assert_scope_active("ingest")
        except RuntimeError as exc:
            self.store.update_job(
                ingest_id,
                status=IngestJobStatus.FAILED,
                error=str(exc),
            )
            job = self.store.read_job(ingest_id)
            assert job is not None
            return job

        self.store.ensure_layout()
        if self.store.read_job(ingest_id) is None:
            now = utc_now_rfc3339()
            self.store.write_job(
                IngestJob(
                    ingest_id=ingest_id,
                    correlation_id=correlation_id,
                    status=IngestJobStatus.PENDING,
                    batch_id=batch_id,
                    created_at=now,
                    updated_at=now,
                    user_space=space,
                )
            )
        elif existing_job is not None and not existing_job.user_space:
            self.store.update_job(ingest_id, user_space=space)
        config_path = _default_pipeline_config_path(self.settings)
        pipeline_sha = pipeline_config_sha256(config_path)
        embedder = self._embedder_info()

        if content is None:
            try:
                content, resolved_name, fetched_type = await fetch_bytes(
                    source_uri,
                    filename=filename,
                )
            except FetchError as exc:
                self.store.update_job(
                    ingest_id,
                    status=IngestJobStatus.FAILED,
                    error=str(exc),
                )
                job = self.store.read_job(ingest_id)
                assert job is not None
                self.store.write_dlq(
                    ingest_id,
                    job=job,
                    manifest=None,
                    reason=str(exc),
                )
                return job
            filename = resolved_name
            content_type = content_type or fetched_type
        else:
            filename = filename or "upload.bin"

        doc_id = doc_id_from_content(content)
        key = idempotency_key(doc_id, pipeline_sha, embedder.sha256)
        existing = self.store.get_idempotency_record(key)
        if existing is not None:
            manifest = self.store.read_manifest(doc_id)
            if manifest is not None and manifest.status in {
                "indexed",
                "noop",
            }:
                rel_manifest = str(
                    self.store.manifest_path(doc_id).relative_to(
                        self.store.root
                    )
                )
                return self.store.update_job(
                    ingest_id,
                    status=IngestJobStatus.NOOP,
                    doc_id=doc_id,
                    manifest_path=rel_manifest,
                    noop=True,
                )

        source = SourceInfo(
            uri=source_uri,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
        )
        created_at = utc_now_rfc3339()
        manifest = build_manifest(
            ingest_id=ingest_id,
            correlation_id=correlation_id,
            doc_id=doc_id,
            source=source,
            pipeline_sha=pipeline_sha,
            embedder=embedder,
            created_at=created_at,
            lineage=LineageInfo(batch_id=batch_id),
        )
        self.store.stage_bytes(doc_id, content, filename=filename)
        manifest_path = self.store.write_manifest(manifest)
        rel_manifest = str(manifest_path.relative_to(self.store.root))
        self.store.update_job(
            ingest_id,
            status=IngestJobStatus.RUNNING,
            doc_id=doc_id,
            manifest_path=rel_manifest,
        )
        manifest.status = "running"
        self.store.write_manifest(manifest)

        try:
            if self._pipeline_fn is not None:
                runner = _load_runner(config_path)
                document = self._pipeline_fn(
                    runner,
                    content,
                    filename,
                    correlation_id,
                )
            else:
                runner = _load_runner(config_path)
                document = await asyncio.to_thread(
                    run_pipeline_on_bytes,
                    runner,
                    content,
                    filename,
                    correlation_id,
                )
            pipeline_path = self.store.staging_path(doc_id) / "pipeline.json"
            pipeline_path.write_text(
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            chunk_count = 0
            if self.settings.index_enabled:
                if self._index_fn is not None:
                    chunk_count = await self._index_fn(document)
                else:
                    chunk_count = await _default_index(
                        document, user_space=space
                    )

            manifest.status = "indexed"
            manifest.chunk_count = chunk_count
            manifest.indexed_at = utc_now_rfc3339()
            self.store.write_manifest(manifest)
            self.store.put_idempotency_record(
                key,
                doc_id=doc_id,
                ingest_id=ingest_id,
                manifest_path=rel_manifest,
            )
            return self.store.update_job(
                ingest_id,
                status=IngestJobStatus.SUCCEEDED,
                doc_id=doc_id,
                manifest_path=rel_manifest,
            )
        except Exception as exc:  # noqa: BLE001 — DLQ + job failure
            LOGGER.exception("Ingest failed for %s", ingest_id)
            manifest.status = "failed"
            manifest.error = str(exc)
            self.store.write_manifest(manifest)
            job = self.store.update_job(
                ingest_id,
                status=IngestJobStatus.FAILED,
                doc_id=doc_id,
                manifest_path=rel_manifest,
                error=str(exc),
            )
            self.store.write_dlq(
                ingest_id,
                job=job,
                manifest=manifest,
                reason=str(exc),
            )
            return job

    async def retry_from_dlq(self, ingest_id: str) -> IngestJob:
        """Re-queue a failed ingest from its DLQ record."""
        dlq = self.store.read_dlq(ingest_id)
        if dlq is None:
            raise KeyError(f"No DLQ record for ingest_id={ingest_id}")
        manifest_data = dlq.get("manifest")
        if not isinstance(manifest_data, dict):
            raise ValueError(f"DLQ {ingest_id} missing manifest")
        manifest = IngestManifest.model_validate(manifest_data)
        source_path = self.store.source_path(
            manifest.doc_id,
            manifest.source.filename or "upload.bin",
        )
        if not source_path.is_file():
            raise FileNotFoundError(
                f"Staged source missing for retry: {source_path}"
            )
        content = source_path.read_bytes()
        correlation_id = current_correlation_id() or manifest.correlation_id
        retry_id = new_action_id()
        now = utc_now_rfc3339()
        job = IngestJob(
            ingest_id=retry_id,
            correlation_id=correlation_id,
            status=IngestJobStatus.PENDING,
            doc_id=manifest.doc_id,
            batch_id=manifest.lineage.batch_id,
            created_at=now,
            updated_at=now,
        )
        self.store.write_job(job)
        return await self.process_source(
            ingest_id=retry_id,
            correlation_id=correlation_id,
            source_uri=manifest.source.uri,
            content=content,
            filename=manifest.source.filename,
            content_type=manifest.source.content_type,
            batch_id=manifest.lineage.batch_id,
        )
