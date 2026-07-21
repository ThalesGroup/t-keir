#!/usr/bin/env python3
"""Ingest T-KEIR demo-corpus documents through the ingest API or Make fallback."""
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
import time
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOG = logging.getLogger("tkeir.corpus.ingest")
REPO_ROOT = Path(__file__).resolve().parents[2]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def csv_values(value: str | None) -> set[str] | None:
    if not value:
        return None
    values = {item.strip() for item in value.split(",") if item.strip()}
    return values or None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=REPO_ROOT / "workspace",
                        help="Root containing corpus_nato/ and/or corpus_enterprise/")
    parser.add_argument("--api-url", default="http://localhost:8091")
    parser.add_argument("--corpus", choices=("osint", "enterprise", "all"), default="all")
    parser.add_argument("--topics", help="Comma-separated topic IDs")
    parser.add_argument("--formats", help="Comma-separated document formats")
    parser.add_argument("--user-space", help="Override the user space for every document")
    parser.add_argument("--token")
    parser.add_argument("--token-url")
    parser.add_argument("--client-id", default="tkeir-cli")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=10,
                        help="Reserved for future batch uploads (currently per-document)")
    parser.add_argument("--status-poll", action="store_true")
    parser.add_argument("--fallback-index", action="store_true")
    parser.add_argument("--output-report", type=Path)
    parser.add_argument("--print-web-guide", action="store_true")
    parser.add_argument("--print-token", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args(argv)
    if args.workers < 1 or args.batch_size < 1:
        parser.error("--workers and --batch-size must be positive")
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
    wanted = ("osint", "enterprise") if args.corpus == "all" else (args.corpus,)
    dirs = {"osint": "corpus_nato", "enterprise": "corpus_enterprise"}
    documents: list[dict[str, Any]] = []
    for corpus in wanted:
        manifest = args.corpus_dir / dirs[corpus] / "manifest.json"
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
            documents.append(doc)
    return documents


def multipart(document: dict[str, Any]) -> tuple[bytes, str]:
    boundary = f"----tkeir-{uuid.uuid4().hex}"
    metadata = {
        "topic_id": document.get("topic_id"), "corpus": document.get("corpus"),
        "doc_type": document.get("doc_type"), "language": document.get("lang", "en"),
        "title": document.get("title"), "user_space": document["resolved_user_space"],
    }
    path = document["file_path"]
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\n"
        "Content-Type: application/json\r\n\r\n".encode() + json.dumps(metadata).encode() + b"\r\n",
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
        "Content-Type: application/octet-stream\r\n\r\n".encode() + path.read_bytes() + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts), boundary


def poll_status(api_url: str, job_id: str, headers: dict[str, str]) -> None:
    for _ in range(30):
        status, body = request_bytes("GET", f"{api_url}/ingest/status/{job_id}", headers=headers)
        if not 200 <= status < 300:
            LOG.warning("Status poll for %s returned HTTP %s", job_id, status)
            return
        try:
            result = json.loads(body)
        except json.JSONDecodeError:
            return
        if str(result.get("status", "")).lower() in {"completed", "complete", "failed", "error"}:
            return
        time.sleep(1)


def upload(document: dict[str, Any], args: argparse.Namespace, token: str | None) -> None:
    data, boundary = multipart(document)
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "X-User-Space": document["resolved_user_space"],
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    status, body = request_bytes("POST", f"{args.api_url.rstrip('/')}/ingest/document", data=data, headers=headers)
    if not 200 <= status < 300:
        raise RuntimeError(f"HTTP {status}: {body.decode(errors='replace')}")
    if args.status_poll:
        try:
            response = json.loads(body)
            job_id = response.get("job_id") or response.get("jobId") or response.get("id")
            if job_id:
                poll_status(args.api_url.rstrip("/"), str(job_id), headers)
        except json.JSONDecodeError:
            pass


def health_ok(api_url: str) -> bool:
    try:
        status, _ = request_bytes("GET", f"{api_url.rstrip('/')}/health", timeout=5)
        return 200 <= status < 300
    except Exception as exc:
        LOG.warning("Health check failed: %s", exc)
        return False


