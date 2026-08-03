"""Title: Publish

Publish agent-generated content (approval-gated re-ingest staging).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import os
from typing import Any

from thot.action.models import new_action_id, utc_now_rfc3339
from thot.agent.models import RunState
from thot.agent.runs import RunStore
from thot.governor.approvals import ApprovalQueue

ORIGIN_AGENT_GENERATED = "agent-generated"


def _observe_auto_publish_enabled() -> bool:
    """Return whether observe mode may auto-approve publish staging.

    Reads ``AGENT_PUBLISH_OBSERVE_AUTO`` (default enabled unless ``0``/``false``).

    Returns:
        ``True`` when observe-mode auto publish is allowed.

    Example:
        >>> from thot.agent.publish import _observe_auto_publish_enabled
        >>> isinstance(_observe_auto_publish_enabled(), bool)
        True
    """
    return os.getenv("AGENT_PUBLISH_OBSERVE_AUTO", "1") not in {
        "0",
        "false",
        "False",
    }


def _approval_matches_run(item: Any, state: RunState) -> bool:
    """True when an approval item targets this run's publish intent.

    Args:
        item: :class:`~thot.governor.models.ApprovalItem` from the queue.
        state: Run whose ``correlation_id`` and ``run_id`` must match.

    Returns:
        ``True`` when correlation, intent, and run id align.

    Example:
        >>> from thot.agent.publish import _approval_matches_run
        >>> from thot.agent.models import RunState
        >>> from thot.governor.models import ApprovalItem
        >>> state = RunState(goal="g", correlation_id="c" * 32)
        >>> item = ApprovalItem(
        ...     approval_id="a1",
        ...     correlation_id="c" * 32,
        ...     actor_id="alice",
        ...     intent="generate",
        ...     reason=f"publish agent-generated run_id={state.run_id}",
        ...     created_at="2026-01-01T00:00:00Z",
        ... )
        >>> _approval_matches_run(item, state)
        True
    """
    return (
        item.correlation_id == state.correlation_id
        and item.intent in {"generate", "agent.publish"}
        and state.run_id in (item.reason or "")
    )


def _resolve_approval_by_id(
    guard_approvals: ApprovalQueue,
    approval_id: str,
    state: RunState,
) -> tuple[Any | None, dict[str, Any] | None]:
    """Look up an approval by id and validate status/correlation.

    Args:
        guard_approvals: Governor approval queue backing store.
        approval_id: Explicit approval id from the publish request.
        state: Run whose correlation id must match when present on the item.

    Returns:
        ``(approved_item, None)`` on success, or ``(None, error_dict)``.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.agent.publish import _resolve_approval_by_id
        >>> from thot.agent.models import RunState
        >>> from thot.governor.approvals import ApprovalQueue
        >>> with tempfile.TemporaryDirectory() as td:
        ...     q = ApprovalQueue(Path(td) / "approvals.json")
        ...     state = RunState(goal="g", correlation_id="c" * 32)
        ...     item, err = _resolve_approval_by_id(q, "missing", state)
        ...     item is None and err["status"] == "rejected"
        True
    """
    approved = guard_approvals.get(approval_id)
    if approved is None:
        return None, {"status": "rejected", "error": "unknown approval_id"}
    if approved.status != "approved":
        return None, {
            "status": "awaiting_approval",
            "approval_id": approved.approval_id,
            "approval_status": approved.status,
        }
    if (
        approved.correlation_id
        and state.correlation_id
        and approved.correlation_id != state.correlation_id
    ):
        return None, {
            "status": "rejected",
            "error": "approval correlation_id mismatch",
        }
    return approved, None


def _find_existing_approval(
    guard_approvals: ApprovalQueue,
    state: RunState,
    mode: str,
) -> tuple[Any | None, dict[str, Any] | None]:
    """Scan the queue for an existing publish approval for this run.

    Args:
        guard_approvals: Governor approval queue.
        state: Run used to match correlation id and run id in reasons.
        mode: Governor mode (``enforce`` blocks on pending items).

    Returns:
        ``(approved_item, None)``, ``(None, awaiting_dict)``, or ``(None, None)``.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.agent.publish import _find_existing_approval
        >>> from thot.agent.models import RunState
        >>> from thot.governor.approvals import ApprovalQueue
        >>> with tempfile.TemporaryDirectory() as td:
        ...     q = ApprovalQueue(Path(td) / "approvals.json")
        ...     state = RunState(goal="g", correlation_id="c" * 32)
        ...     item, err = _find_existing_approval(q, state, "observe")
        ...     item is None and err is None
        True
    """
    for item in guard_approvals.list_all(limit=500):
        if not _approval_matches_run(item, state):
            continue
        if item.status == "approved":
            return item, None
        if item.status == "pending" and mode == "enforce":
            return None, {
                "status": "awaiting_approval",
                "approval_id": item.approval_id,
                "approval_status": "pending",
            }
    return None, None


def _resolve_or_enqueue_approval(
    guard_approvals: ApprovalQueue,
    state: RunState,
    mode: str,
) -> tuple[Any, dict[str, Any] | None]:
    """Enqueue a publish approval and optionally auto-approve in observe mode.

    Args:
        guard_approvals: Governor approval queue.
        state: Run whose correlation id and user space are recorded.
        mode: Governor mode controlling enforce vs observe behavior.

    Returns:
        Tuple of approval item and optional awaiting-approval response dict.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.agent.publish import _resolve_or_enqueue_approval
        >>> from thot.agent.models import RunState
        >>> from thot.governor.approvals import ApprovalQueue
        >>> with tempfile.TemporaryDirectory() as td:
        ...     q = ApprovalQueue(Path(td) / "approvals.json")
        ...     state = RunState(goal="g", correlation_id="c" * 32, user_space="alice")
        ...     item, err = _resolve_or_enqueue_approval(q, state, "enforce")
        ...     err["status"]
        'awaiting_approval'
    """
    item = guard_approvals.enqueue(
        correlation_id=state.correlation_id or ("0" * 32),
        actor_id=state.user_space,
        intent="generate",
        reason=f"publish agent-generated run_id={state.run_id}",
    )
    if mode == "enforce":
        return item, {
            "status": "awaiting_approval",
            "approval_id": item.approval_id,
            "approval_status": "pending",
        }
    if not _observe_auto_publish_enabled():
        return item, {
            "status": "awaiting_approval",
            "approval_id": item.approval_id,
            "approval_status": "pending",
        }
    return guard_approvals.decide(item.approval_id, status="approved"), None


def _write_publish_artifacts(
    store: RunStore,
    state: RunState,
    markdown: str,
    approved: Any,
) -> dict[str, Any]:
    """Write markdown + manifest under ``publishes/{run_id}/`` and blackboard.

    Args:
        store: Run store receiving blackboard publish events.
        state: Succeeded run being staged for re-ingest.
        markdown: Deliverable body written to ``document.md``.
        approved: Approved :class:`~thot.governor.models.ApprovalItem`.

    Returns:
        Published status dict with paths, ids, and ``source_uri``.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.agent.publish import _write_publish_artifacts, ORIGIN_AGENT_GENERATED
        >>> from thot.agent.models import RunState
        >>> from thot.agent.runs import RunStore
        >>> from thot.governor.approvals import ApprovalQueue
        >>> with tempfile.TemporaryDirectory() as td:
        ...     root = Path(td)
        ...     store = RunStore(root)
        ...     store.ensure_layout()
        ...     approvals = ApprovalQueue(root / "approvals.json")
        ...     state = RunState(goal="g", correlation_id="c" * 32, user_space="alice")
        ...     approved = approvals.enqueue(
        ...         correlation_id=state.correlation_id,
        ...         actor_id=state.user_space,
        ...         intent="generate",
        ...         reason=f"publish agent-generated run_id={state.run_id}",
        ...     )
        ...     approved = approvals.decide(approved.approval_id, status="approved")
        ...     out = _write_publish_artifacts(store, state, "# doc\\n", approved)
        ...     out["status"] == "published" and out["origin"] == ORIGIN_AGENT_GENERATED
        True
    """
    publish_id = new_action_id()
    out_dir = store.root / "publishes" / state.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "document.md"
    md_path.write_text(markdown, encoding="utf-8")
    manifest = {
        "schema": "tkeir.agent.publish.v1",
        "publish_id": publish_id,
        "run_id": state.run_id,
        "origin": ORIGIN_AGENT_GENERATED,
        "user_space": state.user_space,
        "correlation_id": state.correlation_id,
        "approval_id": approved.approval_id,
        "markdown_path": str(md_path),
        "source_uri": md_path.resolve().as_uri(),
        "created_at": utc_now_rfc3339(),
        "ingest": {
            "origin": ORIGIN_AGENT_GENERATED,
            "run_id": state.run_id,
            "note": (
                "Re-ingest via POST /ingest/document with this file URI; "
                "manifest origin/run_id must be preserved by the indexer."
            ),
        },
    }
    manifest_path = out_dir / "publish.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    store.append_blackboard(
        state.run_id,
        {
            "kind": "publish",
            "publish_id": publish_id,
            "origin": ORIGIN_AGENT_GENERATED,
            "approval_id": approved.approval_id,
            "path": str(md_path),
        },
    )
    return {
        "status": "published",
        "publish_id": publish_id,
        "origin": ORIGIN_AGENT_GENERATED,
        "run_id": state.run_id,
        "approval_id": approved.approval_id,
        "markdown_path": str(md_path),
        "manifest_path": str(manifest_path),
        "source_uri": manifest["source_uri"],
    }


def _markdown_from_state(state: RunState) -> str:
    """Build publish markdown from compose result or grounded findings.

    Args:
        state: Run with ``compose_result.markdown`` or ``result`` findings.

    Returns:
        Markdown string, or empty when no deliverable is available.

    Example:
        >>> from thot.agent.publish import _markdown_from_state
        >>> from thot.agent.models import RunState, GroundedFindings, GroundedFinding
        >>> state = RunState(
        ...     goal="summarize",
        ...     result=GroundedFindings(
        ...         findings=[GroundedFinding(claim="fact", chunk_ids=["c1"])]
        ...     ),
        ... )
        >>> "# Agent findings" in _markdown_from_state(state)
        True
    """
    if state.compose_result and isinstance(state.compose_result, dict):
        md = state.compose_result.get("markdown")
        if isinstance(md, str) and md.strip():
            return md
    if state.result is not None:
        lines = [f"# Agent findings: {state.goal}", ""]
        for finding in state.result.findings:
            cites = ", ".join(finding.chunk_ids) or "(no chunks)"
            lines.append(f"- {finding.claim}  \n  citations: `{cites}`")
        if state.result.unfilled:
            lines.extend(["", "## Unfilled", ""])
            for item in state.result.unfilled:
                lines.append(f"- {item}")
        return "\n".join(lines) + "\n"
    return ""


def publish_run(
    *,
    store: RunStore,
    guard_approvals: ApprovalQueue,
    state: RunState,
    approval_id: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """Stage an agent deliverable for publication (approval-gated).

    In ``enforce`` mode an approved ApprovalQueue item is required. Observe
    mode still enqueues an approval for auditability but may stage immediately
    when ``AGENT_PUBLISH_OBSERVE_AUTO=1``.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.agent.models import RunState, GroundedFindings, GroundedFinding
        >>> from thot.agent.runs import RunStore
        >>> from thot.agent.publish import publish_run, ORIGIN_AGENT_GENERATED
        >>> from thot.governor.approvals import ApprovalQueue
        >>> with tempfile.TemporaryDirectory() as td:
        ...     root = Path(td)
        ...     store = RunStore(root)
        ...     store.ensure_layout()
        ...     approvals = ApprovalQueue(root / "approvals.json")
        ...     state = RunState(
        ...         goal="g",
        ...         user_space="alice",
        ...         correlation_id="c" * 32,
        ...         status="succeeded",
        ...         result=GroundedFindings(
        ...             findings=[GroundedFinding(claim="x", chunk_ids=["c1"])]
        ...         ),
        ...     )
        ...     _ = store.write_state(state)
        ...     first = publish_run(
        ...         store=store, guard_approvals=approvals, state=state, mode="enforce",
        ...     )
        ...     first["status"]
        'awaiting_approval'
    """
    mode = (mode or os.getenv("GOVERNOR_MODE") or "observe").lower()
    if state.status != "succeeded":
        return {
            "status": "rejected",
            "error": f"run status must be succeeded (got {state.status})",
        }
    markdown = _markdown_from_state(state)
    if not markdown.strip():
        return {
            "status": "rejected",
            "error": "no markdown/deliverable to publish",
        }

    approved = None
    if approval_id:
        approved, error = _resolve_approval_by_id(
            guard_approvals, approval_id, state
        )
        if error is not None:
            return error

    if approved is None:
        approved, error = _find_existing_approval(guard_approvals, state, mode)
        if error is not None:
            return error

    if approved is None:
        approved, error = _resolve_or_enqueue_approval(
            guard_approvals, state, mode
        )
        if error is not None:
            return error

    assert approved is not None
    return _write_publish_artifacts(store, state, markdown, approved)
