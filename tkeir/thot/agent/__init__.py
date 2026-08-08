"""Title: agent package init

T-KEIR agent **library** (Phase B–D) — from scratch, no frameworks.

Identified agents are :class:`~thot.agent.agent.Agent` instances loaded from
YAML. General execution uses :class:`~thot.agent.llm_agent.LLMAgent`. Domain
pipelines such as LLM-Wiki live under :mod:`thot.agent.workflows`. The HTTP
tool that hosts an :class:`~thot.agent.agent.AgentSet` is ``thot.tools.agent``
(``tkeir-agent``).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from typing import Any

from thot.agent.agent import Agent, AgentSet
from thot.agent.base import BaseAgent, BaseAgentGuard, DecisionEngine
from thot.agent.llm_agent import LLMAgent
from thot.agent.models import AgentSpec, GroundedFindings, RunState
from thot.agent.registry import list_agent_names, load_agent_spec

# Loader only — do not import WikiGeneratorWorkflow here (OKF cycle via compose).
from thot.agent.workflows.loader import list_workflow_names, load_workflow

__all__ = [
    "Agent",
    "AgentSet",
    "AgentSpec",
    "BaseAgent",
    "BaseAgentGuard",
    "DecisionEngine",
    "GroundedFindings",
    "LLMAgent",
    "RunState",
    "WikiGeneratorWorkflow",
    "list_agent_names",
    "list_workflow_names",
    "load_agent_spec",
    "load_workflow",
]


def __getattr__(name: str) -> Any:
    """Lazy-export wiki domain type to break ``okf.exporter`` ↔ ``agent`` cycles.

    Example:
        >>> from thot import agent as agent_pkg
        >>> agent_pkg.WikiGeneratorWorkflow.__name__
        'WikiGeneratorWorkflow'
    """
    if name == "WikiGeneratorWorkflow":
        from thot.agent.workflows.wiki_generator import WikiGeneratorWorkflow

        return WikiGeneratorWorkflow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
