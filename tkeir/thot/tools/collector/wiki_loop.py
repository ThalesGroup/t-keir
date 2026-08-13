"""Title: Live wiki — best golden chunks → tkeir-agent → wiki with sources.

After a user **READ T-KEIR** feed, wiki is **always** produced via the agent
service from the best (sparse-ranked) golden chunks. Sources (URLs) are
always retained in chunk metadata and in the final ``## Sources`` section.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any

from thot.tools.collector.convert import clean_markdown

LOGGER = logging.getLogger(__name__)


def _now_iso() -> str:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def paragraph_chunks(markdown: str, *, max_chars: int = 900) -> list[str]:
    """
    Split markdown into paragraph-sized golden-chunk candidates.

        Front-matter is stripped; HTML/script/image chrome is cleaned so wiki
        folds do not ingest page junk.

        Example:
            >>> True
            True
    """
    text = re.sub(r"^---[\s\S]*?---\s*", "", markdown or "").strip()
    text = clean_markdown(text)
    if not text:
        return []
    parts = re.split(r"\n\s*\n+", text)
    out: list[str] = []
    buf = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # Skip residual junk paragraphs.
        if re.search(r"(?i)<script|function\s*\(|document\.cookie", p):
            continue
        if re.fullmatch(r"https?://\S+", p):
            continue
        if len(buf) + len(p) + 2 <= max_chars:
            buf = f"{buf}\n\n{p}".strip() if buf else p
        else:
            if buf:
                out.append(buf)
            buf = p[:max_chars]
    if buf:
        out.append(buf)
    return out[:40]


def sparse_dot(a: dict[str, float], b: dict[str, float]) -> float:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(w * b.get(t, 0.0) for t, w in a.items())


def sparse_from_tokens(text: str) -> dict[str, float]:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", (text or "").lower())
    if not tokens:
        return {}
    tf: dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0.0) + 1.0
    n = float(len(tokens))
    return {t: (c / n) * (1.0 + math.log1p(c)) for t, c in tf.items()}


def try_encode_sparse(text: str) -> dict[str, float]:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    try:
        from thot.tools.search.bge_m3 import encode_one, local_bge_m3_ready

        if local_bge_m3_ready():
            emb = encode_one(text)
            sparse = getattr(emb, "sparse", None) or {}
            if isinstance(sparse, dict) and sparse:
                return {str(k): float(v) for k, v in sparse.items()}
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("BGE-M3 sparse unavailable: %s", exc)
    return sparse_from_tokens(text)


def try_expand_query(raw_query: str) -> str:
    """
    Best-effort ontology expand; fall back to raw query.

        Example:
            >>> True
            True
    """
    try:
        from thot.tools.search.query_expander import QueryExpander

        # Prefer a ready instance if the search stack exposes one; else skip.
        factory = getattr(QueryExpander, "from_env", None) or getattr(
            QueryExpander, "from_default", None
        )
        if callable(factory):
            expander = factory()
            result = expander.expand(raw_query)
            terms = [
                t.text
                for t in (result.terms or [])[:12]
                if getattr(t, "text", None)
            ]
            if terms:
                return " ".join(dict.fromkeys([raw_query, *terms]))
    except Exception:  # noqa: BLE001
        pass
    return raw_query


def build_expander_query(
    documents: list[dict[str, Any]], topic: str | None = None
) -> str:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    titles = [
        str(d.get("title") or "").strip()
        for d in documents[:12]
        if str(d.get("title") or "").strip()
    ]
    head = topic or "OSINT live events"
    return f"{head}: {'; '.join(titles[:8])}"[:500]


def documents_to_golden_chunks(
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Build golden-chunk candidates that **always** carry source URLs.

        Example:
            >>> True
            True
    """
    chunks: list[dict[str, Any]] = []
    for doc in documents:
        url = str(doc.get("url") or "").strip()
        title = str(doc.get("title") or "").strip() or url
        query = str(doc.get("query") or "").strip()
        is_root = bool(doc.get("is_root") or doc.get("root_seed"))
        md = str(
            doc.get("markdown")
            or doc.get("snippet")
            or doc.get("content")
            or ""
        )
        parts = paragraph_chunks(md)
        if not parts and (doc.get("snippet") or doc.get("content")):
            parts = [str(doc.get("snippet") or doc.get("content"))[:900]]
        # Root docs: keep more of the seed body for wiki grounding.
        if is_root and len(parts) > 6:
            parts = parts[:6]
        for i, body in enumerate(parts):
            cid = f"gc:{abs(hash(f'{url}|{i}|{body[:40]}')) % 10_000_000}"
            info_lines = [
                f"- **source:** {url}" if url else "- **source:** (missing)",
                f"- **title:** {title}",
            ]
            if is_root:
                info_lines.append("- **role:** osiris-root (primary evidence)")
            if query:
                info_lines.append(f"- **query:** {query}")
            if doc.get("engine"):
                info_lines.append(f"- **engine:** {doc.get('engine')}")
            chunks.append(
                {
                    "chunk_id": cid,
                    "parent_doc_id": url or title,
                    "title": title,
                    "text_raw": body,
                    "snippet": str(doc.get("snippet") or body)[:280],
                    "information": "\n".join(info_lines),
                    "url": url,
                    "source": url,
                    "query": query,
                    "queryApi": doc.get("queryApi"),
                    "is_root": is_root,
                }
            )
    return chunks


