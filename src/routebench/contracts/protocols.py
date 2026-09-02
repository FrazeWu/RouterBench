"""Behavioral interfaces implemented by benchmark components."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from routebench.contracts.models import ActionRequest, Decision, PlannerContext, ToolResult


@runtime_checkable
class Planner(Protocol):
    async def propose(self, context: PlannerContext) -> ActionRequest: ...


@runtime_checkable
class AuthorizationController(Protocol):
    async def decide(self, action: ActionRequest, context: object) -> Decision: ...


@runtime_checkable
class ToolExecutor(Protocol):
    async def execute(self, action: ActionRequest, workspace: Path) -> ToolResult: ...


@runtime_checkable
class Verifier(Protocol):
    def evaluate(self, workspace: Path, state: object) -> bool: ...
