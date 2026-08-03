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
import time
from collections.abc import Awaitable, Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from thot.action.correlation import current_correlation_id
from thot.action.models import new_action_id, utc_now_rfc3339
from thot.core.ThotLogger import LogUserContext
from thot.core.TkeirPaths import configs_dir
from thot.governor.client import GovernorClient
from thot.tasks.converters.InputFormat import (
    AUTO_DATATYPE,
    detect_input_format,
)
from thot.tasks.pipeline.PipelineConfiguration import PipelineConfiguration
from thot.tasks.pipeline.PipelineRunner import PipelineRunner
from thot.tools.ingest.config import IngestSettings, ingest_settings
from thot.tools.ingest.fetch import (
    FetchError,
    doc_id_from_content,
    fetch_bytes,
)
from thot.tools.ingest.index_passages import index_pipeline_document
from thot.tools.ingest.manifest import (
    build_manifest,
    embedder_fingerprint,
    idempotency_key,
    pipeline_config_sha256,
)
from thot.tools.ingest.models import (
    EmbedderInfo,
    IngestJob,
    IngestJobStatus,
    IngestManifest,
    LineageInfo,
    SourceInfo,
)
from thot.tools.ingest.store import IngestStore
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
    

    Example:
        >>> from thot.tools.ingest.worker import document_extras_from_metadata
        >>> document_extras_from_metadata({"corpus": "demo"})["corpus"]
        'demo'
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
    """Return the pipeline config path from settings or the default.

    Example:
        >>> from thot.tools.ingest.config import ingest_settings
        >>> _default_pipeline_config_path(ingest_settings()).name
        'pipeline.yaml'
    """
    if settings.pipeline_config_path.is_file():
        return settings.pipeline_config_path
    return Path(configs_dir()) / "pipeline.yaml"


def _load_runner(config_path: Path) -> PipelineRunner:
    """Load a :class:`PipelineRunner` from a YAML config file.

    Example:
        >>> from thot.tools.ingest.config import ingest_settings
        >>> runner = _load_runner(_default_pipeline_config_path(ingest_settings()))
        >>> runner is not None
        True
    """
    config = PipelineConfiguration()
    with config_path.open(encoding="utf-8") as handle:
        config.load(handle)
    return PipelineRunner(config)