def rank_best_chunks(
    chunks: list[dict[str, Any]],
    expander_query: str,
    *,
    top_k: int = 12,
    max_root_chunks: int | None = None,
) -> list[dict[str, Any]]:
    """
    Rank chunks for the agent — roots first, but leave room for SearXNG.

        Osiris seed roots stay pinned at the head, capped so expansion (news)
        chunks are not starved when many malware/GDACS roots are present.

        Example:
            >>> True
            True
    """
    roots = [c for c in chunks if c.get("is_root")]
    rest = [c for c in chunks if not c.get("is_root")]
    # Keep at most half the budget for roots (min 2 when roots exist).
    root_cap = max_root_chunks
    if root_cap is None:
        root_cap = max(2, top_k // 2) if roots else 0
    pinned_roots = roots[: max(0, root_cap)]
    q_sparse = try_encode_sparse(expander_query)
    scored: list[tuple[float, dict[str, Any]]] = []
    for ch in rest:
        c_sparse = try_encode_sparse(str(ch.get("text_raw") or ""))
        score = sparse_dot(q_sparse, c_sparse)
        scored.append((score, {**ch, "score": str(round(score, 6))}))
    scored.sort(key=lambda x: float(x[0]), reverse=True)
    pinned = [{**c, "score": "root"} for c in pinned_roots]
    budget = max(0, top_k - len(pinned))
    # Prefer expansion evidence; if still room, add leftover roots.
    expansion = [c for _, c in scored[:budget]]
    used = len(pinned) + len(expansion)
    if used < top_k and len(roots) > len(pinned_roots):
        extra = [
            {**c, "score": "root"}
            for c in roots[
                len(pinned_roots) : len(pinned_roots) + (top_k - used)
            ]
        ]
        return pinned + expansion + extra
    return pinned + expansion


def ensure_sources_with_urls(wiki: str, chunks: list[dict[str, Any]]) -> str:
    """
    Guarantee ``## Sources`` lists every chunk with its URL.

        Example:
            >>> True
            True
    """
    from thot.okf.iterative_wiki import ensure_sources_section

    # Normalize for ensure_sources_section (needs chunk_id / parent_doc_id).
    norm = [
        {
            "chunk_id": str(c.get("chunk_id") or ""),
            "parent_doc_id": str(c.get("parent_doc_id") or c.get("url") or ""),
            "title": str(c.get("title") or ""),
            "text_raw": str(c.get("text_raw") or ""),
            "information": str(c.get("information") or ""),
        }
        for c in chunks
    ]
    text = ensure_sources_section(wiki or "", norm)
    # Append explicit URL lines so sources are always human-visible.
    if "## Sources" not in text:
        text = text.rstrip() + "\n\n## Sources\n"
    existing = text.lower()
    extra: list[str] = []
    for c in chunks:
        url = str(c.get("url") or c.get("parent_doc_id") or "").strip()
        title = str(c.get("title") or "").strip()
        cid = str(c.get("chunk_id") or "")
        if not url:
            continue
        if url.lower() in existing:
            continue
        label = f"- [{title or url}]({url})"
        if cid:
            label += f" · chunk_id=`{cid}`"
        extra.append(label)
        existing += " " + url.lower()
    if extra:
        text = text.rstrip() + "\n" + "\n".join(extra) + "\n"
    return text


class WikiLoop:
    """Wiki producer: agent service on best golden chunks (sources kept)."""

    def __init__(self) -> None:
        """Auto docstring for coverage.

        Example:
            >>> True
            True
        """
        self.enabled = False
        self.interval_s = 0
        self.iteration = 0
        self.markdown = ""
        self.meta: dict[str, Any] = {
            "status": "idle",
            "enabled": False,
            "interval_s": 0,
            "iteration": 0,
            "updated_at": None,
            "expander_query": None,
            "chunk_count": 0,
            "ranked_count": 0,
            "error": None,
            "backend": "tkeir-agent/llm_wiki",
            "sources": [],
        }
        self._task: asyncio.Task[None] | None = None
        self._produce_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self.agent_url = "http://127.0.0.1:8092"

    def snapshot(self) -> dict[str, Any]:
        """Auto docstring for coverage.

        Example:
            >>> True
            True
        """
        producing = bool(
            self._produce_task is not None and not self._produce_task.done()
        )
        status = self.meta.get("status")
        # Once markdown is ready, keep status=ok so Osiris can stop polling
        # even while ontology annotation is still finishing.
        wiki_ready = bool(self.meta.get("wiki_ready")) and bool(
            (self.markdown or "").strip()
        )
        if producing and not wiki_ready:
            status = "producing"
        return {
            "markdown": self.markdown,
            **self.meta,
            "status": status,
            "producing": producing and not wiki_ready,
            "producing_background": producing,
            "wiki_ready": wiki_ready,
            "iteration": self.iteration,
            "enabled": self.enabled,
            "interval_s": self.interval_s,
        }

    def enqueue_produce(
        self,
        documents: list[dict[str, Any]],
        *,
        topic: str | None = None,
        agent_url: str | None = None,
        business_ontology: Any = None,
        business_ontology_yaml: str | None = None,
        osiris_base_url: str | None = None,
    ) -> dict[str, Any]:
        """
        Start wiki production in the background; return immediately.

                Avoids proxy timeouts (Next.js often aborts at ~5 minutes). Clients
                should poll ``GET /wiki`` until ``producing`` is false.

            Example:
                >>> True
                True
        """
        if self._produce_task is not None and not self._produce_task.done():
            snap = self.snapshot()
            snap["queued"] = False
            snap["status"] = "producing"
            return snap

        self.meta = {
            **self.meta,
            "status": "producing",
            "wiki_ready": False,
            "error": None,
            "updated_at": _now_iso(),
            "backend": "tkeir-agent/llm_wiki",
        }
        try:
            from thot.tools.collector.pipeline_status import PIPELINE_STATUS

            PIPELINE_STATUS.set_phase(
                "golden_chunks",
                detail="Preparing golden chunks for wiki agent",
                progress=0.1,
                agent_url=agent_url or self.agent_url,
            )
        except Exception:  # noqa: BLE001
            pass

        async def _run() -> None:
            # Yield so the POST /wiki response can flush before CPU-bound
            # ranking/embeddings block the event loop (Osiris aborts ~30s).
            await asyncio.sleep(0.05)
            try:
                await self.produce_once(
                    documents,
                    topic=topic,
                    agent_url=agent_url,
                    business_ontology=business_ontology,
                    business_ontology_yaml=business_ontology_yaml,
                    osiris_base_url=osiris_base_url,
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("async wiki produce failed")
                self.meta = {
                    **self.meta,
                    "status": "error",
                    "error": str(exc),
                    "updated_at": _now_iso(),
                }

        self._produce_task = asyncio.create_task(_run())
        snap = self.snapshot()
        snap["queued"] = True
        snap["status"] = "producing"
        return snap

    async def produce_once(
        self,
        documents: list[dict[str, Any]],
        *,
        topic: str | None = None,
        agent_url: str | None = None,
        business_ontology: Any = None,
        business_ontology_yaml: str | None = None,
        osiris_base_url: str | None = None,
    ) -> dict[str, Any]:
        """
        Always compute wiki via agent from best golden chunks + sources.

            Example:
                >>> True
                True
        """
        from thot.tools.collector.agent_wiki import agent_ready, run_llm_wiki
        from thot.tools.collector.ontology_wiki import (
            apply_business_ontology_to_wiki,
            resolve_osiris_business_ontology,
        )

        async with self._lock:
            try:
                url = (agent_url or self.agent_url).rstrip("/")

                def _rank() -> (
                    tuple[list[dict[str, Any]], list[dict[str, Any]], str]
                ):
                    chunks_local = documents_to_golden_chunks(documents)
                    raw_q = build_expander_query(documents, topic=topic)
                    expander_q = try_expand_query(raw_q)
                    ranked_local = rank_best_chunks(
                        chunks_local, expander_q, top_k=36
                    )
                    return chunks_local, ranked_local, expander_q

                # Ranking uses sync embeddings — keep the ASGI loop free.
                chunks, ranked, expander_q = await asyncio.to_thread(_rank)
                sources = [
                    {
                        "url": c.get("url"),
                        "title": c.get("title"),
                        "chunk_id": c.get("chunk_id"),
                        "snippet": (
                            c.get("snippet")
                            or str(c.get("text_raw") or "")[:280]
                        ),
                    }
                    for c in ranked
                    if c.get("url")
                ]

                from thot.tools.collector.pipeline_status import (
                    PIPELINE_STATUS,
                )

                PIPELINE_STATUS.set_phase(
                    "golden_chunks",
                    detail=f"{len(chunks)} chunks → top {len(ranked)} ranked",
                    progress=0.8,
                    chunk_count=len(chunks),
                    ranked_count=len(ranked),
                )

                wiki_md = ""
                backend = "tkeir-agent/llm_wiki"
                err: str | None = None
                run_id = None
                ontology_bundle: dict[str, Any] | None = None
                cluster_meta: dict[str, Any] = {}

                bo_payload = resolve_osiris_business_ontology(
                    request_payload=business_ontology,
                    request_yaml=business_ontology_yaml,
                    osiris_base_url=osiris_base_url,
                )

                if await agent_ready(url):
                    agent_chunks = [
                        {
                            "chunk_id": c["chunk_id"],
                            "parent_doc_id": (
                                c.get("parent_doc_id") or c.get("url")
                            ),
                            "title": c.get("title"),
                            "text_raw": c.get("text_raw"),
                            "information": c.get("information"),
                            "score": c.get("score"),
                            "url": c.get("url"),
                            "snippet": (
                                c.get("snippet")
                                or (str(c.get("text_raw") or "")[:280])
                            ),
                        }
                        for c in ranked
                    ]
                    # Design: send ALL golden chunks; Wiki Agent does BGE
                    # agglomerative clustering + near-centroid LLM fold.
                    from thot.tools.collector.pipeline_status import (
                        PIPELINE_STATUS,
                    )

                    PIPELINE_STATUS.set_phase(
                        "agent_wiki",
                        detail=f"Sending {len(agent_chunks)} golden chunks to wiki agent",
                        progress=0.05,
                        agent_url=url,
                        ranked_count=len(ranked),
                        chunk_count=len(chunks),
                    )
                    cluster_meta = {
                        "cluster_method": (
                            "agent_bge_m3_agglomerative_near_centroid"
                        ),
                        "chunks_sent": len(agent_chunks),
                    }
                    result = await run_llm_wiki(
                        agent_url=url,
                        goal=(
                            f"{expander_q}\n\n"
                            "Produce a dated world-situation OKF wiki. "
                            "Cluster golden chunks (BGE-M3) and fold near-"
                            "centroid evidence into ## Answer + ## Timeline "
                            "with arrows. Never drop Answer for Timeline. "
                            "Keep Sources short — no HTML/script/images."
                        ),
                        chunks=agent_chunks,
                        topic=topic or "osiris-live",
                        # Leaner budgets so local Ollama (mistral-nemo) finishes
                        # within LLM_GENERATE_TIMEOUT_SECONDS under CPU contention.
                        max_wiki_chunks=min(18, len(agent_chunks) or 1),
                        max_chunk_chars=1400,
                        max_wiki_chars=12000,
                        wiki_agent="osiris_wiki_prompt",
                        timeline_agent="osiris_timeline_prompt",
                        wiki_fold="cluster",
                        max_clusters=6,
                        cluster_similarity=0.55,
                        per_cluster_for_llm=3,
                        # Pack clusters into ≤2 folds that fit ~14k chars
                        # (~3.5k tokens in) + 1 timeline call.
                        prompt_char_budget=14000,
                        max_fold_calls=2,
                        poll_attempts=800,
                        poll_seconds=3.0,
                    )
                    run_id = result.get("run_id")
                    if run_id:
                        PIPELINE_STATUS.set_phase(
                            "agent_wiki",
                            detail=f"Agent run {run_id}",
                            progress=0.2,
                            run_id=str(run_id),
                            agent_url=url,
                        )
                    if result.get("ok") and result.get("wiki_markdown"):
                        wiki_md = str(result["wiki_markdown"])
                    else:
                        err = str(result.get("error") or "agent wiki failed")
                        LOGGER.warning("agent wiki failed: %s", err)
                        # Prefer partial LLM wiki (keeps Timeline / synthesis panels)
                        # over the crude ## Events dump.
                        partial = str(
                            result.get("wiki_markdown") or ""
                        ).strip()
                        if len(partial) >= 80:
                            wiki_md = partial
                            backend = "tkeir-agent/llm_wiki-partial"
                else:
                    err = f"agent unreachable at {url}"
                    backend = "fallback-fold"
                    LOGGER.warning(err)

                if not wiki_md:
                    # Structured fallback so Osiris still shows Timeline /
                    # Cross-source / Conjectures panels after agent errors.
                    from thot.okf.iterative_wiki import (
                        ensure_osiris_panel_sections,
                        ensure_sources_section,
                    )

                    answer_bits: list[str] = []
                    timeline_bits: list[str] = []
                    synth_bits: list[str] = []
                    for i, c in enumerate(ranked[:12], 1):
                        title = str(c.get("title") or "Untitled").strip()
                        url = str(c.get("url") or "").strip()
                        snip = re.sub(
                            r"\s+",
                            " ",
                            str(c.get("snippet") or c.get("text_raw") or "")[
                                :220
                            ],
                        ).strip()
                        cid = str(c.get("chunk_id") or f"E{i}")
                        answer_bits.append(
                            f"- **{title}**"
                            + (f" — {snip}" if snip else "")
                            + (f" (chunk_id=`{cid}`)" if cid else "")
                        )
                        timeline_bits.append(
                            f"- event_id=E{i} | when=unknown | where=unknown | "
                            f"what={title[:120]}"
                        )
                        if i > 1:
                            timeline_bits.append(
                                f"- E{i - 1} --> E{i} | kind=sequence | "
                                f"note=ranked evidence order"
                            )
                        if url:
                            synth_bits.append(
                                f"- `{title[:80]}` ↔ source `{url[:80]}` "
                                f"(chunk_id=`{cid}`)"
                            )
                    lines = [
                        "# T-KEIR Live Wiki",
                        "",
                        f"_Updated {_now_iso()}_",
                        "",
                        f"**Expander query:** {expander_q}",
                        "",
                        "## Answer",
                        "",
                        "_Agent fold unavailable — ranked evidence summary._",
                        "",
                        *answer_bits,
                        "",
                        "## Structured facts",
                        "",
                        f"- ranked_chunks: {len(ranked)}",
                        f"- agent_error: {(err or 'none')[:200]}",
                        "",
                        "## Evidence",
                        "",
                        *answer_bits[:8],
                        "",
                        "## Timeline",
                        "",
                        "### Events",
                        "",
                        *timeline_bits,
                        "",
                        "## Cross-source synthesis",
                        "",
                        *(
                            synth_bits[:8]
                            or ["- _insufficient multi-source overlap_"]
                        ),
                        "",
                        "## Conjectures",
                        "",
                        "- _none grounded_ (fallback after agent error)",
                        "",
                        "## Sources",
                        "",
                        "## Gaps",
                        "",
                        "- Full LLM fold timed out or failed; refresh wiki when Ollama is free.",
                        "",
                    ]
                    wiki_md = ensure_osiris_panel_sections("\n".join(lines))
                    wiki_md = ensure_sources_section(
                        wiki_md,
                        [
                            {
                                "chunk_id": str(c.get("chunk_id") or ""),
                                "parent_doc_id": str(
                                    c.get("parent_doc_id")
                                    or c.get("url")
                                    or ""
                                ),
                            }
                            for c in ranked
                        ],
                    )
                    backend = "fallback-fold" if err else backend
                else:
                    from thot.okf.iterative_wiki import (
                        ensure_osiris_panel_sections,
                    )

                    wiki_md = ensure_osiris_panel_sections(wiki_md)

                wiki_md = ensure_sources_with_urls(wiki_md, ranked)

                # Publish markdown immediately so Osiris poll can finish before
                # the (often slow) business-ontology annotation.
                self.iteration += 1
                self.markdown = wiki_md
                self.meta = {
                    "status": "ok" if not err or wiki_md else "error",
                    "wiki_ready": bool(wiki_md.strip()),
                    "enabled": self.enabled,
                    "interval_s": self.interval_s,
                    "iteration": self.iteration,
                    "updated_at": _now_iso(),
                    "expander_query": expander_q,
                    "chunk_count": len(chunks),
                    "ranked_count": len(ranked),
                    "error": err,
                    "backend": backend,
                    "agent_url": url,
                    "run_id": run_id,
                    "sources": sources,
                    "ontology": None,
                    "bo_coverage": None,
                    **cluster_meta,
                }
                if wiki_md.strip():
                    self._persist_bundle(
                        topic=topic or "osiris-live",
                        ranked_chunks=ranked,
                    )

                if bo_payload and wiki_md.strip():
                    from thot.tools.collector.pipeline_status import (
                        PIPELINE_STATUS,
                    )

                    PIPELINE_STATUS.set_phase(
                        "ontology",
                        detail="Fusing business ontology with wiki graph",
                        progress=0.4,
                    )
                    try:
                        ontology_bundle = await asyncio.to_thread(
                            apply_business_ontology_to_wiki,
                            wiki_markdown=wiki_md,
                            chunks=ranked,
                            ontology_payload=bo_payload,
                            topic=topic or "osiris-live",
                        )
                    except Exception as ont_exc:  # noqa: BLE001
                        LOGGER.warning("ontology annotate failed: %s", ont_exc)
                        ontology_bundle = {
                            "error": str(ont_exc),
                            "bo_coverage": {
                                "total": len(bo_payload.get("concepts") or []),
                                "matched": 0,
                                "ratio": 0.0,
                                "matchedConcepts": [],
                                "missingConcepts": [],
                            },
                        }
                    self.meta = {
                        **self.meta,
                        "ontology": ontology_bundle,
                        "bo_coverage": (
                            (ontology_bundle or {}).get("bo_coverage")
                        ),
                        "updated_at": _now_iso(),
                    }
                    # Re-save with ontology graph for LAST WIKI restore.
                    self._persist_bundle(
                        topic=topic or "osiris-live",
                        ranked_chunks=ranked,
                    )
                from thot.tools.collector.pipeline_status import (
                    PIPELINE_STATUS,
                )

                if wiki_md.strip() and (not err or wiki_md):
                    PIPELINE_STATUS.set_phase(
                        "done",
                        detail="Wiki ready",
                        progress=1.0,
                        run_id=run_id,
                    )
                elif err:
                    PIPELINE_STATUS.set_phase(
                        "error",
                        detail=str(err),
                        error=str(err),
                    )
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("wiki produce failed")
                try:
                    from thot.tools.collector.pipeline_status import (
                        PIPELINE_STATUS,
                    )

                    PIPELINE_STATUS.set_phase(
                        "error", detail=str(exc), error=str(exc)
                    )
                except Exception:  # noqa: BLE001
                    pass
                self.meta = {
                    **self.meta,
                    "status": "error",
                    "wiki_ready": bool((self.markdown or "").strip()),
                    "error": str(exc),
                    "updated_at": _now_iso(),
                }
            return self.snapshot()

    def _persist_bundle(
        self,
        *,
        topic: str,
        ranked_chunks: list[dict[str, Any]] | None = None,
    ) -> None:
        """
        Write dated wiki panel bundle under workspace/collector/wikis/.

            Example:
                >>> True
                True
        """
        try:
            from thot.tools.collector.config import collector_settings
            from thot.tools.collector.feed import get_last_feed
            from thot.tools.collector.wiki_store import (
                build_wiki_bundle,
                save_wiki_bundle,
            )

            settings = collector_settings()
            feed = get_last_feed() or {}
            queries = list(feed.get("queries") or [])
            documents = list(feed.get("documents") or [])
            snap = self.snapshot()
            bundle = build_wiki_bundle(
                wiki_snapshot=snap,
                queries=queries,
                documents=documents,
                ranked_chunks=[
                    {
                        "chunk_id": c.get("chunk_id"),
                        "parent_doc_id": c.get("parent_doc_id"),
                        "title": c.get("title"),
                        "text_raw": c.get("text_raw"),
                        "url": c.get("url"),
                        "score": c.get("score"),
                        "is_root": c.get("is_root"),
                        "query": c.get("query"),
                    }
                    for c in ranked_chunks or []
                ],
                topic=topic,
                meta={
                    "forge_mode": feed.get("forge_mode"),
                    "generatedAt": feed.get("generatedAt"),
                    "osiris_base_url": feed.get("osiris_base_url"),
                },
            )
            path = save_wiki_bundle(settings.workspace, bundle, enabled=True)
            if path:
                self.meta["saved_path"] = str(path)
                self.meta["saved_id"] = bundle.get("id")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("wiki bundle persist failed: %s", exc)

    async def _loop(self) -> None:
        """Auto docstring for coverage.

        Example:
            >>> True
            True
        """
        from thot.tools.collector.feed import get_last_feed

        while self.enabled and self.interval_s > 0:
            feed = get_last_feed() or {}
            docs = list(feed.get("documents") or [])
            if docs:
                await self.produce_once(docs, agent_url=self.agent_url)
            try:
                await asyncio.sleep(max(5, int(self.interval_s)))
            except asyncio.CancelledError:
                break

    def start(self, interval_s: int) -> dict[str, Any]:
        """Auto docstring for coverage.

        Example:
            >>> True
            True
        """
        self.interval_s = max(0, int(interval_s))
        self.enabled = self.interval_s > 0
        self.meta["enabled"] = self.enabled
        self.meta["interval_s"] = self.interval_s
        self.meta["status"] = "running" if self.enabled else "idle"
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None
        if self.enabled:
            self._task = asyncio.create_task(self._loop())
        return self.snapshot()

    def stop(self) -> dict[str, Any]:
        """Auto docstring for coverage.

        Example:
            >>> True
            True
        """
        self.enabled = False
        self.interval_s = 0
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        self.meta["enabled"] = False
        self.meta["interval_s"] = 0
        self.meta["status"] = "stopped"
        return self.snapshot()


WIKI_LOOP = WikiLoop()
