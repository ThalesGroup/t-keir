"""Title: OKF v0.1 static and query-scoped bundle exporter.

Example:
    >>> from thot.okf.exporter import first_sentence, render_frontmatter
    >>> first_sentence("Hello world. More text.")
    'Hello world.'

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
import tarfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import yaml

from thot.action.correlation import current_correlation_id, generate_trace_id
from thot.action.models import (
    ActionContext,
    ActionRecord,
    ActorInfo,
    ContextVersions,
    DecisionInfo,
    ExecutionInfo,
    ImpactInfo,
    IntentInfo,
    ResultInfo,
    sha256_hex,
    utc_now_rfc3339,
)
from thot.action.sink import ActionSink, default_action_sink
from thot.compose.kg import UserSpaceKG
from thot.core.SentenceSegmenter import SentenceSegmenter
from thot.okf.models import (
    OkfBundle,
    OkfConceptFrontmatter,
    OkfExportRequest,
    OkfExportResult,
)
from thot.tools.search.vespa_client import (
    VespaClient,
    document_vespa_id,
    normalize_user_space,
)

LOGGER = logging.getLogger(__name__)

BATCH_SIZE = 50
OKF_VERSION = "0.1"


class OkfVespaClient(Protocol):
    """Minimal Vespa surface used by the exporter (mockable in tests)."""

    async def list_parent_documents(
        self,
        *,
        user_space: str,
        max_docs: int,
        doc_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return parent document field dicts for ``user_space``."""

    async def list_chunk_ids_for_parent(
        self,
        *,
        user_space: str,
        doc_ref: str,
        parent_source_id: str,
    ) -> list[dict[str, Any]]:
        """Return chunk stubs ``{chunk_id, text_raw}`` for a parent."""


