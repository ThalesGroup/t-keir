"""Title: LLM-Wiki specialized workflow (domain layer on the agent framework).

Wiki match / upsert / iterative fold live here — not inside
:class:`~thot.agent.llm_agent.LLMAgent` or the core loop. The orchestrator
delegates builtin ``wiki_upsert`` / ``okf_iterative_wiki`` to this module.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from thot.action.models import utc_now_rfc3339
from thot.agent.guard import AgentGuard
from thot.agent.loop import LlmClient
from thot.agent.models import GroundedFinding, GroundedFindings, RunState
from thot.agent.runs import RunStore

LOGGER = logging.getLogger(__name__)


def _format_exc(exc: BaseException) -> str:
    """Format an exception for run ``error`` fields.

    Example:
        >>> from thot.agent.workflows.wiki_generator import _format_exc
        >>> _format_exc(ValueError("x"))
        'ValueError: x'
    """
    name = type(exc).__name__
    msg = str(exc).strip()
    return f"{name}: {msg}" if msg else name


def _truthy(value: Any) -> bool:
    """Normalize truthy params (bool / ``1`` / ``true`` / ``yes`` / ``on``).

    Example:
        >>> from thot.agent.workflows.wiki_generator import _truthy
        >>> _truthy("yes")
        True
    """
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


class WikiGeneratorWorkflow:
    """Domain workflow: match/create OKF wiki and update via LLM.

    Uses the shared run store + :class:`AgentGuard` for audit/SPIFFE; does not
    embed ReAct tool loops (those stay on :class:`~thot.agent.llm_agent.LLMAgent`).

    Example:
        >>> import inspect
        >>> from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow
        >>> inspect.iscoroutinefunction(WikiGeneratorWorkflow.generate_wiki)
        True
    """

    def __init__(
        self,
        *,
        store: RunStore,
        guard: AgentGuard,
        llm: LlmClient,
    ) -> None:
        """Bind run store, guard, and LLM client.

        Example:
            >>> from unittest.mock import MagicMock
            >>> from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow
            >>> w = WikiGeneratorWorkflow(
            ...     store=MagicMock(), guard=MagicMock(), llm=MagicMock()
            ... )
            >>> w.store is not None
            True
        """
        self.store = store
        self.guard = guard
        self.llm = llm

    def _fail(self, state: RunState, *, error: str) -> RunState:
        """Mark ``state`` failed, persist it, and return it.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from unittest.mock import MagicMock
            >>> from thot.agent.models import RunState
            >>> from thot.agent.runs import RunStore
            >>> from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     w = WikiGeneratorWorkflow(
            ...         store=store, guard=MagicMock(), llm=MagicMock()
            ...     )
            ...     st = RunState(goal="g", user_space="u@tkeir", run_id="r1")
            ...     _ = store.write_state(st)
            ...     w._fail(st, error="boom").status
            'failed'
        """
        state.status = "failed"
        state.error = error
        state.ended_at = utc_now_rfc3339()
        self.store.write_state(state)
        return state

    @staticmethod
    def bundle_root(user_space: str, bundle_id: str) -> Path | None:
        """Resolve OKF bundle directory for ``bundle_id``.

        Example:
            >>> from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow
            >>> WikiGeneratorWorkflow.bundle_root("dev@tkeir", "") is None
            True
        """
        # Lazy import: avoids okf.exporter ↔ agent circular import at package load.
        from thot.okf.exporter import default_okf_root, user_okf_root

        bid = (bundle_id or "").strip()
        if not bid:
            return None
        root = user_okf_root(user_space) / bid
        if root.is_dir():
            return root
        legacy = default_okf_root() / bid
        if legacy.is_dir():
            return legacy
        return None

    @staticmethod
    def wiki_chunks_for_bundle(
        params: dict[str, Any], root: Path
    ) -> list[dict[str, str]]:
        """Prefer HMI grab/search chunks; else load bundle evidence_chunks.json.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow
            >>> with tempfile.TemporaryDirectory() as td:
            ...     WikiGeneratorWorkflow.wiki_chunks_for_bundle({}, Path(td))
            []
        """
        from thot.okf.iterative_wiki import (
            chunks_from_params,
            load_evidence_chunks,
            write_evidence_chunks,
        )

        chunks = chunks_from_params(params)
        if chunks:
            write_evidence_chunks(root, chunks)
            return chunks
        return load_evidence_chunks(root)

    @staticmethod
    def seed_or_load_wiki(
        *,
        bundle_id: str,
        user_space: str,
        query: str,
        wiki_cfg: dict[str, Any],
        store: Any,
    ) -> str:
        """Return existing wiki or a persona/OKF seed skeleton.

        Example:
            >>> class _Store:
            ...     def get_wiki(self, *_a, **_k):
            ...         return "# Existing\\nbody"
            >>> from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow
            >>> WikiGeneratorWorkflow.seed_or_load_wiki(
            ...     bundle_id="b",
            ...     user_space="u",
            ...     query="q",
            ...     wiki_cfg={"structured_facts_seed": ""},
            ...     store=_Store(),
            ... ).startswith("# Existing")
            True
        """
        from thot.okf.iterative_wiki import seed_iterative_wiki

        try:
            initial = store.get_wiki(bundle_id, user_space) or ""
        except Exception:  # noqa: BLE001
            initial = ""
        if (
            not initial.strip()
            or "_OKF wiki" in initial
            or "_Iterative wiki" in initial
        ):
            return seed_iterative_wiki(
                query=query,
                structured_facts_seed=wiki_cfg["structured_facts_seed"],
            )
        return initial

    @staticmethod
    def findings_from_wiki_chunks(
        chunks: list[dict[str, str]],
        *,
        max_chunks: int,
        query: str,
        path: Any,
        prompt_name: str,
    ) -> GroundedFindings:
        """Build grounded findings stubs from wiki evidence chunks.

        Example:
            >>> from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow
            >>> out = WikiGeneratorWorkflow.findings_from_wiki_chunks(
            ...     [{"chunk_id": "c1", "text_raw": "fact", "parent_doc_id": "d1"}],
            ...     max_chunks=2,
            ...     query="q",
            ...     path="/tmp/w",
            ...     prompt_name="p",
            ... )
            >>> out.findings[0].claim
            'fact'
        """
        usable = [c for c in chunks if (c.get("text_raw") or "").strip()][
            :max_chunks
        ]
        findings = [
            GroundedFinding(
                claim=(c.get("text_raw") or "")[:400],
                chunk_ids=[str(c.get("chunk_id") or "")],
                document_ids=[str(c.get("parent_doc_id") or "")],
                confidence=0.5,
            )
            for c in usable
            if c.get("chunk_id")
        ]
        return GroundedFindings(
            goal=query,
            findings=findings,
            unfilled=(
                []
                if findings
                else ["no evidence chunks available for iterative wiki"]
            ),
            notes=f"okf_iterative_wiki path={path} prompt={prompt_name}",
        )

    @staticmethod
    def resolve_wiki_prompt_config(params: dict[str, Any]) -> dict[str, Any]:
        """Load persona ``*_prompt`` agent wiki seed/system from run params.

        Example:
            >>> from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow
            >>> WikiGeneratorWorkflow.resolve_wiki_prompt_config({})["prompt_name"]
            ''
        """
        from thot.agent.registry import load_agent_spec

        name = str(
            params.get("wiki_agent")
            or params.get("prompt_name")
            or params.get("wiki_prompt_agent")
            or ""
        ).strip()
        empty: dict[str, Any] = {
            "prompt_name": name,
            "structured_facts_seed": "",
            "merge_system": "",
            "priority_keys": [],
        }
        if not name:
            return empty
        try:
            spec = load_agent_spec(name)
        except FileNotFoundError:
            LOGGER.warning("wiki prompt agent not found: %s", name)
            return empty
        return {
            "prompt_name": name,
            "structured_facts_seed": (
                (spec.wiki_structured_facts_seed or "").strip()
            ),
            "merge_system": (spec.wiki_merge_system_prompt or "").strip(),
            "priority_keys": list(spec.wiki_information_priority_keys or []),
        }

    @staticmethod
    def _match_threshold(params: dict[str, Any]) -> float:
        """Parse wiki match threshold from params / env.

        Example:
            >>> from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow
            >>> WikiGeneratorWorkflow._match_threshold({"wiki_match_threshold": "0.2"})
            0.2
        """
        raw_threshold = params.get("wiki_match_threshold")
        if raw_threshold is None or raw_threshold == "":
            raw_threshold = os.getenv("WIKI_MATCH_THRESHOLD", "0.15")
        try:
            return float(raw_threshold)
        except (TypeError, ValueError):
            return 0.15

    def _resolve_wiki_bundle(
        self,
        state: RunState,
        *,
        params: dict[str, Any],
        query: str,
        wiki_cfg: dict[str, Any],
        okf: Any,
    ) -> tuple[str, Path, bool, Any] | RunState:
        """Match or create an OKF bundle for wiki upsert.

        Returns ``(bundle_id, root, created, match)`` or a failed ``RunState``.

        Example:
            >>> import inspect
            >>> from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow
            >>> inspect.isfunction(WikiGeneratorWorkflow._resolve_wiki_bundle)
            True
        """
        from thot.okf.iterative_wiki import create_evidence_bundle
        from thot.okf.wiki_match import find_closest_wiki

        threshold = self._match_threshold(params)
        match = find_closest_wiki(
            state.user_space, query, store=okf, threshold=threshold
        )
        created = False
        bundle_id = ""
        root: Path | None = None
        if match is not None:
            bundle_id = match.bundle_id
            root = self.bundle_root(state.user_space, bundle_id)
            if root is None:
                match = None
        if match is None:
            try:
                bundle_id, root = create_evidence_bundle(
                    user_space=state.user_space,
                    query=query or "wiki",
                    chunks=list(params.get("chunks") or [])[:8],
                    structured_facts_seed=wiki_cfg["structured_facts_seed"],
                )
            except Exception as exc:  # noqa: BLE001
                return self._fail(
                    state, error=f"wiki_upsert create: {_format_exc(exc)}"
                )
            created = True
        else:
            bundle_id = match.bundle_id
            root = Path(match.path)
        assert root is not None
        return bundle_id, root, created, match

    async def run_upsert(self, state: RunState) -> RunState:
        """Match closest user wiki or create; single-pass LLM upsert.

        Example:
            >>> await WikiGeneratorWorkflow(...).run_upsert(state)  # doctest: +SKIP
        """
        from thot.okf.iterative_wiki import build_wiki_upsert_pass
        from thot.okf.store import OkfBundleStore
        from thot.okf.wiki_match import extract_wiki_sections

        params = dict(state.params or {})
        if "use_wiki" in params and not _truthy(params.get("use_wiki")):
            state.params = {
                **params,
                "wiki_markdown": "",
                "wiki_excerpt": "",
                "wiki_extract": "",
                "has_llm_wiki": "false",
            }
            self.store.write_state(state)
            return state

        if not self.guard.check_action_permission(
            state, {"type": "wiki_upsert", "tool": "wiki_upsert"}
        ):
            return self._fail(
                state, error="wiki_upsert: blocked by AgentGuard"
            )

        query = str(
            params.get("query") or params.get("topic") or state.goal or ""
        ).strip()
        okf = OkfBundleStore()
        wiki_cfg = self.resolve_wiki_prompt_config(params)
        resolved = self._resolve_wiki_bundle(
            state, params=params, query=query, wiki_cfg=wiki_cfg, okf=okf
        )
        if isinstance(resolved, RunState):
            return resolved
        bundle_id, root, created, match = resolved

        chunks = self.wiki_chunks_for_bundle(params, root)
        current = okf.get_wiki(bundle_id, state.user_space) or ""
        # Situation reports need ample evidence — raise defaults + hard max.
        max_chunks = max(1, min(int(params.get("max_wiki_chunks") or 24), 48))
        try:
            max_chunk_chars = int(params.get("max_chunk_chars") or 2200)
        except (TypeError, ValueError):
            max_chunk_chars = 2200
        try:
            max_wiki_chars = int(params.get("max_wiki_chars") or 24000)
        except (TypeError, ValueError):
            max_wiki_chars = 24000
        # Persona prompts may request larger folds, but respect caller caps when
        # already set (collector lean budgets for local Ollama).
        if wiki_cfg.get("merge_system"):
            if "max_chunk_chars" not in params:
                max_chunk_chars = max(max_chunk_chars, 1600)
            if "max_wiki_chars" not in params:
                max_wiki_chars = max(max_wiki_chars, 14000)
        fold_mode = str(
            params.get("wiki_fold") or params.get("wiki_mode") or ""
        ).strip().lower()
        use_cluster = fold_mode in {"cluster", "bge", "agglomerative"}
        sequential = fold_mode in {"sequential", "iterative", "chunk"}
        try:
            cluster_sim = float(params.get("cluster_similarity") or 0.55)
        except (TypeError, ValueError):
            cluster_sim = 0.55
        try:
            max_clusters = int(params.get("max_clusters") or 8)
        except (TypeError, ValueError):
            max_clusters = 8
        try:
            per_cluster_llm = int(params.get("per_cluster_for_llm") or 5)
        except (TypeError, ValueError):
            per_cluster_llm = 5
        per_cluster_llm = max(2, min(6, per_cluster_llm))
        try:
            prompt_char_budget = int(params.get("prompt_char_budget") or 14000)
        except (TypeError, ValueError):
            prompt_char_budget = 14000
        prompt_char_budget = max(6000, min(32000, prompt_char_budget))
        try:
            max_fold_calls = int(params.get("max_fold_calls") or 3)
        except (TypeError, ValueError):
            max_fold_calls = 3
        max_fold_calls = max(1, min(6, max_fold_calls))
        try:
            if use_cluster or sequential:
                from thot.okf.iterative_wiki import build_wiki_iteratively

                LOGGER.info(
                    "wiki_upsert fold=%s chunks=%s clusters_cap=%s "
                    "per_cluster=%s packs_cap=%s budget_chars=%s "
                    "preclustered=%s",
                    "cluster" if use_cluster else "sequential",
                    max_chunks,
                    max_clusters,
                    per_cluster_llm,
                    max_fold_calls,
                    prompt_char_budget,
                    bool(params.get("clusters") or params.get("preclustered")),
                )

                def _progress(wiki_text: str, index: int, total: int) -> None:
                    try:
                        okf.put_wiki(bundle_id, state.user_space, wiki_text)
                    except Exception:  # noqa: BLE001
                        LOGGER.debug("mid-wiki put failed", exc_info=True)
                    self.store.append_blackboard(
                        state.run_id,
                        {
                            "kind": "wiki_progress",
                            "builtin": "wiki_upsert",
                            "bundle_id": bundle_id,
                            "chunk_index": index,
                            "chunk_total": total,
                            "wiki_chars": len(wiki_text),
                            "fold": "cluster" if use_cluster else "sequential",
                            "prompt_name": wiki_cfg["prompt_name"],
                            "provenance": "wiki_generator",
                        },
                    )
                    self.store.write_state(state)

                wiki = await build_wiki_iteratively(
                    llm=self.llm,
                    query=query,
                    chunks=chunks,
                    initial_wiki=current,
                    max_chunks=max_chunks,
                    on_progress=_progress,
                    system=wiki_cfg["merge_system"],
                    structured_facts_seed=wiki_cfg["structured_facts_seed"],
                    information_priority_keys=wiki_cfg["priority_keys"],
                    sequential=sequential and not use_cluster,
                    cluster=use_cluster,
                    cluster_similarity=cluster_sim,
                    max_clusters=max_clusters,
                    max_chunk_chars=max_chunk_chars,
                    max_wiki_chars=max_wiki_chars,
                    per_cluster_for_llm=per_cluster_llm,
                    prompt_char_budget=prompt_char_budget,
                    max_fold_calls=max_fold_calls,
                    prebuilt_clusters=(
                        list(params.get("clusters") or [])
                        if _truthy(params.get("preclustered"))
                        or bool(params.get("clusters"))
                        else None
                    ),
                )
            else:
                wiki = await build_wiki_upsert_pass(
                    llm=self.llm,
                    query=query,
                    chunks=chunks,
                    current_wiki=current,
                    max_chunks=max_chunks,
                    max_chunk_chars=max_chunk_chars,
                    max_wiki_chars=max_wiki_chars,
                    system=wiki_cfg["merge_system"],
                    structured_facts_seed=wiki_cfg["structured_facts_seed"],
                    information_priority_keys=wiki_cfg["priority_keys"],
                )

            # Optional second persona: arrow timeline from dated evidence.
            timeline_name = str(
                params.get("timeline_agent")
                or params.get("timeline_prompt")
                or ""
            ).strip()
            if timeline_name:
                from thot.okf.iterative_wiki import build_timeline_pass

                tl_cfg = self.resolve_wiki_prompt_config(
                    {"wiki_agent": timeline_name, "prompt_name": timeline_name}
                )
                LOGGER.info("wiki timeline pass agent=%s", timeline_name)
                try:
                    wiki = await build_timeline_pass(
                        llm=self.llm,
                        query=query,
                        chunks=chunks,
                        current_wiki=wiki,
                        system=tl_cfg.get("merge_system") or None,
                        information_priority_keys=tl_cfg.get("priority_keys")
                        or None,
                        max_chunk_chars=max(1200, max_chunk_chars // 2),
                        max_wiki_chars=max_wiki_chars,
                        max_chunks=max_chunks,
                    )
                    self.store.append_blackboard(
                        state.run_id,
                        {
                            "kind": "wiki_timeline",
                            "builtin": "wiki_upsert",
                            "bundle_id": bundle_id,
                            "timeline_agent": timeline_name,
                            "wiki_chars": len(wiki),
                            "provenance": "wiki_generator",
                        },
                    )
                except Exception as tl_exc:  # noqa: BLE001
                    # Keep Answer / Cross-source / Conjectures if timeline stalls.
                    LOGGER.warning(
                        "wiki timeline pass failed — keeping prior wiki: %s",
                        tl_exc,
                    )
                    self.store.append_blackboard(
                        state.run_id,
                        {
                            "kind": "wiki_timeline_error",
                            "builtin": "wiki_upsert",
                            "bundle_id": bundle_id,
                            "error": str(tl_exc),
                            "provenance": "wiki_generator",
                        },
                    )

            from thot.okf.iterative_wiki import ensure_osiris_panel_sections

            wiki = ensure_osiris_panel_sections(wiki)
            path = okf.put_wiki(bundle_id, state.user_space, wiki)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("wiki_upsert failed")
            # Salvage mid-fold wiki so Osiris keeps Timeline / synthesis panels.
            salvaged = ""
            try:
                salvaged = str(locals().get("wiki") or "").strip()
            except Exception:  # noqa: BLE001
                salvaged = ""
            if not salvaged and bundle_id:
                try:
                    salvaged = (okf.get_wiki(bundle_id, state.user_space) or "").strip()
                except Exception:  # noqa: BLE001
                    salvaged = ""
            if salvaged:
                from thot.okf.iterative_wiki import ensure_osiris_panel_sections

                salvaged = ensure_osiris_panel_sections(salvaged)
                try:
                    okf.put_wiki(bundle_id, state.user_space, salvaged)
                except Exception:  # noqa: BLE001
                    pass
                state.status = "succeeded"
                state.error = f"wiki_upsert_partial: {_format_exc(exc)}"
                state.ended_at = utc_now_rfc3339()
                state.params = {
                    **dict(state.params or {}),
                    "bundle_id": bundle_id,
                    "wiki_markdown": salvaged,
                    "wiki_excerpt": extract_wiki_sections(
                        salvaged, max_chars=2400
                    ),
                    "wiki_extract": extract_wiki_sections(
                        salvaged, max_chars=2400
                    ),
                    "has_llm_wiki": "true",
                    "wiki_partial": "true",
                    "prompt_name": wiki_cfg["prompt_name"],
                    "wiki_agent": wiki_cfg["prompt_name"],
                }
                self.store.write_state(state)
                return state
            return self._fail(state, error=f"wiki_upsert: {_format_exc(exc)}")

        excerpt = extract_wiki_sections(wiki, max_chars=max(2400, max_wiki_chars // 2))
        slim = {
            k: v
            for k, v in params.items()
            if k not in {"chunks", "grab_chunks"}
        }
        state.params = {
            **slim,
            "bundle_id": bundle_id,
            "wiki_markdown": wiki,
            "wiki_excerpt": excerpt,
            "wiki_extract": excerpt,
            "has_llm_wiki": "true",
            "wiki_created": "true" if created else "false",
            "wiki_match_score": (
                "" if created else str(getattr(match, "score", ""))
            ),
            "prompt_name": wiki_cfg["prompt_name"],
            "wiki_agent": wiki_cfg["prompt_name"],
            "chunks": chunks,
        }
        state.result = self.findings_from_wiki_chunks(
            chunks,
            max_chunks=max_chunks,
            query=query,
            path=path,
            prompt_name=wiki_cfg["prompt_name"] or "wiki_upsert",
        )
        self.store.append_blackboard(
            state.run_id,
            {
                "kind": "builtin",
                "builtin": "wiki_upsert",
                "bundle_id": bundle_id,
                "created": created,
                "chunk_count": len(chunks[:max_chunks]),
                "wiki_chars": len(wiki),
                "path": str(path),
                "provenance": "wiki_generator",
            },
        )
        self.guard.emit(
            kind="okf.wiki.upsert",
            state=state,
            intent="okf.wiki",
            ext={"bundle_id": bundle_id, "created": created},
        )
        self.store.write_state(state)
        return state

    async def run_iterative(self, state: RunState) -> RunState:
        """Legacy iterative wiki fold (``wiki_mode=iterative``).

        Example:
            >>> await WikiGeneratorWorkflow(...).run_iterative(state)  # doctest: +SKIP
        """
        from thot.okf.iterative_wiki import build_wiki_iteratively
        from thot.okf.store import OkfBundleStore

        if not self.guard.check_action_permission(
            state, {"type": "okf_iterative_wiki", "tool": "okf_iterative_wiki"}
        ):
            return self._fail(
                state, error="okf_iterative_wiki: blocked by AgentGuard"
            )

        params = dict(state.params or {})
        query = str(
            params.get("query") or params.get("topic") or state.goal or ""
        ).strip()
        bundle_id = str(params.get("bundle_id") or "").strip()
        root = self.bundle_root(state.user_space, bundle_id)
        if root is None:
            return self._fail(
                state,
                error=(
                    "okf_iterative_wiki: missing bundle_id / bundle directory"
                ),
            )

        wiki_cfg = self.resolve_wiki_prompt_config(params)
        chunks = self.wiki_chunks_for_bundle(params, root)
        max_chunks = max(1, min(int(params.get("max_wiki_chunks") or 6), 12))
        okf = OkfBundleStore()
        initial = self.seed_or_load_wiki(
            bundle_id=bundle_id,
            user_space=state.user_space,
            query=query,
            wiki_cfg=wiki_cfg,
            store=okf,
        )

        def _progress(wiki_text: str, index: int, total: int) -> None:
            try:
                okf.put_wiki(bundle_id, state.user_space, wiki_text)
            except Exception:  # noqa: BLE001
                LOGGER.debug("mid-wiki put failed", exc_info=True)
            self.store.append_blackboard(
                state.run_id,
                {
                    "kind": "wiki_progress",
                    "builtin": "okf_iterative_wiki",
                    "bundle_id": bundle_id,
                    "chunk_index": index,
                    "chunk_total": total,
                    "wiki_chars": len(wiki_text),
                    "prompt_name": wiki_cfg["prompt_name"],
                    "provenance": "wiki_generator",
                },
            )
            self.store.write_state(state)

        try:
            wiki = await build_wiki_iteratively(
                llm=self.llm,
                query=query,
                chunks=chunks,
                initial_wiki=initial,
                max_chunks=max_chunks,
                on_progress=_progress,
                system=wiki_cfg["merge_system"],
                structured_facts_seed=wiki_cfg["structured_facts_seed"],
                information_priority_keys=wiki_cfg["priority_keys"],
                sequential=True,
            )
            path = okf.put_wiki(bundle_id, state.user_space, wiki)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("okf_iterative_wiki failed")
            return self._fail(
                state, error=f"okf_iterative_wiki: {_format_exc(exc)}"
            )

        slim = {
            k: v
            for k, v in params.items()
            if k not in {"chunks", "grab_chunks"}
        }
        state.params = {
            **slim,
            "wiki_markdown": wiki,
            "wiki_excerpt": wiki,
            "has_llm_wiki": "true",
            "wiki_chunk_count": len(chunks[:max_chunks]),
            "prompt_name": wiki_cfg["prompt_name"],
            "wiki_agent": wiki_cfg["prompt_name"],
        }
        state.result = self.findings_from_wiki_chunks(
            chunks,
            max_chunks=max_chunks,
            query=query,
            path=path,
            prompt_name=wiki_cfg["prompt_name"],
        )
        self.store.append_blackboard(
            state.run_id,
            {
                "kind": "builtin",
                "builtin": "okf_iterative_wiki",
                "bundle_id": bundle_id,
                "chunk_count": len(chunks[:max_chunks]),
                "wiki_chars": len(wiki),
                "path": str(path),
                "prompt_name": wiki_cfg["prompt_name"],
                "provenance": "wiki_generator",
            },
        )
        self.guard.emit(
            kind="okf.wiki.iterative",
            state=state,
            intent="okf.wiki",
            ext={
                "bundle_id": bundle_id,
                "chunk_count": len(chunks[:max_chunks]),
                "prompt_name": wiki_cfg["prompt_name"],
            },
        )
        self.store.write_state(state)
        return state

    async def generate_wiki(
        self,
        topic: str,
        *,
        state: RunState,
        identity_token: Any | None = None,
        iterative: bool = False,
    ) -> RunState:
        """Public entry point preserved for callers / HMI compatibility.

        Args:
            topic: Wiki topic / query (written into params when empty).
            state: Existing run state (must have ``user_space`` / ``run_id``).
            identity_token: Optional SPIFFE id checked via AgentGuard.
            iterative: When true, use legacy iterative fold.

        Returns:
            Updated :class:`RunState` after wiki generation.

        Example:
            >>> await WikiGeneratorWorkflow(...).generate_wiki(  # doctest: +SKIP
            ...     "topic", state=state
            ... )
        """
        if identity_token is not None and not self.guard.validate_identity(
            identity_token
        ):
            raise PermissionError(
                "SPIRE identity validation failed for wiki generation"
            )
        params = dict(state.params or {})
        params.setdefault("query", topic)
        params.setdefault("topic", topic)
        state.params = params
        if iterative:
            return await self.run_iterative(state)
        return await self.run_upsert(state)