def make_fallback(documents: list[dict[str, Any]], report: dict[str, Any], dry_run: bool) -> None:
    """Fall back to pipeline + Vespa index without ``make pipeline`` (avoids spaCy reinstall side effects)."""
    report["fallback_mode"] = "make_index"
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        groups[document["resolved_user_space"]].append(document)
    if dry_run:
        return
    tkeir_dir = REPO_ROOT / "tkeir"
    uv = os.environ.get("UV", "uv")
    python = os.environ.get("PYTHON", "3.11")
    pipeline_cfg = tkeir_dir / "configs" / "pipeline.yaml"
    for space, group in groups.items():
        with tempfile.TemporaryDirectory(prefix="tkeir-ingest-") as temp:
            stage, output = Path(temp) / "stage", Path(temp) / "output"
            stage.mkdir()
            output.mkdir()
            for index, document in enumerate(group):
                shutil.copy2(document["file_path"], stage / f"{index:05d}_{document['file_path'].name}")
            env = os.environ.copy()
            env["VESPA_USER_SPACE"] = space
            pipeline = subprocess.run(
                [
                    uv, "run", "--no-sync", "--python", python, "tkeir-pipeline",
                    "-c", str(pipeline_cfg),
                    "-i", str(stage),
                    "-o", str(output),
                    "-t", "auto",
                ],
                cwd=tkeir_dir,
                env=env,
                capture_output=True,
                text=True,
            )
            index_result = None
            if pipeline.returncode == 0:
                index_result = subprocess.run(
                    [
                        uv, "run", "--python", python, "python", "-m",
                        "thot.tools.search.index_documents", "-i", str(output),
                    ],
                    cwd=tkeir_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                )
            if pipeline.returncode == 0 and index_result and index_result.returncode == 0:
                report["sent"] += len(group)
            else:
                message = (pipeline.stderr or pipeline.stdout or "").strip()
                if index_result is not None:
                    message = (index_result.stderr or index_result.stdout or message).strip()
                # One group-level error entry (not N copies of the same stderr).
                report["failed"] += len(group)
                report["errors"].append(
                    {
                        "doc_id": ",".join(str(d.get("id")) for d in group[:5]),
                        "path": f"user_space={space} count={len(group)}",
                        "error": message[:2000] or f"pipeline={pipeline.returncode} index={getattr(index_result, 'returncode', None)}",
                    }
                )


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
    print("OSINT corpus → demo-user")
    print("  1. Open http://localhost:3000")
    print("  2. Sign in as: demo-user / demo-user")
    print("  3. Navigate to Upload / Ingest")
    print("  4. Drag files by topic from corpus_nato/ (see examples below)")
    print("  5. Verify: query \"SITREP Objective ALPHA\"")
    print("\nEnterprise corpus → demo-admin (AcmeSystems)")
    print("  1. Sign OUT, sign in as: demo-admin / demo-admin")
    print("  2. Upload from corpus_enterprise/ by topic")
    print("  3. Verify: query \"AcmeSystems Project ATLAS\"")
    print("\nISOLATION CHECK:")
    print("  As demo-user  → query \"AcmeSystems Project ATLAS\" → 0 results")
    print("  As demo-admin → query \"SITREP Objective ALPHA\"    → 0 results")
    print("\nExamples (paths relative to --corpus-dir):")
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
        rel = osint_example["file_path"].relative_to(corpus_dir)
        print(f"curl -X POST {api_url.rstrip('/')}/ingest/document \\")
        print('  -H "Authorization: Bearer $TOKEN_USER" \\')
        print(f"  -F 'file=@{rel}' \\")
        print(f"  -F 'metadata={json.dumps(metadata)}'")
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


def make_report(args: argparse.Namespace, documents: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "started_at": now(), "ended_at": None, "api_url": args.api_url,
        "fallback_mode": None, "total": len(documents), "sent": 0, "noop": 0, "failed": 0,
        "by_user_space": dict(Counter(doc["resolved_user_space"] for doc in documents)),
        "by_corpus": dict(Counter(doc["corpus"] for doc in documents)),
        "by_topic": dict(Counter(doc.get("topic_id") for doc in documents)),
        "errors": [],
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.ERROR if args.quiet else logging.INFO, format="%(levelname)s: %(message)s")
    args.corpus_dir = args.corpus_dir.expanduser().resolve()
    if args.print_web_guide:
        documents = load_documents(args)
        print_web_guide(documents, args.corpus_dir, args.api_url)
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
            LOG.warning("Ingest API is unavailable; using Make pipeline/index fallback")
            make_fallback(documents, report, args.dry_run)
        elif not args.dry_run:
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = {executor.submit(upload, document, args, token): document for document in documents}
                for future in as_completed(futures):
                    document = futures[future]
                    try:
                        future.result()
                        report["sent"] += 1
                    except Exception as exc:
                        report["failed"] += 1
                        report["errors"].append({
                            "doc_id": document.get("id"), "path": str(document.get("path")), "error": str(exc),
                        })
                        LOG.error("Failed %s: %s", document.get("id"), exc)
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
