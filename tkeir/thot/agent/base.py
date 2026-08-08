"""Title: Engine-agnostic agent abstractions.

Pure contracts for decision engines, guardrails, and agents. Domain workflows
(LLM-Wiki, OTAN compose, …) sit *on top* of these interfaces — they are not
part of the core agent loop.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, TypeVar

S = TypeVar("S")
A = TypeVar("A")


class DecisionEngine(ABC, Generic[S, A]):
    """Abstract policy interface ``π(s) → a``.

    Example:
        >>> from thot.agent.base import DecisionEngine
        >>> import inspect
        >>> inspect.isabstract(DecisionEngine)
        True
    """

    @abstractmethod
    def predict_action(self, state: S) -> A:
        """Return the next action for ``state``.

        Example:
            >>> DecisionEngine().predict_action({})  # doctest: +SKIP
        """


class BaseAgentGuard(ABC, Generic[S, A]):
    """Guardrail contract: identity verification + action authorization.

    Concrete governor/SPIFFE logic lives in
    :class:`~thot.agent.guard.AgentGuard`.

    Example:
        >>> from thot.agent.base import BaseAgentGuard
        >>> import inspect
        >>> inspect.isabstract(BaseAgentGuard)
        True
    """

    @abstractmethod
    def validate_identity(self, identity_token: Any) -> bool:
        """Return True when the workload / caller identity is allowed.

        Example:
            >>> BaseAgentGuard().validate_identity(None)  # doctest: +SKIP
        """

    @abstractmethod
    def check_action_permission(self, state: S, proposed_action: A) -> bool:
        """Return True when ``proposed_action`` may run in ``state``.

        Example:
            >>> BaseAgentGuard().check_action_permission({}, {})  # doctest: +SKIP
        """


class BaseAgent(ABC, Generic[S, A]):
    """Core agent contract — engine + optional guard, no domain coupling.

    Example:
        >>> from thot.agent.base import BaseAgent
        >>> import inspect
        >>> inspect.isabstract(BaseAgent)
        True
    """

    def __init__(
        self,
        engine: DecisionEngine[S, A] | None = None,
        guard: BaseAgentGuard[S, A] | None = None,
    ) -> None:
        """Bind an optional decision engine and guardrail.

        Example:
            >>> from thot.agent.base import BaseAgent
            >>> class _Tiny(BaseAgent):
            ...     async def run(self, input_data, identity_context=None):
            ...         return input_data
            >>> _Tiny().engine is None
            True
        """
        self.engine = engine
        self.guard = guard

    @abstractmethod
    async def run(
        self,
        input_data: Any,
        identity_context: Optional[Any] = None,
    ) -> Any:
        """Execute one agent invocation (single- or multi-turn).

        Example:
            >>> await BaseAgent().run("goal")  # doctest: +SKIP
        """
