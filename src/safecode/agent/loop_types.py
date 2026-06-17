"""Shared result dataclasses for AgentLoop (v6.29).

Extracted from loop.py to break the circular import that arises when mixin
modules need to construct AgentStepResult/AgentRunResult while loop.py
imports those same mixin modules.

All existing imports of the form::

    from safecode.agent.loop import AgentStepResult, AgentRunResult

continue to work because loop.py re-exports both names.
"""
from __future__ import annotations

from dataclasses import dataclass

from safecode.agent.session import AgentSessionState


@dataclass(frozen=True)
class AgentStepResult:
    """Result of advancing one agent step."""

    state: AgentSessionState
    observation: str
    stopped_for_approval: bool = False


@dataclass(frozen=True)
class AgentRunResult:
    """Result of advancing a bounded number of agent steps."""

    state: AgentSessionState
    steps: list[AgentStepResult]
    stopped_reason: str
