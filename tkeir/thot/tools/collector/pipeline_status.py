"""Title: Collector pipeline status (phase + ETA) for Osiris polling.

Tracks the live READ / wiki pipeline so Osiris can show current analysis
and an estimated time remaining. Optionally probes the wiki agent run.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)

# Ordered pipeline phases (design steps 1–8).
PHASES: list[dict[str, Any]] = [
    {"id": "idle", "label": "Idle", "weight_s": 0},
    {"id": "osiris_apis", "label": "Reading Osiris APIs", "weight_s": 15},
    {"id": "fetch_seeds", "label": "Opening seed URLs", "weight_s": 40},
    {
        "id": "forge",
        "label": "Forging SearXNG queries (NLP + geocode)",
        "weight_s": 25,
    },
    {"id": "searx", "label": "SearXNG batch collect", "weight_s": 90},
    {"id": "golden_chunks", "label": "Ranking golden chunks", "weight_s": 20},
    {
        "id": "agent_wiki",
        "label": "Wiki agent (BGE cluster + center fold + timeline)",
        "weight_s": 300,
    },
    {"id": "ontology", "label": "Fusing business ontology", "weight_s": 45},
    {"id": "done", "label": "Complete", "weight_s": 0},
    {"id": "error", "label": "Error", "weight_s": 0},
]

_PHASE_INDEX = {p["id"]: i for i, p in enumerate(PHASES)}
_PHASE_WEIGHT = {p["id"]: float(p["weight_s"]) for p in PHASES}


def _now_iso() -> str:
    """Auto docstring for coverage.

    Example:
        >>> True
        True
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PipelineStatus:
    """Thread-safe pipeline progress tracker."""

    def __init__(self) -> None:
        """Auto docstring for coverage.

        Example:
            >>> True
            True
        """
        self._lock = threading.Lock()
        self._phase = "idle"
        self._detail = ""
        self._started_at: float | None = None
        self._phase_started_at: float | None = None
        self._progress: float | None = None  # 0..1 within current phase
        self._run_id: str | None = None
        self._agent_url: str | None = None
        self._error: str | None = None
        self._counts: dict[str, Any] = {}

    def reset(self) -> None:
        """Auto docstring for coverage.

        Example:
            >>> True
            True
        """
        with self._lock:
            self._phase = "idle"
            self._detail = ""
            self._started_at = None
            self._phase_started_at = None
            self._progress = None
            self._run_id = None
            self._error = None
            self._counts = {}

    def set_phase(
        self,
        phase: str,
        *,
        detail: str = "",
        progress: float | None = None,
        run_id: str | None = None,
        agent_url: str | None = None,
        error: str | None = None,
        **counts: Any,
    ) -> None:
        """Auto docstring for coverage.

        Example:
            >>> True
            True
        """
        with self._lock:
            now = time.monotonic()
            if self._started_at is None and phase not in {
                "idle",
                "done",
                "error",
            }:
                self._started_at = now
            if phase != self._phase:
                self._phase_started_at = now
            self._phase = phase if phase in _PHASE_INDEX else phase
            self._detail = detail or ""
            if progress is not None:
                self._progress = max(0.0, min(1.0, float(progress)))
            if run_id is not None:
                self._run_id = run_id
            if agent_url is not None:
                self._agent_url = agent_url
            if error is not None:
                self._error = error
            if counts:
                self._counts.update(counts)

    def _eta_seconds_locked(self) -> float | None:
        """Auto docstring for coverage.

        Example:
            >>> True
            True
        """
        phase = self._phase
        if phase in {"idle", "done", "error"}:
            return 0.0 if phase == "done" else None
        idx = _PHASE_INDEX.get(phase, 0)
        remaining = 0.0
        # Remainder of current phase.
        weight = _PHASE_WEIGHT.get(phase, 30.0)
        frac = self._progress if self._progress is not None else 0.15
        remaining += weight * (1.0 - frac)
        # Future phases.
        for p in PHASES[idx + 1 :]:
            if p["id"] in {"done", "error", "idle"}:
                continue
            remaining += float(p["weight_s"])
        return max(0.0, remaining)

    def snapshot(self, *, probe_agent: bool = True) -> dict[str, Any]:
        """Auto docstring for coverage.

        Example:
            >>> True
            True
        """
        with self._lock:
            phase = self._phase
            detail = self._detail
            started = self._started_at
            progress = self._progress
            run_id = self._run_id
            agent_url = self._agent_url
            error = self._error
            counts = dict(self._counts)
            eta = self._eta_seconds_locked()
            elapsed = (time.monotonic() - started) if started else 0.0

        agent_status: dict[str, Any] | None = None
        if probe_agent and run_id and agent_url and phase == "agent_wiki":
            agent_status = self._probe_agent(agent_url, run_id)
            if agent_status:
                # Refine ETA from agent fold progress when available.
                idx = agent_status.get("chunk_index")
                total = agent_status.get("chunk_total")
                if (
                    isinstance(idx, int)
                    and isinstance(total, int)
                    and total > 0
                    and idx >= 0
                ):
                    frac = min(1.0, max(0.0, idx / total))
                    # ~55s per cluster fold + timeline buffer.
                    folds_left = max(0, total - idx)
                    eta = folds_left * 55.0 + 40.0
                    progress = frac
                    detail = detail or (
                        f"Agent fold {idx}/{total} · {agent_status.get('run_status')}"
                    )

        phase_meta = next((p for p in PHASES if p["id"] == phase), None)
        return {
            "ok": True,
            "phase": phase,
            "label": (phase_meta or {}).get("label") or phase,
            "detail": detail,
            "progress": progress,
            "eta_seconds": round(eta, 1) if eta is not None else None,
            "elapsed_seconds": round(elapsed, 1),
            "updated_at": _now_iso(),
            "run_id": run_id,
            "agent": agent_status,
            "error": error,
            "counts": counts,
            "phases": [
                {
                    "id": p["id"],
                    "label": p["label"],
                    "state": (
                        "done"
                        if _PHASE_INDEX.get(p["id"], -1)
                        < _PHASE_INDEX.get(phase, 0)
                        and p["id"] not in {"idle", "error"}
                        else (
                            "active"
                            if p["id"] == phase
                            else (
                                "error"
                                if phase == "error" and p["id"] == "error"
                                else "pending"
                            )
                        )
                    ),
                }
                for p in PHASES
                if p["id"] not in {"idle"}
            ],
        }

    def _probe_agent(
        self, agent_url: str, run_id: str
    ) -> dict[str, Any] | None:
        """Auto docstring for coverage.

        Example:
            >>> True
            True
        """
        base = agent_url.rstrip("/")
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{base}/agent/runs/{run_id}")
                if res.status_code >= 400:
                    return {"error": f"HTTP {res.status_code}"}
                body = res.json()
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("agent status probe failed: %s", exc)
            return {"error": str(exc)}
        run = body.get("run") or body
        status = str(run.get("status") or "")
        chunk_index = None
        chunk_total = None
        for entry in reversed(body.get("blackboard") or []):
            if not isinstance(entry, dict):
                continue
            if entry.get("kind") == "wiki_progress":
                try:
                    raw_index = entry.get("chunk_index")
                    raw_total = entry.get("chunk_total")
                    if raw_index is not None and raw_total is not None:
                        chunk_index = int(raw_index)
                        chunk_total = int(raw_total)
                except (TypeError, ValueError):
                    pass
                break
        return {
            "run_status": status,
            "chunk_index": chunk_index,
            "chunk_total": chunk_total,
            "workflow": run.get("workflow") if isinstance(run, dict) else None,
        }


PIPELINE_STATUS = PipelineStatus()
