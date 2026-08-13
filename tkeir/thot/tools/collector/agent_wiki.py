"""Title: Call tkeir-agent to build a live wiki from golden chunks.

Default wiki path: ranked golden chunks → ``POST /agent/runs`` (``llm_wiki``)
→ poll until ``wiki_markdown`` — sources always retained.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)


async def agent_ready(base_url: str, *, timeout_s: float = 3.0) -> bool:
    """
    True when agent ``/health`` (or ``/ready``) answers OK.

        Example:
            >>> True
            True
    """
    base = base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            for path in ("/ready", "/health", "/"):
                try:
                    res = await client.get(f"{base}{path}")
                    if res.status_code < 500:
                        return True
                except Exception:  # noqa: BLE001
                    continue
    except Exception:  # noqa: BLE001
        return False
    return False


async def run_llm_wiki(
    *,
    agent_url: str,
    goal: str,
    chunks: list[dict[str, Any]],
    topic: str = "osiris-live",
    max_wiki_chunks: int = 10,
    poll_seconds: float = 3.0,
    poll_attempts: int = 400,
    timeout_s: float = 60.0,
    wiki_agent: str = "osiris_wiki_prompt",
    timeline_agent: str = "osiris_timeline_prompt",
    max_chunk_chars: int = 2800,
    max_wiki_chars: int = 14000,
    wiki_fold: str = "cluster",
    cluster_similarity: float = 0.55,
    max_clusters: int = 6,
    per_cluster_for_llm: int = 3,
    prompt_char_budget: int = 14000,
    max_fold_calls: int = 3,
    clusters: list[list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """
    Start ``llm_wiki`` workflow and wait for ``wiki_markdown``.

        Clustering is **agglomerative (BGE-M3)** and should be done by the
        collector. Pass ``clusters`` when already computed; the agent only runs
        one LLM fold call per cluster (+ optional timeline persona).

        Returns:
            ``{ok, wiki_markdown, run_id, status, error?, chunks, clusters?}``

        Example:
            >>> True
            True
    """
    base = agent_url.rstrip("/")
    fold = (wiki_fold or "cluster").strip().lower()
    # Clustering (BGE-M3 agglomerative + near-centroid) runs on the wiki agent.
    # Collector only sends golden chunks unless it already preclustered.
    body = {
        "workflow": "llm_wiki",
        "goal": (
            goal.strip()
            or "Build a dated OSINT wiki (agglomerative near-centroid fold) + arrow timeline"
        ),
        "params": {
            "topic": topic,
            "query": goal,
            "chunks": chunks,
            "clusters": clusters or [],
            "preclustered": bool(clusters),
            "max_wiki_chunks": max(1, min(int(max_wiki_chunks), 48)),
            "max_chunk_chars": max(800, int(max_chunk_chars)),
            "max_wiki_chars": max(4000, int(max_wiki_chars)),
            "use_wiki": True,
            "stop_at_wiki_extract": True,
            "wiki_agent": wiki_agent,
            "prompt_name": wiki_agent,
            "timeline_agent": timeline_agent,
            "wiki_fold": fold,
            "wiki_mode": fold,
            "cluster_similarity": float(cluster_similarity),
            "max_clusters": max(1, min(int(max_clusters), 12)),
            "per_cluster_for_llm": max(2, min(6, int(per_cluster_for_llm))),
            "prompt_char_budget": max(
                6000, min(32000, int(prompt_char_budget))
            ),
            "max_fold_calls": max(1, min(6, int(max_fold_calls))),
        },
    }
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_s, read=timeout_s)
    ) as client:
        res = await client.post(f"{base}/agent/runs", json=body)
        if res.status_code >= 400:
            return {
                "ok": False,
                "error": f"agent HTTP {res.status_code}: {res.text[:300]}",
                "wiki_markdown": "",
                "run_id": None,
                "status": "failed",
                "chunks": chunks,
            }
        created = res.json()
        run_id = str(created.get("run_id") or "")
        if not run_id:
            return {
                "ok": False,
                "error": "agent returned no run_id",
                "wiki_markdown": "",
                "run_id": None,
                "status": "failed",
                "chunks": chunks,
            }

        last: dict[str, Any] = {}
        for _ in range(max(1, poll_attempts)):
            await asyncio.sleep(poll_seconds)
            snap = await client.get(f"{base}/agent/runs/{run_id}")
            if snap.status_code >= 400:
                continue
            last = snap.json()
            run = last.get("run") or last
            status = str(run.get("status") or "")
            if status in {
                "succeeded",
                "failed",
                "blocked",
                "killed",
                "cancelled",
            }:
                break

        run = last.get("run") or last
        status = str(run.get("status") or "unknown")
        params = run.get("params") or {}
        result = run.get("result") or last.get("compose_result") or {}
        wiki = str(
            params.get("wiki_markdown")
            or params.get("wiki_extract")
            or params.get("wiki_excerpt")
            or (
                result.get("wiki_markdown") if isinstance(result, dict) else ""
            )
            or ""
        ).strip()
        # Blackboard may carry a path-only entry; prefer params wiki text.
        if not wiki:
            for entry in last.get("blackboard") or []:
                if not isinstance(entry, dict):
                    continue
                md = entry.get("wiki_markdown") or entry.get("markdown")
                if isinstance(md, str) and md.strip():
                    wiki = md.strip()
                    break
        # Accept partial salvaged wikis (status may be succeeded with wiki_partial,
        # or failed with mid-fold markdown still present).
        if wiki and (
            status == "succeeded"
            or str(params.get("wiki_partial") or "").lower()
            in {"1", "true", "yes"}
            or len(wiki) >= 80
        ):
            return {
                "ok": (
                    status == "succeeded"
                    or str(params.get("wiki_partial") or "").lower()
                    in {"1", "true", "yes"}
                ),
                "wiki_markdown": wiki,
                "run_id": run_id,
                "status": status,
                "chunks": chunks,
                "clusters": clusters or [],
                "error": (
                    None
                    if status == "succeeded"
                    else str(run.get("error") or f"agent status={status}")
                ),
            }
        return {
            "ok": False,
            "error": str(run.get("error") or f"agent status={status}"),
            "wiki_markdown": wiki,
            "run_id": run_id,
            "status": status,
            "chunks": chunks,
            "clusters": clusters or [],
        }
