"""Title: General-purpose LLM agent (engine-agnostic wrapper).

Wraps :class:`~thot.agent.loop.AgentLoop` behind :class:`~thot.agent.base.BaseAgent`.
No wiki/OKF domain logic — register tools and run goals only.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from thot.action.models import utc_now_rfc3339
from thot.agent.base import BaseAgent, DecisionEngine
from thot.agent.guard import AgentGuard
from thot.agent.loop import AgentLoop, LlmClient
from thot.agent.models import AgentSpec, RunState
from thot.agent.runs import RunStore
from thot.agent.toolbox import ToolRegistry


class PassthroughDecisionEngine(DecisionEngine[RunState, dict[str, Any]]):
    """Placeholder engine — the ReAct loop owns turn-by-turn decisions.

    Example:
        >>> from thot.agent.llm_agent import PassthroughDecisionEngine
        >>> from thot.agent.models import RunState
        >>> PassthroughDecisionEngine().predict_action(RunState(goal="g"))["type"]
        'delegate_loop'
    """

    def predict_action(self, state: RunState) -> dict[str, Any]:
        """Return a delegate-to-loop action for ``state``.

        Example:
            >>> from thot.agent.llm_agent import PassthroughDecisionEngine
            >>> from thot.agent.models import RunState
            >>> PassthroughDecisionEngine().predict_action(RunState(goal="g"))["type"]
            'delegate_loop'
        """
        return {"type": "delegate_loop", "goal": state.goal}


class LLMAgent(BaseAgent[RunState, dict[str, Any]]):
    """Standalone LLM agent: tools + ReAct loop, wiki-agnostic.

    Example:
        >>> import inspect
        >>> from thot.agent.llm_agent import LLMAgent
        >>> inspect.iscoroutinefunction(LLMAgent.run)
        True
    """

    def __init__(
        self,
        *,
        store: RunStore,
        guard: AgentGuard,
        llm: LlmClient,
        toolbox: ToolRegistry | None = None,
        spec: AgentSpec | None = None,
        max_steps: int | None = None,
    ) -> None:
        """Wire run store, guard, LLM client, and optional tool registry.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.guard import AgentGuard
            >>> from thot.agent.llm_agent import LLMAgent
            >>> from thot.agent.runs import RunStore
            >>> class _StubLlm:
            ...     async def generate(self, prompt, **kw):
            ...         return '{}'
            >>> with tempfile.TemporaryDirectory() as td:
            ...     agent = LLMAgent(
            ...         store=RunStore(Path(td)),
            ...         guard=AgentGuard(Path(td) / "gov"),
            ...         llm=_StubLlm(),
            ...     )
            ...     agent.spec.name
            'llm_agent'
        """
        super().__init__(engine=PassthroughDecisionEngine(), guard=guard)
        self.store = store
        self.llm = llm
        self.toolbox = toolbox
        self.spec = spec or AgentSpec(name="llm_agent")
        if max_steps is not None:
            self.spec = self.spec.model_copy(
                update={
                    "stop": self.spec.stop.model_copy(
                        update={"max_steps": max_steps}
                    )
                }
            )
        self._loop = AgentLoop(
            store=store, guard=guard, llm=llm, toolbox=toolbox
        )
        self._extra_tools: dict[str, Callable[..., Any]] = {}

    def register_tool(self, name: str, func: Callable[..., Any]) -> None:
        """Register an extra callable tool by name (for specialized workflows).

        Example:
            >>> from thot.agent.llm_agent import LLMAgent  # doctest: +SKIP
            >>> agent.register_tool("echo", lambda x: x)  # doctest: +SKIP
        """
        self._extra_tools[name] = func

    async def run(
        self,
        input_data: Any,
        identity_context: Optional[Any] = None,
        *,
        state: RunState | None = None,
        spec: AgentSpec | None = None,
        authorization: str | None = None,
        finalize: bool = True,
    ) -> RunState:
        """Run a single-agent ReAct loop for ``input_data`` (goal string or state).

        Args:
            input_data: Goal string, or an existing :class:`RunState`.
            identity_context: Optional SPIFFE id for :meth:`AgentGuard.validate_identity`.
            state: Optional pre-built run state (overrides ``input_data`` when set).
            spec: Optional agent YAML spec (defaults to constructor ``spec``).
            authorization: Bearer forwarded to MCP tools.
            finalize: When true, mark the run succeeded on final.

        Returns:
            Terminal :class:`RunState`.

        Example:
            >>> await agent.run("goal")  # doctest: +SKIP
        """
        guard = self.guard
        # Always ask the guard: under SPIFFE_ENFORCE, None/empty fails.
        if isinstance(guard, AgentGuard) and not guard.validate_identity(
            identity_context
        ):
            raise PermissionError(
                "SPIRE/SPIFFE identity validation failed "
                f"(identity={identity_context!r})"
            )

        if state is None:
            if isinstance(input_data, RunState):
                state = input_data
            else:
                goal = str(input_data or "").strip() or "agent run"
                state = RunState(
                    agent=(spec or self.spec).name,
                    goal=goal,
                    status="queued",
                    started_at=utc_now_rfc3339(),
                )
                if identity_context:
                    state.spiffe_id = str(identity_context)
                self.store.write_state(state)

        if isinstance(guard, AgentGuard):
            proposed = {"type": "run", "goal": state.goal}
            if not guard.check_action_permission(state, proposed):
                raise PermissionError(
                    f"AgentGuard blocked agent run for goal={state.goal!r}"
                )

        use_spec = spec or self.spec
        return await self._loop.run(
            state,
            use_spec,
            authorization=authorization,
            finalize=finalize,
        )
