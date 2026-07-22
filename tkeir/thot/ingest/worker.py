"""Title: Worker

Run pipeline + optional Vespa indexing for ingest jobs.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import logging
import os
import tempfile
from collections.abc import Awaitable, Callable
from functools import lru_cache
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

PipelineFn = Callable[..., dict[str, Any]]
IndexFn = Callable[[dict[str, Any]], Awaitable[int]]


def document_extras_from_metadata(
    metadata: dict[str, Any] | None,
    *,
    ontologies: list[str] | None = None,
) -> dict[str, Any] | None:
    """Build pipeline document extras from ingest multipart/JSON fields.

    ``ontologies`` must already be **server-local staged paths** produced from
    client-uploaded bytes (never client filesystem paths). Legacy path keys in
    metadata are ignored for derive-from.
    """
    from thot.tasks.document_ontology.OntologyLexicon import (
        normalize_ontology_path_list,
        stamp_document_ontologies,
    )

    extras: dict[str, Any] = {}
    if metadata:
        extras["metadata"] = dict(metadata)
        for key in (
            "corpus",
            "topic_id",
            "doc_type",
            "title",
            "user_space",
            "language",
        ):
            if key in metadata and metadata[key] is not None:
                extras[key] = metadata[key]

    collected = normalize_ontology_path_list(ontologies)
    if collected:
        stamp_document_ontologies(extras, collected)

    return extras or None


def _default_pipeline_config_path(settings: IngestSettings) -> Path:
    if settings.pipeline_config_path.is_file():
        return settings.pipeline_config_path
    return Path(configs_dir()) / "pipeline.yaml"


def _load_runner(config_path: Path) -> PipelineRunner:
    config = PipelineConfiguration()
    with config_path.open(encoding="utf-8") as handle:
        config.load(handle)
    return PipelineRunner(config)


@lru_cache(maxsize=4)
def _cached_runner(config_path: str) -> PipelineRunner:
    """Reuse one PipelineRunner (and spaCy models) per config path."""
    return _load_runner(Path(config_path))


def ensure_source_doc_id(
    document: dict[str, Any],
    *,
    filename: str | None = None,
    content_digest: str | None = None,
) -> dict[str, Any]:
    """Guarantee ``source_doc_id`` for Vespa indexing.

    Pre-converted corpus JSON (title/content only) skips the converter, which
    normally stamps ``source_doc_id``. Fall back to ``source``, then a stable
    ingest URI from the content digest / filename.
    """
    existing = document.get("source_doc_id")
    if isinstance(existing, str) and existing.strip():
        return document
    source = document.get("source")
    if isinstance(source, str) and source.strip():
        document["source_doc_id"] = source.strip()
        return document
    name = filename or "upload.bin"
    if content_digest:
        document["source_doc_id"] = f"ingest://{content_digest}/{name}"
    else:
        document["source_doc_id"] = f"ingest://{name}"
    if not document.get("source"):
        document["source"] = document["source_doc_id"]
    return document


def run_pipeline_on_bytes(
    runner: PipelineRunner,
    content: bytes,
    filename: str,
    correlation_id: str,
    *,
    document_extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the NLP pipeline on raw document bytes.

    ``document_extras`` (e.g. per-request ``ontologies`` paths) are
    merged into the pipeline input and preserved across the converter step.
    """
    from thot.ingest.fetch import doc_id_from_content

    suffix = Path(filename).suffix or ".bin"
    call_context = LogUserContext(correlation_id)
    call_context["input-file"] = filename
    call_context["source-file-size-bytes"] = len(content)
    content_digest = doc_id_from_content(content)

    with tempfile.TemporaryDirectory(prefix="tkeir-ingest-") as temp_dir:
        input_path = Path(temp_dir) / f"source{suffix}"
        input_path.write_bytes(content)
        if input_path.suffix == ".json":
            with input_path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict) and (
                "content" in payload or "content_tokens" in payload
            ):
                if document_extras:
                    payload = {**payload, **document_extras}
                # Corpus JSON often has title/content only — stamp id before
                # run_converted (converter is skipped).
                ensure_source_doc_id(
                    payload,
                    filename=filename,
                    content_digest=content_digest,
                )
                # content may be a plain string in demo corpora.
                if isinstance(payload.get("content"), str):
                    payload["content"] = [payload["content"]]
                result = runner.run_converted(
                    payload,
                    call_context=call_context,
                )
                return ensure_source_doc_id(
                    result,
                    filename=filename,
                    content_digest=content_digest,
                )
        resolved_type = detect_input_format(
            str(input_path),
            content,
            AUTO_DATATYPE,
        )
        encoded = base64.b64encode(content).decode()
        payload: dict[str, Any] = {
            "datatype": resolved_type,
            "data": encoded,
            "source": f"ingest://{content_digest}/{filename}",
            "source_doc_id": f"ingest://{content_digest}/{filename}",
        }
        if document_extras:
            payload.update(document_extras)
            # Keep a stable id even if extras omit it.
            ensure_source_doc_id(
                payload,
                filename=filename,
                content_digest=content_digest,
            )
        result = runner.run(payload, call_context=call_context)
        return ensure_source_doc_id(
            result,
            filename=filename,
            content_digest=content_digest,
        )


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
        # Serialize heavy NLP+index work — parallel spaCy runs OOM host ingest (SIGKILL 137).
        self._pipeline_sem = asyncio.Semaphore(self.settings.max_concurrency)

    def _embedder_info(self) -> EmbedderInfo:
        provider = os.getenv("PROVIDER", "ollama")
        model = os.getenv("EMBEDDING_MODEL", "bge-m3")
        digest = embedder_fingerprint(provider=provider, model=model)
        return EmbedderInfo(model=model, provider=provider, sha256=digest)

    def _runner(self, config_path: Path) -> PipelineRunner:
        if self._pipeline_fn is not None:
            return _load_runner(config_path)
        return _cached_runner(str(config_path.resolve()))

    def _invoke_pipeline_fn(
        self,
        runner: PipelineRunner,
        content: bytes,
        filename: str,
        correlation_id: str,
        document_extras: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Call injected pipeline_fn; pass extras when the callable accepts them."""
        assert self._pipeline_fn is not None
        fn = self._pipeline_fn
        try:
            params = inspect.signature(fn).parameters
        except (TypeError, ValueError):
            params = {}
        accepts_extras = "document_extras" in params or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
        if accepts_extras:
            return fn(
                runner,
                content,
                filename,
                correlation_id,
                document_extras=document_extras,
            )
        return fn(runner, content, filename, correlation_id)

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
        document_extras: dict[str, Any] | None = None,
    ) -> IngestJob:
        """Fetch (when needed), stage, pipeline, and optionally index."""
        from thot.tools.search.user_space import resolve_vespa_user_space

        existing_job = self.store.read_job(ingest_id)
        space = resolve_vespa_user_space(
            None,
            fallback=user_space
            or (existing_job.user_space if existing_job else None),
        )
        extras = document_extras
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
            async with self._pipeline_sem:
                if self._pipeline_fn is not None:
                    runner = self._runner(config_path)
                    document = self._invoke_pipeline_fn(
                        runner,
                        content,
                        filename,
                        correlation_id,
                        extras,
                    )
                else:
                    runner = self._runner(config_path)
                    document = await asyncio.to_thread(
                        run_pipeline_on_bytes,
                        runner,
                        content,
                        filename,
                        correlation_id,
                        document_extras=extras,
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
            if self.settings.stop_on_failed:
                from thot.ingest.shutdown import request_ingest_shutdown

                request_ingest_shutdown(
                    f"stop-on-failed: ingest_id={ingest_id} error={exc}"
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