class VespaOkfBackend:
    """Default backend: YQL over ``tkeir_document`` / ``chunk`` schemas."""

    def __init__(self, vespa: VespaClient | None = None) -> None:
        self._vespa = vespa or VespaClient()

    async def list_parent_documents(
        self,
        *,
        user_space: str,
        max_docs: int,
        doc_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        space = normalize_user_space(user_space)
        wanted = {normalize_user_space(d) for d in (doc_ids or [])} if doc_ids else None
        # Prefer source_doc_id match when callers pass logical ids.
        hits = max(1, min(int(max_docs), 400))
        payload: dict[str, Any] = {
            "yql": (
                "select * from tkeir_document where true "
                f"limit {hits}"
            ),
            "hits": hits,
            "streaming.groupname": space,
        }
        response = await self._vespa.search(payload)
        children = (
            ((response.get("root") or {}).get("children"))
            if isinstance(response, dict)
            else None
        ) or []
        out: list[dict[str, Any]] = []
        for child in children:
            fields = dict((child or {}).get("fields") or {})
            fields["_vespa_id"] = str((child or {}).get("id") or "")
            doc_space = normalize_user_space(
                str(fields.get("user_space") or space)
            )
            if doc_space != space:
                continue
            source = str(fields.get("source_doc_id") or "")
            if wanted is not None:
                key = source or fields.get("_vespa_id") or ""
                if source not in wanted and key not in wanted:
                    # also allow stable key / basename matches
                    if not any(
                        w in source or source.endswith(w) or w == key
                        for w in wanted
                    ):
                        continue
            out.append(fields)
            if len(out) >= max_docs:
                break
        return out

    async def list_chunk_ids_for_parent(
        self,
        *,
        user_space: str,
        doc_ref: str,
        parent_source_id: str,
    ) -> list[dict[str, Any]]:
        space = normalize_user_space(user_space)
        # Match by doc_ref attribute when possible; fall back to parent title search.
        yql = (
            f'select * from chunk where doc_ref contains '
            f'"{_yql_escape(doc_ref)}" limit 200'
        )
        payload: dict[str, Any] = {
            "yql": yql,
            "hits": 200,
            "streaming.groupname": space,
        }
        try:
            response = await self._vespa.search(payload)
        except Exception:  # noqa: BLE001
            LOGGER.warning(
                "chunk lookup failed for doc_ref=%s; retrying broad query",
                doc_ref,
            )
            payload["yql"] = "select * from chunk where true limit 200"
            response = await self._vespa.search(payload)
        children = (
            ((response.get("root") or {}).get("children"))
            if isinstance(response, dict)
            else None
        ) or []
        out: list[dict[str, Any]] = []
        for child in children:
            fields = (child or {}).get("fields") or {}
            chunk_space = normalize_user_space(
                str(fields.get("user_space") or space)
            )
            if chunk_space != space:
                continue
            ref = str(fields.get("doc_ref") or "")
            if doc_ref and doc_ref not in ref and parent_source_id not in ref:
                continue
            cid = str(fields.get("chunk_id") or "").strip()
            if not cid:
                continue
            out.append(
                {
                    "chunk_id": cid,
                    "text_raw": str(fields.get("text_raw") or "")[:240],
                }
            )
        return out


def _yql_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def default_okf_root() -> Path:
    """Return ``OKF_ROOT`` or ``.tkeir-okf`` under CWD."""
    raw = os.getenv("OKF_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.cwd() / ".tkeir-okf").resolve()


def first_sentence(text: str, *, language: str = "en") -> str:
    """Return the first sentence of ``text`` (pysbd via SentenceSegmenter).

    Example:
        >>> from thot.okf.exporter import first_sentence
        >>> first_sentence("One. Two.")
        'One.'
    """
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return ""
    try:
        sentences = SentenceSegmenter(language).segment(cleaned)
    except Exception:  # noqa: BLE001
        sentences = []
    if sentences:
        return str(sentences[0]).strip()
    # Fallback: first period / hard truncate
    for sep in (". ", "? ", "! "):
        if sep in cleaned:
            return cleaned.split(sep, 1)[0].strip() + sep.strip()
    return cleaned[:200]


def render_frontmatter(fm: OkfConceptFrontmatter) -> str:
    """Serialize frontmatter to YAML between ``---`` fences."""
    data = fm.model_dump(mode="json", exclude_none=True)
    # Stable key order for tests / diffs
    dumped = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()
    return f"---\n{dumped}\n---\n"


def _content_text(fields: dict[str, Any]) -> str:
    content = fields.get("content")
    if isinstance(content, list):
        return " ".join(str(x) for x in content if x)
    if isinstance(content, str):
        return content
    return ""


def _keywords_from_fields(fields: dict[str, Any], limit: int = 10) -> list[str]:
    tags: list[str] = []
    for key in ("title_keywords", "content_keywords", "keywords"):
        raw = fields.get(key)
        if isinstance(raw, list):
            tags.extend(str(x).strip() for x in raw if str(x).strip())
        elif isinstance(raw, str) and raw.strip():
            tags.append(raw.strip())
    # Deduplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        low = tag.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(tag)
        if len(out) >= limit:
            break
    return out


def _entities_table(json_ld: str) -> str:
    if not json_ld or not json_ld.strip():
        return "_No entities available._\n"
    try:
        payload = json.loads(json_ld)
    except json.JSONDecodeError:
        return "_Ontology JSON-LD not parseable as JSON._\n"
    nodes = payload if isinstance(payload, list) else [payload]
    rows: list[tuple[str, str, str]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        types = node.get("@type") or node.get("type") or ""
        if isinstance(types, list):
            type_s = ", ".join(str(t) for t in types)
        else:
            type_s = str(types) if types else ""
        label = (
            node.get("rdfs:label")
            or node.get("label")
            or node.get("http://www.w3.org/2000/01/rdf-schema#label")
            or node.get("@id")
            or ""
        )
        if isinstance(label, list):
            label = label[0] if label else ""
        if isinstance(label, dict):
            label = label.get("@value") or label.get("value") or str(label)
        freq = node.get("frequency") or node.get("count") or ""
        if not type_s and not label:
            continue
        rows.append((str(type_s), str(label), str(freq)))
    if not rows:
        return "_No entities available._\n"
    lines = [
        "| @type | rdfs:label | frequency |",
        "| --- | --- | --- |",
    ]
    for type_s, label, freq in rows[:40]:
        lines.append(f"| {type_s} | {label} | {freq} |")
    return "\n".join(lines) + "\n"


def _relations_table(kg: UserSpaceKG, *, limit: int = 20) -> str:
    triples = kg.find_svo(limit=limit)
    if not triples:
        return "_No relations available._\n"
    lines = [
        "| subject | predicate | object |",
        "| --- | --- | --- |",
    ]
    for triple in triples:
        subj = str(triple.get("subject") or triple.get("s") or "")
        pred = str(triple.get("predicate") or triple.get("p") or "")
        obj = str(triple.get("object") or triple.get("o") or "")
        lines.append(f"| {subj} | {pred} | {obj} |")
    return "\n".join(lines) + "\n"


def _emit_export_action(
    *,
    sink: ActionSink,
    user_space: str,
    kind: str,
    doc_ids: list[str],
    bundle_id: str,
    status: str = "success",
    error: str | None = None,
) -> str:
    cid = current_correlation_id() or generate_trace_id()
    record = ActionRecord(
        correlation_id=cid,
        actor=ActorInfo(type="service", id=user_space),
        intent=IntentInfo(declared="okf.export", scope_source="manual"),
        context=ActionContext(
            env=os.getenv("TKEIR_ENV", "dev"),
            service=os.getenv("TKEIR_SERVICE", "tkeir-okf"),
            versions=ContextVersions(app=os.getenv("TKEIR_VERSION", "")),
            request_hash=sha256_hex(f"{bundle_id}:{kind}:{len(doc_ids)}"),
        ),
        decision=DecisionInfo(policy_result="allow", rules_fired=[kind]),
        execution=ExecutionInfo(
            started_at=utc_now_rfc3339(),
            ended_at=utc_now_rfc3339(),
            status=status,  # type: ignore[arg-type]
        ),
        result=ResultInfo(doc_ids=doc_ids, error=error),
        impact=ImpactInfo(class_="write"),
        ext={
            "action_kind": kind,
            "bundle_id": bundle_id,
            "user_space": user_space,
            "tkeir_okf_version": OKF_VERSION,
        },
    )
    sink.append(record)
    return record.action_id


def _write_concept_file(path: Path, fm: OkfConceptFrontmatter, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_frontmatter(fm) + "\n" + body.lstrip() + "\n", encoding="utf-8"
    )


def _safe_concept_filename(doc_id: str) -> str:
    cleaned = "".join(
        c if c.isalnum() or c in "-_." else "_" for c in doc_id
    ).strip("._")
    return cleaned or "document"


async def _build_concept_markdown(
    *,
    fields: dict[str, Any],
    user_space: str,
    chunk_stubs: list[dict[str, Any]],
    kg: UserSpaceKG,
) -> tuple[OkfConceptFrontmatter, str, bool]:
    source = str(fields.get("source_doc_id") or fields.get("_vespa_id") or "unknown")
    title = str(fields.get("title") or source)
    content = _content_text(fields)
    description = first_sentence(content)
    json_ld = str(fields.get("json_ld") or fields.get("document_ontology") or "")
    if isinstance(fields.get("document_ontology"), dict):
        ont = fields["document_ontology"]
        json_ld = str(ont.get("json_ld") or json_ld)
    unfilled = not bool(json_ld.strip())
    tags = _keywords_from_fields(fields)
    if not tags:
        for ent in kg.find_keywords(limit=10):
            lab = str(ent.get("label") or "").strip()
            if lab:
                tags.append(lab)
        tags = tags[:10]
    chunk_ids = [str(c["chunk_id"]) for c in chunk_stubs if c.get("chunk_id")]
    doc_type = str(fields.get("doc_type") or "Document")
    pipeline_sha = fields.get("pipeline_config_sha256") or fields.get(
        "tkeir_pipeline_sha"
    )
    fm = OkfConceptFrontmatter(
        type=doc_type,
        title=title,
        description=description or None,
        resource=f"vespa://{user_space}/{source}",
        tags=tags,
        timestamp=datetime.now(timezone.utc),
        tkeir_doc_id=source,
        tkeir_user_space=user_space,
        tkeir_chunk_ids=chunk_ids,
        tkeir_pipeline_sha=str(pipeline_sha) if pipeline_sha else None,
        tkeir_okf_version=OKF_VERSION,
    )
    citation_lines = [
        f"- [chunk {cid}](../chunks/{cid}.md)" for cid in chunk_ids
    ] or ["_No chunk citations._"]
    body = "\n".join(
        [
            f"# {title}",
            "",
            "## Entities",
            "",
            _entities_table(json_ld).rstrip(),
            "",
            "## Relations",
            "",
            _relations_table(kg).rstrip(),
            "",
            "## Knowledge Graph",
            "",
            kg.summary(topic=title, max_triples=30),
            "",
            "## Citations",
            "",
            *citation_lines,
            "",
        ]
    )
    return fm, body, unfilled


async def export_full(
    request: OkfExportRequest,
    vespa_client: OkfVespaClient | None = None,
    action_sink: ActionSink | None = None,
) -> OkfExportResult:
    """Export documents in ``user_space`` as an OKF v0.1 bundle.

    Example:
        >>> import inspect
        >>> from thot.okf.exporter import export_full
        >>> inspect.iscoroutinefunction(export_full)
        True
    """
    sink = action_sink if action_sink is not None else default_action_sink()
    backend: OkfVespaClient = vespa_client or VespaOkfBackend()
    space = normalize_user_space(request.user_space)
    bundle_id = str(uuid.uuid4())
    root = (
        Path(request.output_dir).expanduser().resolve()
        if request.output_dir
        else default_okf_root() / bundle_id
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / "concepts").mkdir(exist_ok=True)
    (root / "chunks").mkdir(exist_ok=True)

    parents = await backend.list_parent_documents(
        user_space=space,
        max_docs=request.max_docs,
        doc_ids=request.doc_ids,
    )
    unfilled: list[str] = []
    concept_ids: list[str] = []
    batch_ids: list[str] = []
    last_action_id = ""
    written = 0

    for fields in parents:
        source = str(
            fields.get("source_doc_id") or fields.get("_vespa_id") or f"doc-{written}"
        )
        doc_ref = str(
            fields.get("_vespa_id")
            or document_vespa_id(source, user_space=space)
        )
        chunk_stubs = await backend.list_chunk_ids_for_parent(
            user_space=space,
            doc_ref=doc_ref,
            parent_source_id=source,
        )
        json_ld = str(fields.get("json_ld") or "")
        if isinstance(fields.get("document_ontology"), dict):
            json_ld = str(
                fields["document_ontology"].get("json_ld") or json_ld
            )
        kg = UserSpaceKG(space, use_process_cache=False)
        turtles = [json_ld] if json_ld.strip() else []
        kg.load(turtles, document_ids=[source])
        fm, body, missing_ont = await _build_concept_markdown(
            fields=fields,
            user_space=space,
            chunk_stubs=chunk_stubs,
            kg=kg,
        )
        if missing_ont:
            unfilled.append(source)
        concept_rel = f"concepts/{_safe_concept_filename(source)}"
        _write_concept_file(root / f"{concept_rel}.md", fm, body)
        concept_ids.append(concept_rel)
        for stub in chunk_stubs:
            cid = str(stub["chunk_id"])
            excerpt = first_sentence(str(stub.get("text_raw") or ""))
            chunk_fm = OkfConceptFrontmatter(
                type="Chunk",
                title=f"chunk {cid}",
                description=excerpt or None,
                resource=f"vespa://{space}/chunk/{cid}",
                tags=[],
                timestamp=datetime.now(timezone.utc),
                tkeir_doc_id=source,
                tkeir_user_space=space,
                tkeir_chunk_ids=[cid],
                tkeir_okf_version=OKF_VERSION,
            )
            chunk_body = (
                f"# Chunk `{cid}`\n\n"
                f"Parent: [{concept_rel}](../{concept_rel}.md)\n\n"
                f"{excerpt}\n"
            )
            _write_concept_file(root / "chunks" / f"{cid}.md", chunk_fm, chunk_body)
        batch_ids.append(source)
        written += 1
        if len(batch_ids) >= BATCH_SIZE:
            last_action_id = _emit_export_action(
                sink=sink,
                user_space=space,
                kind="okf.export.batch",
                doc_ids=list(batch_ids),
                bundle_id=bundle_id,
            )
            batch_ids.clear()

    if batch_ids or written == 0:
        last_action_id = _emit_export_action(
            sink=sink,
            user_space=space,
            kind="okf.export.batch" if batch_ids else "okf.export.full",
            doc_ids=list(batch_ids) if batch_ids else [],
            bundle_id=bundle_id,
        )

    # index.md + log.md
    index_lines = [
        "# OKF Bundle Index",
        "",
        f"- bundle_id: `{bundle_id}`",
        f"- user_space: `{space}`",
        f"- concept_count: {len(concept_ids)}",
        f"- tkeir_okf_version: {OKF_VERSION}",
        "",
        "## Concepts",
        "",
    ]
    for cid in concept_ids:
        index_lines.append(f"- [{cid}]({cid}.md)")
    if request.query:
        index_lines.extend(["", f"- [query_context](query_context.md)"])
    (root / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    log_entry = (
        f"# OKF Log\n\n"
        f"- {utc_now_rfc3339()} — export "
        f"concepts={len(concept_ids)} user_space={space} "
        f"bundle_id={bundle_id}\n"
    )
    (root / "log.md").write_text(log_entry, encoding="utf-8")

    bundle = OkfBundle(
        bundle_id=bundle_id,
        user_space=space,
        query=request.query,
        concept_count=len(concept_ids),
        created_at=datetime.now(timezone.utc),
        path=str(root),
    )
    meta = {
        "bundle": bundle.model_dump(mode="json"),
        "concept_ids": concept_ids,
        "unfilled_docs": unfilled,
    }
    (root / ".tkeir-meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    last_action_id = _emit_export_action(
        sink=sink,
        user_space=space,
        kind="okf.export.full" if not request.query else "okf.export.scoped",
        doc_ids=[c.split("/", 1)[-1] for c in concept_ids],
        bundle_id=bundle_id,
    ) or last_action_id
    return OkfExportResult(
        bundle=bundle,
        unfilled_docs=unfilled,
        action_record_id=last_action_id,
    )


class OkfRagClient(Protocol):
    """Minimal RAG surface for scoped export."""

    async def query(
        self, query: str, *, user_space: str, hits: int
    ) -> dict[str, Any]:
        """Return a RAG-like payload with document ids and answer."""


class HttpOkfRagClient:
    """Call ``MCP_RAG_URL`` /rag/query when available."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (
            base_url
            or os.getenv("MCP_RAG_URL")
            or os.getenv("RAG_URL")
            or "http://127.0.0.1:8090"
        ).rstrip("/")

    async def query(
        self, query: str, *, user_space: str, hits: int
    ) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/rag/query",
                json={"query": query, "hits": hits},
                headers={"X-Tkeir-User-Space": user_space},
            )
            if response.is_error:
                # Fallback: retrieval-only hybrid via empty answer
                return {
                    "answer": "",
                    "chunks": [],
                    "document_ids": [],
                    "error": response.text[:300],
                }
            data = response.json()
            return data if isinstance(data, dict) else {}


def _document_ids_from_rag(payload: dict[str, Any], *, max_docs: int) -> list[str]:
    ids: list[str] = []
    for key in ("document_ids", "documents"):
        raw = payload.get(key)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    ids.append(item.strip())
                elif isinstance(item, dict):
                    for k in ("document_id", "parent_doc_id", "source_doc_id", "id"):
                        val = item.get(k)
                        if val:
                            ids.append(str(val))
                            break
    for chunk in payload.get("chunks") or []:
        if not isinstance(chunk, dict):
            continue
        for k in ("parent_doc_id", "document_id", "source_doc_id"):
            val = chunk.get(k)
            if val:
                ids.append(str(val))
                break
    # Deduplicate
    seen: set[str] = set()
    out: list[str] = []
    for doc_id in ids:
        if doc_id in seen:
            continue
        seen.add(doc_id)
        out.append(doc_id)
        if len(out) >= max_docs:
            break
    return out


async def export_scoped(
    request: OkfExportRequest,
    vespa_client: OkfVespaClient | None = None,
    rag_client: OkfRagClient | None = None,
    action_sink: ActionSink | None = None,
) -> OkfExportResult:
    """Export documents returned by a RAG query as an OKF bundle.

    Example:
        >>> import inspect
        >>> from thot.okf.exporter import export_scoped
        >>> inspect.iscoroutinefunction(export_scoped)
        True
    """
    if not request.query:
        return await export_full(
            request, vespa_client=vespa_client, action_sink=action_sink
        )
    rag = rag_client or HttpOkfRagClient()
    space = normalize_user_space(request.user_space)
    rag_payload = await rag.query(
        request.query, user_space=space, hits=request.max_docs
    )
    doc_ids = _document_ids_from_rag(rag_payload, max_docs=request.max_docs)
    scoped = OkfExportRequest(
        user_space=space,
        query=request.query,
        max_docs=request.max_docs,
        output_dir=request.output_dir,
        doc_ids=doc_ids or None,
    )
    # If RAG returned no ids, still create an empty-ish bundle with query context
    result = await export_full(
        scoped, vespa_client=vespa_client, action_sink=action_sink
    )
    root = Path(result.bundle.path)
    answer = str(
        rag_payload.get("answer")
        or rag_payload.get("short_answer")
        or ""
    ).strip()
    concept_links = []
    meta_path = root / ".tkeir-meta.json"
    concept_ids: list[str] = []
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        concept_ids = list(meta.get("concept_ids") or [])
    for cid in concept_ids:
        concept_links.append(f"- [{cid}]({cid}.md)")
    qc_fm = OkfConceptFrontmatter(
        type="Query Context",
        title="Query Context",
        description=first_sentence(request.query),
        resource=None,
        tags=["query"],
        timestamp=datetime.now(timezone.utc),
        tkeir_doc_id="query_context",
        tkeir_user_space=space,
        tkeir_chunk_ids=[],
        tkeir_okf_version=OKF_VERSION,
    )
    qc_body = "\n".join(
        [
            "# Query Context",
            "",
            "## Query",
            "",
            request.query,
            "",
            "## RAG answer summary",
            "",
            answer or "_No answer returned._",
            "",
            "## Concepts",
            "",
            *(concept_links or ["_No concepts._"]),
            "",
        ]
    )
    _write_concept_file(root / "query_context.md", qc_fm, qc_body)
    # Refresh index to include query_context
    index_path = root / "index.md"
    if index_path.is_file():
        text = index_path.read_text(encoding="utf-8")
        if "query_context.md" not in text:
            index_path.write_text(
                text.rstrip() + "\n\n- [query_context](query_context.md)\n",
                encoding="utf-8",
            )
    result.bundle.query = request.query
    result.bundle.concept_count = len(concept_ids) + 1
    return result


def tar_bundle(bundle_path: Path, dest: Path | None = None) -> Path:
    """Create a ``.tar.gz`` archive of an OKF bundle directory."""
    root = bundle_path.resolve()
    out = dest or root.with_suffix(".tar.gz")
    if out.suffixes[-2:] != [".tar", ".gz"]:
        out = Path(str(out) + ".tar.gz") if not str(out).endswith(".tar.gz") else out
    with tarfile.open(out, "w:gz") as archive:
        archive.add(root, arcname=root.name)
    return out


def delete_bundle(bundle_path: Path) -> None:
    """Atomically remove a bundle directory (DSR / forget)."""
    root = bundle_path.resolve()
    if not root.exists():
        return
    tmp = root.with_name(root.name + ".deleting")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    os.replace(root, tmp)
    shutil.rmtree(tmp, ignore_errors=True)


def cli_main(argv: list[str] | None = None) -> int:
    """CLI entry: ``tkeir-okf-export``."""
    parser = argparse.ArgumentParser(prog="tkeir-okf-export")
    parser.add_argument("--user-space", default=os.getenv("VESPA_USER_SPACE", "dev@tkeir"))
    parser.add_argument("--query", default=None)
    parser.add_argument("--output", default=None, help="Bundle output directory")
    parser.add_argument("--max-docs", type=int, default=200)
    args = parser.parse_args(argv)
    request = OkfExportRequest(
        user_space=args.user_space,
        query=args.query,
        max_docs=args.max_docs,
        output_dir=args.output,
    )
    if args.query:
        result = asyncio.run(export_scoped(request))
    else:
        result = asyncio.run(export_full(request))
    print(
        json.dumps(
            {
                "bundle_id": result.bundle.bundle_id,
                "path": result.bundle.path,
                "concept_count": result.bundle.concept_count,
                "query": result.bundle.query,
                "unfilled_docs": result.unfilled_docs,
                "action_record_id": result.action_record_id,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