@lru_cache(maxsize=4)
def _cached_runner(config_path: str) -> PipelineRunner:
    """Reuse one PipelineRunner (and spaCy models) per config path.

    Example:
        >>> from thot.tools.ingest.config import ingest_settings
        >>> path = str(_default_pipeline_config_path(ingest_settings()).resolve())
        >>> _cached_runner(path) is _cached_runner(path)
        True
    """
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
    

    Example:
        >>> from thot.tools.ingest.worker import ensure_source_doc_id
        >>> ensure_source_doc_id({"source": "s1"})["source_doc_id"]
        's1'
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
    datatype: str | None = None,
) -> dict[str, Any]:
    """Execute the NLP pipeline on raw document bytes.

    ``document_extras`` (e.g. per-request ``ontologies`` paths) are
    merged into the pipeline input and preserved across the converter step.

    ``datatype`` selects the converter input type. Default ``None`` uses
    auto-detection (same as ingest). Pass ``\"raw\"`` to force
    :class:`~thot.tasks.converters.RawTextConverter.RawTextConverter`.
    

    Example:
        >>> from thot.tools.ingest.worker import run_pipeline_on_bytes
        >>> callable(run_pipeline_on_bytes)
        True
    """
    from thot.tools.ingest.fetch import doc_id_from_content

    suffix = Path(filename).suffix or ".bin"
    call_context = LogUserContext(correlation_id)
    call_context["input-file"] = filename
    call_context["source-file-size-bytes"] = len(content)
    content_digest = doc_id_from_content(content)
    requested = (datatype or "").strip().lower() or None

    with tempfile.TemporaryDirectory(prefix="tkeir-ingest-") as temp_dir:
        input_path = Path(temp_dir) / f"source{suffix}"
        input_path.write_bytes(content)
        # Pre-converted pipeline JSON: skip converter unless datatype forced.
        if input_path.suffix == ".json" and requested is None:
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
        if requested == "raw":
            from thot.tasks.converters.InputFormat import is_binary_document

            if is_binary_document(content):
                raise ValueError(
                    "Binary documents cannot use datatype 'raw'; "
                    "pass datatype=auto (or pdf/docx/…)"
                )
            resolved_type = "raw"
        else:
            resolved_type = detect_input_format(
                str(input_path),
                content,
                requested or AUTO_DATATYPE,
            )
        encoded = base64.b64encode(content).decode()
        payload = {
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
    document: dict[str, Any],
    *,
    user_space: str | None = None,
    nlp_ms: float = 0.0,
    target: str = "both",
    dataset: str | None = None,
    ontology_payload: dict[str, Any] | None = None,
) -> int:
    """Index one analyzed document into Vespa (default worker index hook).

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(_default_index)
        True
    """
    async with VespaClient() as vespa:
        result = await index_pipeline_document(
            document,
            vespa=vespa,
            target=target,  # type: ignore[arg-type]
            user_space=user_space,
            ontology_payload=ontology_payload,
            dataset=dataset,
            nlp_ms=nlp_ms,
        )
        return result.passage_count


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
        """Bind worker to ``store`` and optional pipeline/index overrides.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> from thot.tools.ingest.worker import IngestWorker
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     worker = IngestWorker(IngestStore(Path(temp_dir)))
            ...     worker.store.root.name == Path(temp_dir).name
            True
        """
        self.store = store
        self.settings = settings or ingest_settings()
        self._pipeline_fn = pipeline_fn
        self._index_fn = index_fn
        # Serialize heavy NLP+index work — parallel spaCy runs OOM host ingest (SIGKILL 137).
        self._pipeline_sem = asyncio.Semaphore(self.settings.max_concurrency)

    def _embedder_info(self) -> EmbedderInfo:
        """Build embedder fingerprint metadata for ingest manifests.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     worker = IngestWorker(IngestStore(Path(temp_dir)))
            ...     worker._embedder_info().model
            'bge-m3'
        """
        provider = os.getenv("PROVIDER", "ollama")
        model = os.getenv("EMBEDDING_MODEL", "bge-m3")
        digest = embedder_fingerprint(provider=provider, model=model)
        return EmbedderInfo(model=model, provider=provider, sha256=digest)

    def _runner(self, config_path: Path) -> PipelineRunner:
        """Return a pipeline runner (cached unless a custom pipeline_fn is set).

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> from thot.tools.ingest.config import ingest_settings
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     worker = IngestWorker(IngestStore(Path(temp_dir)))
            ...     runner = worker._runner(_default_pipeline_config_path(ingest_settings()))
            ...     runner is not None
            True
        """
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
        """Call injected pipeline_fn; pass extras when the callable accepts them.

        Example:
            >>> import inspect
            >>> inspect.isfunction(IngestWorker._invoke_pipeline_fn)
            True
        """
        assert self._pipeline_fn is not None
        fn = self._pipeline_fn
        try:
            params = dict(inspect.signature(fn).parameters)
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

    def _bootstrap_job(
        self,
        *,
        ingest_id: str,
        correlation_id: str,
        batch_id: str | None,
        space: str,
        existing_job: IngestJob | None,
    ) -> IngestJob | None:
        """Assert governor scope and ensure job record. Return failed job or None.

        Example:
            >>> import inspect
            >>> inspect.isfunction(IngestWorker._bootstrap_job)
            True
        """
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
        return None

    def _fail_fetch(self, ingest_id: str, exc: FetchError) -> IngestJob:
        """Mark job failed and write DLQ after a source fetch error.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> from thot.tools.ingest.models import IngestJob, IngestJobStatus
            >>> from thot.action.models import utc_now_rfc3339
            >>> from thot.tools.ingest.fetch import FetchError
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     store = IngestStore(Path(temp_dir))
            ...     store.ensure_layout()
            ...     now = utc_now_rfc3339()
            ...     _ = store.write_job(IngestJob(
            ...         ingest_id="i1", correlation_id="c1",
            ...         status=IngestJobStatus.PENDING, created_at=now, updated_at=now,
            ...     ))
            ...     worker = IngestWorker(store)
            ...     job = worker._fail_fetch("i1", FetchError("bad url"))
            ...     job.status.value
            'failed'
        """
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

    def _idempotent_noop_job(
        self,
        *,
        ingest_id: str,
        doc_id: str,
        key: str,
    ) -> IngestJob | None:
        """Return NOOP job update when an indexed/noop idempotency hit exists.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.tools.ingest.store import IngestStore
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     worker = IngestWorker(IngestStore(Path(temp_dir)))
            ...     worker._idempotent_noop_job(ingest_id="i1", doc_id="d1", key="k1") is None
            True
        """
        existing = self.store.get_idempotency_record(key)
        if existing is None:
            return None
        manifest = self.store.read_manifest(doc_id)
        if manifest is None or manifest.status not in {"indexed", "noop"}:
            return None
        rel_manifest = str(
            self.store.manifest_path(doc_id).relative_to(self.store.root)
        )
        return self.store.update_job(
            ingest_id,
            status=IngestJobStatus.NOOP,
            doc_id=doc_id,
            manifest_path=rel_manifest,
            noop=True,
        )

    @staticmethod
    def _resolve_business_ontology_payload(
        *,
        dataset: str | None,
        request_payload: Any,
    ) -> dict[str, Any] | None:
        """Load ``datasets/<dataset>/business_ontology.yaml`` and merge request.

        Example:
            >>> IngestWorker._resolve_business_ontology_payload(
            ...     dataset="missing", request_payload=None,
            ... ) is None
            True
        """
        from thot.tools.search.business_ontology import (
            load_dataset_business_ontology_payload,
            merge_business_ontology_payloads,
        )

        file_payload = None
        if dataset:
            file_payload = load_dataset_business_ontology_payload(dataset)
        merged = merge_business_ontology_payloads(
            file_payload, request_payload
        )
        if not merged:
            return None
        concepts = merged.get("concepts") if isinstance(merged, dict) else None
        if not isinstance(concepts, list) or not concepts:
            return None
        return merged

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
        index_target: str = "both",
    ) -> IngestJob:
        """Fetch (when needed), stage, pipeline, and optionally index.

        Example:
            >>> import inspect
            >>> from thot.tools.ingest.worker import IngestWorker
            >>> inspect.iscoroutinefunction(IngestWorker.process_source)
            True
        """
        from thot.tools.search.user_space import resolve_vespa_user_space

        existing_job = self.store.read_job(ingest_id)
        space = resolve_vespa_user_space(
            None,
            fallback=user_space
            or (existing_job.user_space if existing_job else None),
        )
        extras = dict(document_extras or {})
        # index_target may be carried in extras from JSON-record ingest.
        target = (
            str(extras.pop("index_target", None) or index_target or "both")
            .strip()
            .lower()
        )
        if target not in {"global", "user", "both"}:
            target = "both"
        record_concepts = extras.pop("record_concept_ids", None)
        forced_source = extras.pop("source_doc_id", None) or extras.pop(
            "source", None
        )
        force_reindex = bool(extras.pop("force_reindex", False))
        bo_dataset_raw = extras.pop("business_ontology_dataset", None)
        bo_payload_raw = extras.pop("business_ontology", None)
        bo_dataset = (
            str(bo_dataset_raw).strip()
            if isinstance(bo_dataset_raw, str) and bo_dataset_raw.strip()
            else (
                str(extras.get("dataset")).strip()
                if extras.get("dataset")
                else None
            )
        )
        if bo_dataset and not extras.get("dataset"):
            extras["dataset"] = bo_dataset
        failed = self._bootstrap_job(
            ingest_id=ingest_id,
            correlation_id=correlation_id,
            batch_id=batch_id,
            space=space,
            existing_job=existing_job,
        )
        if failed is not None:
            return failed

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
                return self._fail_fetch(ingest_id, exc)
            filename = resolved_name
            content_type = content_type or fetched_type
        else:
            filename = filename or "upload.bin"

        doc_id = doc_id_from_content(content)
        key = idempotency_key(doc_id, pipeline_sha, embedder.sha256)
        if not force_reindex:
            noop_job = self._idempotent_noop_job(
                ingest_id=ingest_id, doc_id=doc_id, key=key
            )
            if noop_job is not None:
                return noop_job

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
                t_nlp = time.perf_counter()
                pipeline_extras = extras or None
                if self._pipeline_fn is not None:
                    runner = self._runner(config_path)
                    document = self._invoke_pipeline_fn(
                        runner,
                        content,
                        filename,
                        correlation_id,
                        pipeline_extras,
                    )
                else:
                    runner = self._runner(config_path)
                    document = await asyncio.to_thread(
                        run_pipeline_on_bytes,
                        runner,
                        content,
                        filename,
                        correlation_id,
                        document_extras=pipeline_extras,
                    )
                nlp_ms = (time.perf_counter() - t_nlp) * 1000
                if isinstance(forced_source, str) and forced_source.strip():
                    document["source_doc_id"] = forced_source.strip()
                    document["source"] = forced_source.strip()
                if isinstance(record_concepts, list) and record_concepts:
                    document["record_concept_ids"] = [
                        str(c).strip()
                        for c in record_concepts
                        if c and str(c).strip()
                    ]
                if bo_dataset and not document.get("dataset"):
                    document["dataset"] = bo_dataset

                ontology_payload = self._resolve_business_ontology_payload(
                    dataset=bo_dataset,
                    request_payload=bo_payload_raw,
                )
                if ontology_payload is not None:
                    from thot.tools.search.business_ontology import (
                        annotate_document_with_business_ontology,
                    )

                    document = annotate_document_with_business_ontology(
                        document, ontology_payload
                    )
                    document["business_ontology_applied"] = {
                        "dataset": bo_dataset,
                        "concept_count": (
                            len(ontology_payload.get("concepts") or [])
                            if isinstance(ontology_payload, dict)
                            else None
                        ),
                    }

                source_ref = str(
                    document.get("source_doc_id")
                    or document.get("source")
                    or ""
                ).strip()
                if source_ref:
                    self.store.write_analyzed_document(
                        doc_id,
                        document,
                        source_ref=source_ref,
                    )
                pipeline_path = (
                    self.store.staging_path(doc_id) / "pipeline.json"
                )
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
                            document,
                            user_space=space,
                            nlp_ms=nlp_ms,
                            target=target,
                            dataset=bo_dataset
                            or (
                                str(document.get("dataset")).strip()
                                if document.get("dataset")
                                else None
                            ),
                            ontology_payload=ontology_payload,
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
                from thot.tools.ingest.shutdown import request_ingest_shutdown

                request_ingest_shutdown(
                    f"stop-on-failed: ingest_id={ingest_id} error={exc}"
                )
            return job

    async def retry_from_dlq(self, ingest_id: str) -> IngestJob:
        """Re-queue a failed ingest from its DLQ record.

        Example:
            >>> import inspect
            >>> from thot.tools.ingest.worker import IngestWorker
            >>> inspect.iscoroutinefunction(IngestWorker.retry_from_dlq)
            True
        """
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
