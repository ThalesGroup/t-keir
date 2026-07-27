#!/usr/bin/env python3
"""Title: Ingest dataset

Ingest T-KEIR demo dataset documents through the ingest API or Make fallback.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOG = logging.getLogger("tkeir.datasets.ingest")
REPO_ROOT = Path(__file__).resolve().parents[2]

_ONTOLOGY_SUFFIXES = {".ttl", ".owl", ".rdf", ".xml"}


def resolve_ontology_args(args: argparse.Namespace) -> list[Path]:
    """Resolve ``--ontologies`` / ``--ontology-dir`` to local files the client uploads.

    These paths are read on the **client** only; file bytes are sent in the
    ingest request. The server never opens these paths.
    """
    paths: list[Path] = []
    raw = getattr(args, "ontologies", None)
    if raw:
        for part in str(raw).split(","):
            part = part.strip()
            if part:
                paths.append(Path(part).expanduser())
    ontology_dir = getattr(args, "ontology_dir", None)
    if ontology_dir:
        root = Path(ontology_dir).expanduser().resolve()
        if not root.is_dir():
            raise SystemExit(f"--ontology-dir not a directory: {root}")
        for path in sorted(root.iterdir()):
            if path.is_file() and path.suffix.lower() in _ONTOLOGY_SUFFIXES:
                paths.append(path)
    ordered: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = path.resolve()
        if not resolved.is_file():
            raise SystemExit(f"ontology file not found: {path}")
        key = str(resolved)
        if key not in seen:
            seen.add(key)
            ordered.append(resolved)
    return ordered


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def csv_values(value: str | None) -> set[str] | None:
    if not value:
        return None
    values = {item.strip() for item in value.split(",") if item.strip()}
    return values or None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets-dir", type=Path, default=REPO_ROOT / "datasets",
                        help="Root containing osint/ and/or enterprise/")
    parser.add_argument("--api-url", default="http://localhost:8091")
    parser.add_argument("--dataset", choices=("osint", "enterprise", "all"), default="all")
    parser.add_argument(
        "--ontologies",
        help="Comma-separated local OWL/TTL/RDF files; client uploads their "
        "bytes as multipart ontology_file (server never reads these paths)",
    )
    parser.add_argument(
        "--ontology-dir",
        type=Path,
        help="Local directory of OWL/TTL/RDF files; client uploads each file's "
        "bytes with the document (server has no access to this directory)",
    )
    parser.add_argument("--topics", help="Comma-separated topic IDs")
    parser.add_argument("--formats", help="Comma-separated document formats")
    parser.add_argument("--user-space", help="Override the user space for every document")
    parser.add_argument("--token")
    parser.add_argument("--token-url")
    parser.add_argument("--client-id", default="tkeir-cli")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, default=1,
                        help="Parallel upload workers (default 1; keep low — ingest serializes NLP)")
    parser.add_argument("--batch-size", type=int, default=10,
                        help="Reserved for future batch uploads (currently per-document)")
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="HTTP timeout seconds for upload requests (default 120)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Retries on timeout / connection errors (default 3)",
    )
    parser.add_argument(
        "--wait",
        dest="wait",
        action="store_true",
        default=True,
        help="Wait for each ingest job to finish before counting it (default: on)",
    )
    parser.add_argument(
        "--no-wait",
        dest="wait",
        action="store_false",
        help="Only wait for HTTP 202 accept (progress is submit-rate, not index-rate)",
    )
    parser.add_argument(
        "--status-poll",
        dest="wait",
        action="store_true",
        help="Alias for --wait (poll /ingest/status until done)",
    )
    parser.add_argument(
        "--poll-timeout",
        type=int,
        default=3600,
        help="Max seconds to wait per document when --wait is set (default 3600)",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=1,
        help="Log progress every N completed docs (default 1; use 10 for quieter runs)",
    )
    parser.add_argument("--fallback-index", action="store_true",
                        help="If ingest API is down, run local tkeir-pipeline + index "
                             "(slow for large corpora; requires --force-fallback when "
                             "document count exceeds --fallback-max-docs)")
    parser.add_argument(
        "--force-fallback",
        action="store_true",
        help="Allow the local pipeline/index fallback for large corpora",
    )
    parser.add_argument(
        "--fallback-max-docs",
        type=int,
        default=50,
        help="Max docs allowed for unforced pipeline fallback (default: 50)",
    )
    parser.add_argument(
        "--stop-on-failed",
        action="store_true",
        help="On first document failure: cancel remaining uploads, stop the "
        "ingest server (/ingest/stop), and exit non-zero (fast debug)",
    )
    parser.add_argument("--output-report", type=Path)
    parser.add_argument("--print-web-guide", action="store_true")
    parser.add_argument("--print-token", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args(argv)
    if args.workers < 1 or args.batch_size < 1:
        parser.error("--workers and --batch-size must be positive")
    if args.fallback_max_docs < 1:
        parser.error("--fallback-max-docs must be positive")
    if args.timeout < 1 or args.retries < 0:
        parser.error("--timeout must be >= 1 and --retries must be >= 0")
    if args.poll_timeout < 1 or args.progress_every < 1:
        parser.error("--poll-timeout and --progress-every must be >= 1")
    return args


def request_bytes(method: str, url: str, *, data: bytes | None = None,
                  headers: dict[str, str] | None = None, timeout: int = 10) -> tuple[int, bytes]:
    """Use httpx/requests when installed, then stdlib urllib."""
    headers = headers or {}
    try:
        import httpx  # type: ignore[import-not-found]
        response = httpx.request(method, url, content=data, headers=headers, timeout=timeout)
        return response.status_code, response.content
    except ImportError:
        pass
    try:
        import requests  # type: ignore[import-not-found]
        response = requests.request(method, url, data=data, headers=headers, timeout=timeout)
        return response.status_code, response.content
    except ImportError:
        pass
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def fetch_token(args: argparse.Namespace) -> str | None:
    if args.token:
        return args.token
    if args.token_url:
        if not args.username or args.password is None:
            raise ValueError("--token-url requires --username and --password")
        payload = urlencode({
            "grant_type": "password", "client_id": args.client_id,
            "username": args.username, "password": args.password,
        }).encode()
        status, body = request_bytes(
            "POST", args.token_url, data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not 200 <= status < 300:
            raise RuntimeError(f"token request failed with HTTP {status}: {body.decode(errors='replace')}")
        token = json.loads(body).get("access_token")
        if not token:
            raise RuntimeError("token response has no access_token")
        return str(token)
    return os.environ.get("INGEST_DEV_TOKEN")


def load_documents(args: argparse.Namespace) -> list[dict[str, Any]]:
    topics, formats = csv_values(args.topics), csv_values(args.formats)
    wanted = ("osint", "enterprise") if args.dataset == "all" else (args.dataset,)
    dirs = {"osint": "osint", "enterprise": "enterprise"}
    # Process-time only — client reads these files and uploads bytes per request.
    ontology_files = resolve_ontology_args(args)
    if ontology_files:
        LOG.info(
            "Will upload %s ontology file(s) with each document (content, not paths)",
            len(ontology_files),
        )
    documents: list[dict[str, Any]] = []
    for corpus in wanted:
        manifest = args.datasets_dir / dirs[corpus] / "manifest.json"
        if not manifest.is_file():
            LOG.warning("Skipping missing manifest: %s", manifest)
            continue
        content = json.loads(manifest.read_text(encoding="utf-8"))
        for raw in content.get("documents", []):
            if topics and raw.get("topic_id") not in topics:
                continue
            if formats and raw.get("format") not in formats:
                continue
            doc = dict(raw)
            doc["corpus"] = corpus
            doc["file_path"] = manifest.parent / str(doc["path"])
            doc["resolved_user_space"] = args.user_space or doc.get("user_space") or os.environ.get(
                "VESPA_USER_SPACE", "dev@tkeir"
            )
            if ontology_files:
                # Local Path objects — multipart() reads bytes for upload.
                doc["ontology_files"] = list(ontology_files)
            documents.append(doc)
    return documents


def multipart(document: dict[str, Any]) -> tuple[bytes, str]:
    boundary = f"----tkeir-{uuid.uuid4().hex}"
    metadata: dict[str, Any] = {
        "topic_id": document.get("topic_id"),
        "corpus": document.get("corpus"),
        "doc_type": document.get("doc_type"),
        "language": document.get("lang", "en"),
        "title": document.get("title"),
        "user_space": document["resolved_user_space"],
    }
    path = document["file_path"]
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\n"
        "Content-Type: application/json\r\n\r\n".encode()
        + json.dumps(metadata).encode()
        + b"\r\n",
    ]
    # Upload ontology *content* (server stages under INGEST_ROOT; no client paths).
    for onto in document.get("ontology_files") or []:
        onto_path = Path(onto)
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="ontology_file"; '
                f'filename="{onto_path.name}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
            + onto_path.read_bytes()
            + b"\r\n"
        )
    parts.extend(
        [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f'filename="{path.name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n".encode()
            + path.read_bytes()
            + b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(parts), boundary


def format_duration(seconds: float) -> str:
    """Human-readable duration for progress / ETA lines."""
    if seconds < 0 or seconds != seconds:  # NaN
        return "?"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


class ProgressTracker:
    """Thread-safe ingest progress with rolling ETA."""

    def __init__(self, total: int, *, every: int = 1, quiet: bool = False) -> None:
        self.total = max(0, total)
        self.every = max(1, every)
        self.quiet = quiet
        self.done = 0
        self.ok = 0
        self.failed = 0
        self.started = time.monotonic()
        self._lock = threading.Lock()
        self._last_log_at = 0.0

    def tick(self, *, ok: bool, doc_id: str | None = None) -> None:
        with self._lock:
            self.done += 1
            if ok:
                self.ok += 1
            else:
                self.failed += 1
            should_log = (
                not self.quiet
                and (
                    self.done == 1
                    or self.done == self.total
                    or self.done % self.every == 0
                    or (time.monotonic() - self._last_log_at) >= 15.0
                )
            )
            if should_log:
                self._last_log_at = time.monotonic()
                LOG.info("%s", self.line(doc_id=doc_id))

    def line(self, *, doc_id: str | None = None) -> str:
        elapsed = max(0.001, time.monotonic() - self.started)
        rate = self.done / elapsed
        remaining = max(0, self.total - self.done)
        eta = remaining / rate if rate > 0 and self.done > 0 else None
        pct = (100.0 * self.done / self.total) if self.total else 100.0
        parts = [
            f"progress {self.done}/{self.total} ({pct:5.1f}%)",
            f"ok={self.ok} failed={self.failed}",
            f"elapsed {format_duration(elapsed)}",
            f"{rate:.2f} docs/s",
        ]
        if eta is None:
            parts.append("ETA …")
        else:
            parts.append(f"ETA {format_duration(eta)}")
        if doc_id:
            parts.append(f"last={doc_id}")
        return " | ".join(parts)


def poll_status(
    api_url: str,
    job_id: str,
    headers: dict[str, str],
    *,
    timeout_s: int = 3600,
    interval_s: float = 2.0,
) -> str:
    """Poll until the ingest job reaches a terminal state; return status string."""
    deadline = time.monotonic() + timeout_s
    last_status = "pending"
    while time.monotonic() < deadline:
        status, body = request_bytes(
            "GET",
            f"{api_url}/ingest/status/{job_id}",
            headers=headers,
            timeout=min(30, timeout_s),
        )
        if not 200 <= status < 300:
            raise RuntimeError(f"Status poll HTTP {status}: {body.decode(errors='replace')}")
        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Status poll returned non-JSON for {job_id}") from exc
        last_status = str(result.get("status", "")).lower()
        if last_status in {"succeeded", "complete", "completed", "noop"}:
            return last_status
        if last_status in {"failed", "error"}:
            detail = result.get("error") or last_status
            raise RuntimeError(f"Ingest job {job_id} failed: {detail}")
        time.sleep(interval_s)
    raise TimeoutError(
        f"Ingest job {job_id} still {last_status!r} after {timeout_s}s"
    )


def upload(document: dict[str, Any], args: argparse.Namespace, token: str | None) -> str:
    """Upload one document; optionally wait for indexing. Returns terminal status."""
    data, boundary = multipart(document)
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "X-User-Space": document["resolved_user_space"],
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    # Status GETs need auth headers but not multipart content-type.
    status_headers = {k: v for k, v in headers.items() if k != "Content-Type"}
    if token:
        status_headers["Authorization"] = f"Bearer {token}"
    url = f"{args.api_url.rstrip('/')}/ingest/document"
    last_error: Exception | None = None
    for attempt in range(args.retries + 1):
        try:
            status, body = request_bytes(
                "POST", url, data=data, headers=headers, timeout=args.timeout
            )
            if not 200 <= status < 300:
                raise RuntimeError(f"HTTP {status}: {body.decode(errors='replace')}")
            terminal = "accepted"
            if args.wait:
                try:
                    response = json.loads(body)
                except json.JSONDecodeError as exc:
                    raise RuntimeError("Ingest accept response was not JSON") from exc
                job_id = (
                    response.get("ingest_id")
                    or response.get("job_id")
                    or response.get("jobId")
                    or response.get("id")
                )
                if not job_id:
                    raise RuntimeError(f"No ingest_id in accept response: {response}")
                terminal = poll_status(
                    args.api_url.rstrip("/"),
                    str(job_id),
                    status_headers,
                    timeout_s=args.poll_timeout,
                )
            return terminal
        except Exception as exc:  # noqa: BLE001 — retry transient network failures
            last_error = exc
            msg = str(exc).lower()
            transient = any(
                token in msg
                for token in (
                    "timed out",
                    "timeout",
                    "connection refused",
                    "connection reset",
                    "server disconnected",
                    "temporarily unavailable",
                )
            )
            # Do not retry definitive job failures from the ingest worker.
            if "ingest job" in msg and "failed" in msg:
                raise
            if not transient or attempt >= args.retries:
                raise
            delay = min(30.0, 1.5 ** attempt)
            LOG.warning(
                "Retry %s/%s for %s after %s (sleep %.1fs)",
                attempt + 1,
                args.retries,
                document.get("id"),
                exc,
                delay,
            )
            time.sleep(delay)
    assert last_error is not None
    raise last_error


def health_ok(api_url: str) -> bool:
    try:
        status, _ = request_bytes("GET", f"{api_url.rstrip('/')}/health", timeout=5)
        return 200 <= status < 300
    except Exception as exc:
        LOG.warning("Health check failed: %s", exc)
        return False


def make_fallback(
    documents: list[dict[str, Any]],
    report: dict[str, Any],
    dry_run: bool,
    *,
    force: bool = False,
    max_docs: int = 50,
    stop_on_failed: bool = False,
) -> None:
    """Fall back to local pipeline + Vespa index when the ingest API is down.

    Running the full NLP pipeline on thousands of dataset files can take hours and
    previously looked “hung” because stdout was captured. Prefer a host ingest
    process in P0 (no tkeir containers)::

        make bootstrap
        make ingest          # terminal 1 — uv / host :8091
        make datasets-ingest   # terminal 2

    For P1 Compose (after ``make images``)::

        make compose-up PROFILES=core,ingest
        make datasets-ingest
    """
    report["fallback_mode"] = "local_pipeline_index"
    total = len(documents)
    if total > max_docs and not force:
        msg = (
            f"Ingest API unavailable and local fallback refused for {total} docs "
            f"(limit={max_docs} without --force-fallback).\n"
            "  P0 (host tools, no tkeir containers):\n"
            "    make bootstrap && make ingest\n"
            "    make datasets-ingest\n"
            "  P1 (Compose images under IMAGE_REGISTRY=local):\n"
            "    make images && make compose-up PROFILES=core,ingest\n"
            "    make datasets-ingest\n"
            "  Or force the slow host pipeline (hours for large corpora):\n"
            "    make datasets-ingest INGEST_FLAGS='--force-fallback'\n"
            "  Or ingest a small slice first:\n"
            "    make datasets-ingest INGEST_FLAGS='--topics situational_awareness --formats txt'"
        )
        LOG.error("%s", msg)
        report["failed"] += total
        report["errors"].append(
            {
                "doc_id": "*",
                "path": f"count={total}",
                "error": msg,
            }
        )
        return

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        groups[document["resolved_user_space"]].append(document)
    if dry_run:
        return

    LOG.warning(
        "Local pipeline/index fallback for %s document(s) across %s user-space(s). "
        "This runs full NLP conversion — expect a long runtime; progress streams below.",
        total,
        len(groups),
    )
    tkeir_dir = REPO_ROOT / "tkeir"
    uv = os.environ.get("UV", "uv")
    python = os.environ.get("PYTHON", "3.11")
    pipeline_default = tkeir_dir / "configs" / "pipeline.yaml"
    # Collect process-time ontologies from documents (local files on this host).
    runtime_ontologies: list[str] = []
    for document in documents:
        for path in document.get("ontology_files") or document.get("ontologies") or []:
            text = str(path)
            if text not in runtime_ontologies:
                runtime_ontologies.append(text)

    for space, group in groups.items():
        pipeline_cfg = pipeline_default
        temp_cfg_dir: tempfile.TemporaryDirectory[str] | None = None
        if runtime_ontologies:
            # Generate a temporary pipeline that enables derive-from with the
            # caller-supplied paths (no corpus-specific config files).
            temp_cfg_dir = tempfile.TemporaryDirectory(prefix="tkeir-onto-cfg-")
            cfg_root = Path(temp_cfg_dir.name)
            onto_cfg = cfg_root / "document-ontology.yaml"
            pipe_cfg = cfg_root / "pipeline.yaml"
            onto_cfg.write_text(
                "logger:\n  logging-level: info\n"
                "document-ontology:\n  builders:\n  - language: en\n"
                "    include-title-triples: true\n"
                "    include-content-triples: true\n"
                "    min-keyword-length: 3\n"
                "    max-repair-attempts: 2\n"
                "    alignment:\n      enabled: true\n"
                "      similarity-threshold: 0.85\n"
                "      min-cluster-size: 2\n"
                "    save-alignment: false\n"
                "    derive-from:\n      enabled: true\n"
                "      paths:\n"
                + "".join(f"        - {p}\n" for p in runtime_ontologies)
                + "      similarity-threshold: 0.8\n"
                "      match-classes: true\n"
                "      match-individuals: true\n"
                "      add-subclass-links: true\n"
                "      add-type-links: true\n"
                "      add-same-as-links: true\n"
                "      include-matched-axioms: false\n"
                "      save-report: false\n"
                "    save-derivation: false\n",
                encoding="utf-8",
            )
            # Point ontology task at the temp config; other tasks stay in configs/.
            pipe_cfg.write_text(
                "logger:\n  logging-level: info\n"
                "pipeline:\n  default-language: en\n  configs:\n"
                "    converter: converter.yaml\n"
                "    tokenizer: tokenizer.yaml\n"
                "    morphosyntax: mstagger.yaml\n"
                "    ner: nertagger.yaml\n"
                "    syntax: syntactic-tagger.yaml\n"
                "    keywords: keywords.yaml\n"
                "    chunking: golden-chunking.yaml\n"
                f"    ontology: {onto_cfg.resolve()}\n"
                "    chunk-questions: chunk-questions.yaml\n",
                encoding="utf-8",
            )
            pipeline_cfg = pipe_cfg
        LOG.info(
            "Fallback user_space=%s docs=%s pipeline=%s ontologies=%s — starting…",
            space,
            len(group),
            pipeline_cfg.name,
            len(runtime_ontologies),
        )
        try:
            with tempfile.TemporaryDirectory(prefix="tkeir-ingest-") as temp:
                stage, output = Path(temp) / "stage", Path(temp) / "output"
                stage.mkdir()
                output.mkdir()
                for index, document in enumerate(group):
                    shutil.copy2(
                        document["file_path"],
                        stage / f"{index:05d}_{document['file_path'].name}",
                    )
                env = os.environ.copy()
                env["VESPA_USER_SPACE"] = space
                pipeline = subprocess.run(
                    [
                        uv,
                        "run",
                        "--no-sync",
                        "--python",
                        python,
                        "tkeir-pipeline",
                        "-c",
                        str(pipeline_cfg),
                        "-i",
                        str(stage),
                        "-o",
                        str(output),
                        "-t",
                        "auto",
                    ],
                    cwd=tkeir_dir,
                    env=env,
                )
                index_result = None
                if pipeline.returncode == 0:
                    LOG.info(
                        "Fallback user_space=%s — indexing %s pipeline outputs…",
                        space,
                        len(list(output.rglob("*.json"))),
                    )
                    index_result = subprocess.run(
                        [
                            uv,
                            "run",
                            "--python",
                            python,
                            "python",
                            "-m",
                            "thot.tools.ingest.index_documents",
                            "-i",
                            str(output),
                        ],
                        cwd=tkeir_dir,
                        env=env,
                    )
                if (
                    pipeline.returncode == 0
                    and index_result
                    and index_result.returncode == 0
                ):
                    report["sent"] += len(group)
                    LOG.info(
                        "Fallback user_space=%s OK (%s docs)", space, len(group)
                    )
                else:
                    message = (
                        f"pipeline={pipeline.returncode} "
                        f"index={getattr(index_result, 'returncode', None)}"
                    )
                    report["failed"] += len(group)
                    report["errors"].append(
                        {
                            "doc_id": ",".join(
                                str(d.get("id")) for d in group[:5]
                            ),
                            "path": f"user_space={space} count={len(group)}",
                            "error": message,
                        }
                    )
                    LOG.error(
                        "Fallback user_space=%s failed: %s", space, message
                    )
                    if stop_on_failed:
                        LOG.error(
                            "stop-on-failed: aborting remaining fallback groups"
                        )
                        return
        finally:
            if temp_cfg_dir is not None:
                temp_cfg_dir.cleanup()


def print_web_guide(documents: list[dict[str, Any]], corpus_dir: Path, api_url: str) -> None:
    examples: dict[tuple[str, str], dict[str, Any]] = {}
    for doc in documents:
        examples.setdefault((str(doc.get("topic_id")), str(doc.get("format"))), doc)
    osint_example = next((doc for doc in documents if doc["corpus"] == "osint"), None)
    enterprise_example = next((doc for doc in documents if doc["corpus"] == "enterprise"), None)
    print("=" * 71)
    print("T-KEIR CORPUS WEB INGESTION GUIDE")
    print(f"Generated: {now()}")
    print("=" * 71)
    print("\nMODE A — HMI Drag-and-Drop")
    print("──────────────────────────")
    print("OSINT dataset → demo-user")
    print("  1. Open http://localhost:3000")
    print("  2. Sign in as: demo-user / demo-user")
    print("  3. Navigate to Upload / Ingest")
    print("  4. Drag files by topic from osint/ (see examples below)")
    print("  5. Verify: query \"SITREP Objective ALPHA\"")
    print("\nEnterprise dataset → demo-admin (AcmeSystems)")
    print("  1. Sign OUT, sign in as: demo-admin / demo-admin")
    print("  2. Upload from enterprise/ by topic")
    print("  3. Verify: query \"AcmeSystems Project ATLAS\"")
    print("\nISOLATION CHECK:")
    print("  As demo-user  → query \"AcmeSystems Project ATLAS\" → 0 results")
    print("  As demo-admin → query \"SITREP Objective ALPHA\"    → 0 results")
    print("\nExamples (paths relative to --datasets-dir):")
    for (_, _), doc in sorted(examples.items()):
        rel = doc["file_path"].relative_to(corpus_dir)
        print(f"  [{doc['topic_id']}] {rel}  ({doc['resolved_user_space']})")
    print("\n" + "=" * 71)
    print("MODE B — Direct API (curl)")
    print("──────────────────────────")
    print("TOKEN_USER=$(curl -s -X POST \\")
    print("  http://localhost:8082/realms/tkeir/protocol/openid-connect/token \\")
    print("  -d 'grant_type=password&client_id=tkeir-cli&username=demo-user&password=demo-user' \\")
    print("  | python3 -c \"import sys,json; print(json.load(sys.stdin)['access_token'])\")")
    print()
    if osint_example:
        metadata = {
            "topic_id": osint_example.get("topic_id"),
            "corpus": "osint",
            "doc_type": osint_example.get("doc_type"),
            "language": osint_example.get("lang", "en"),
            "title": osint_example.get("title"),
            "user_space": "demo-user",
        }
        ontologies = osint_example.get("ontology_files")
        if ontologies:
            metadata["note"] = "ontology_file parts upload content (not paths)"
        rel = osint_example["file_path"].relative_to(corpus_dir)
        print(f"curl -X POST {api_url.rstrip('/')}/ingest/document \\")
        print('  -H "Authorization: Bearer $TOKEN_USER" \\')
        print(f"  -F 'file=@{rel}' \\")
        for onto in ontologies or []:
            print(f"  -F 'ontology_file=@{onto}' \\")
        print(f"  -F 'metadata={json.dumps(metadata)}'")
        print("  # ontology_file = file bytes; server stages under INGEST_ROOT")
    if enterprise_example:
        metadata = {
            "topic_id": enterprise_example.get("topic_id"),
            "corpus": "enterprise",
            "doc_type": enterprise_example.get("doc_type"),
            "language": enterprise_example.get("lang", "en"),
            "title": enterprise_example.get("title"),
            "user_space": "demo-admin",
        }
        rel = enterprise_example["file_path"].relative_to(corpus_dir)
        print("\n# Then as demo-admin with an AcmeSystems file:")
        print(f"curl -X POST {api_url.rstrip('/')}/ingest/document \\")
        print('  -H "Authorization: Bearer $TOKEN_ADMIN" \\')
        print(f"  -F 'file=@{rel}' \\")
        print(f"  -F 'metadata={json.dumps(metadata)}'")
    print("=" * 71)


def stop_ingest_server(
    api_url: str,
    token: str | None,
    *,
    reason: str,
) -> None:
    """Ask the ingest API to shut down (best-effort)."""
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{api_url.rstrip('/')}/ingest/stop"
    try:
        status, body = request_bytes(
            "POST",
            url,
            data=json.dumps({"reason": reason}).encode(),
            headers=headers,
            timeout=5,
        )
        if 200 <= status < 300:
            LOG.error("Requested ingest server stop: %s", reason)
            return
        LOG.warning(
            "ingest /stop returned HTTP %s: %s",
            status,
            body.decode(errors="replace"),
        )
    except Exception as exc:  # noqa: BLE001
        LOG.warning("Could not reach ingest /stop (%s)", exc)


def abort_remaining_uploads(
    futures: dict[Any, dict[str, Any]],
    report: dict[str, Any],
    *,
    error: str,
) -> None:
    """Cancel pending futures and mark remaining docs as failed in the report."""
    for pending in futures:
        pending.cancel()
    remaining = [doc for fut, doc in futures.items() if not fut.done()]
    for doc in remaining:
        report["failed"] += 1
        report["errors"].append(
            {
                "doc_id": doc.get("id"),
                "path": str(doc.get("path")),
                "error": error,
            }
        )


def make_report(args: argparse.Namespace, documents: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "started_at": now(), "ended_at": None, "api_url": args.api_url,
        "fallback_mode": None, "total": len(documents), "sent": 0, "noop": 0, "failed": 0,
        "by_user_space": dict(Counter(doc["resolved_user_space"] for doc in documents)),
        "by_dataset": dict(Counter(doc["corpus"] for doc in documents)),
        "by_topic": dict(Counter(doc.get("topic_id") for doc in documents)),
        "errors": [],
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.ERROR if args.quiet else logging.INFO, format="%(levelname)s: %(message)s")
    args.datasets_dir = args.datasets_dir.expanduser().resolve()
    if args.print_web_guide:
        documents = load_documents(args)
        print_web_guide(documents, args.datasets_dir, args.api_url)
        return 0
    try:
        token = fetch_token(args)
    except Exception as exc:
        LOG.error("%s", exc)
        return 1
    if args.print_token:
        if token:
            print(token)
            return 0
        LOG.error("No token resolved")
        return 1
    documents = load_documents(args)
    report = make_report(args, documents)
    try:
        if args.fallback_index and not health_ok(args.api_url):
            LOG.warning(
                "Ingest API unavailable at %s — attempting local pipeline/index fallback",
                args.api_url,
            )
            make_fallback(
                documents,
                report,
                args.dry_run,
                force=args.force_fallback,
                max_docs=args.fallback_max_docs,
                stop_on_failed=args.stop_on_failed,
            )
        elif not health_ok(args.api_url) and not args.fallback_index and not args.dry_run:
            msg = (
                f"Ingest API unavailable at {args.api_url}. "
                "P0: make ingest   |   P1: make compose-up PROFILES=core,ingest"
            )
            LOG.error("%s", msg)
            report["failed"] += len(documents)
            report["errors"].append(
                {"doc_id": "*", "path": "*", "error": msg}
            )
        elif not args.dry_run:
            consecutive_refused = 0
            progress = ProgressTracker(
                len(documents),
                every=args.progress_every,
                quiet=args.quiet,
            )
            mode = "wait-for-index" if args.wait else "accept-only"
            LOG.info(
                "Starting ingest of %s document(s) with %s worker(s) (%s)",
                len(documents),
                args.workers,
                mode,
            )
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = {
                    executor.submit(upload, document, args, token): document
                    for document in documents
                }
                for future in as_completed(futures):
                    document = futures[future]
                    doc_id = str(document.get("id") or "")
                    try:
                        terminal = future.result()
                        report["sent"] += 1
                        if terminal == "noop":
                            report["noop"] += 1
                        consecutive_refused = 0
                        progress.tick(ok=True, doc_id=doc_id or None)
                    except Exception as exc:
                        report["failed"] += 1
                        report["errors"].append({
                            "doc_id": document.get("id"),
                            "path": str(document.get("path")),
                            "error": str(exc),
                        })
                        LOG.error("Failed %s: %s", document.get("id"), exc)
                        progress.tick(ok=False, doc_id=doc_id or None)
                        if args.stop_on_failed:
                            reason = (
                                f"stop-on-failed: doc={document.get('id')} "
                                f"error={exc}"
                            )
                            LOG.error(
                                "stop-on-failed: aborting client and stopping "
                                "ingest server — %s",
                                exc,
                            )
                            abort_remaining_uploads(
                                futures,
                                report,
                                error="aborted: stop-on-failed",
                            )
                            stop_ingest_server(
                                args.api_url, token, reason=reason
                            )
                            break
                        if "connection refused" in str(exc).lower():
                            consecutive_refused += 1
                        else:
                            consecutive_refused = 0
                        if consecutive_refused >= 20:
                            LOG.error(
                                "Ingest API appears down (connection refused ×%s); "
                                "aborting remaining uploads. Restart with: make ingest",
                                consecutive_refused,
                            )
                            abort_remaining_uploads(
                                futures,
                                report,
                                error="aborted: ingest API connection refused",
                            )
                            break
            if not args.quiet:
                LOG.info("Finished: %s", progress.line())
    finally:
        report["ended_at"] = now()
        if args.output_report:
            args.output_report.parent.mkdir(parents=True, exist_ok=True)
            args.output_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        print(json.dumps(report, indent=2))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
