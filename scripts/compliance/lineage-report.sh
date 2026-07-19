#!/usr/bin/env bash
# Emit a document lineage report from ingest manifests + optional audit store.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DOC_ID="${DOC_ID:-${DOC:?Set DOC=<sha256 doc_id>}}"
INGEST_ROOT="${INGEST_ROOT:-/var/tkeir/ingest}"
FORMAT="${FORMAT:-text}"
export DOC_ID INGEST_ROOT FORMAT

python3 - <<PY
import json
import os
from pathlib import Path

doc_id = os.environ["DOC_ID"]
root = Path(os.environ["INGEST_ROOT"])
manifest = root / "staging" / doc_id / "ingest.manifest.json"
if not manifest.is_file():
    # try manifests dir layout
    candidates = list(root.rglob(f"**/staging/{doc_id}/ingest.manifest.json"))
    if not candidates:
        candidates = list(root.rglob("**/ingest.manifest.json"))
        matches = []
        for path in candidates:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("doc_id") == doc_id or data.get("document", {}).get("doc_id") == doc_id:
                matches.append((path, data))
        if not matches:
            raise SystemExit(f"No manifest found for doc_id={doc_id} under {root}")
        path, data = matches[0]
    else:
        path = candidates[0]
        data = json.loads(path.read_text(encoding="utf-8"))
else:
    path = manifest
    data = json.loads(path.read_text(encoding="utf-8"))

report = {
    "doc_id": doc_id,
    "manifest_path": str(path),
    "ingest_id": data.get("ingest_id"),
    "correlation_id": data.get("correlation_id"),
    "source": data.get("source"),
    "processing": data.get("processing") or {
        "pipeline_config_sha256": data.get("pipeline_config_sha256"),
        "embedder": data.get("embedder"),
    },
    "lineage": data.get("lineage"),
    "status": data.get("status"),
    "note": "Queries that surfaced this doc are listed via audit ActionRecords result.doc_ids",
}
if os.environ.get("FORMAT") == "json":
    print(json.dumps(report, indent=2))
else:
    print(f"doc_id:          {report['doc_id']}")
    print(f"ingest_id:       {report.get('ingest_id')}")
    print(f"correlation_id:  {report.get('correlation_id')}")
    print(f"manifest:        {report['manifest_path']}")
    print(f"status:          {report.get('status')}")
    print(f"source:          {report.get('source')}")
PY
