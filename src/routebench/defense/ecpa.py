"""Interleaved recovery; no hidden evaluator, automatic success stop or rollback."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Protocol

from pydantic import Field

from routebench.authorization.controllers import (
    OperationalAuthorizationContext,
    OperationalAuthorizationController,
)
from routebench.contracts import ActionRequest, DecisionKind, FeedbackMode
from routebench.defense.contracts import (
    ApprovalRule,
    PublicRecoveryTask,
    WitnessStatus,
    completion_witness,
    content_hash,
    granted,
    public_policy_allows,
)
from routebench.runtime.reference import InvalidRouteActionError, Preview, ScenarioState
from routebench.runtime.reference import TrustedToolExecutor as ToolExecutor
from routebench.scenarios.schema import AuthorityGrant, GraphEdgeSpec, RouteActionSpec, StrictModel


class DefenseDecisionKind(StrEnum):
    ALLOW = "allow"
    CONSTRAIN = "constrain"
    ESCALATE = "escalate"
    DENY = "deny"


class BudgetLimits(StrictModel):
    decisions: int = Field(default=32, gt=0)
    agent_calls: int = Field(default=64, gt=0)
    executions: int = Field(default=16, gt=0)
    approvals: int = Field(default=4, ge=0)
    previews: int = Field(default=256, ge=0)
    searches: int = Field(default=4096, ge=0)
    total: int = Field(default=8192, gt=0)


class BudgetExhausted(RuntimeError):
    pass


class AgentResponseError(RuntimeError):
    """An attempted model call failed; the episode must remain in its denominator."""


@dataclass(slots=True)
class BudgetLedger:
    limits: BudgetLimits
    used: dict[str, int] = field(default_factory=dict)

    def remaining(self, name: str) -> int:
        return int(getattr(self.limits, name)) - self.used.get(name, 0)

    def charge(self, name: str, count: int = 1) -> None:
        if count < 0 or name == "total":
            raise ValueError("invalid resource charge")
        if self.remaining(name) < count:
            raise BudgetExhausted(name)
        if self.remaining("total") < count:
            raise BudgetExhausted("total")
        self.used[name] = self.used.get(name, 0) + count
        self.used["total"] = self.used.get("total", 0) + count

    def snapshot(self) -> dict[str, int]:
        return {name: self.remaining(name) for name in BudgetLimits.model_fields}


class AgentReplyKind(StrEnum):
    PROPOSE = "propose"
    STOP = "stop"
    ACCEPT = "accept"
    REJECT = "reject"


class AgentReply(StrictModel):
    kind: AgentReplyKind
    edge_id: str | None = None
    action: RouteActionSpec | None = None
    request_hash: str | None = None


class DefenseCandidate(StrictModel):
    candidate_id: str
    kind: DefenseDecisionKind
    edge_id: str | None = None
    action: RouteActionSpec | None = None
    request_hash: str | None = None
    grant_id: str | None = None
    witness: WitnessStatus | None = None


class TrustedReceipt(StrictModel):
    edge_id: str
    request_hash: str
    node: str
    facts: tuple[str, ...]
    labels: tuple[str, ...]
    approval_epoch: int


class ToolContent(StrictModel):
    """Low-trust data, never parsed as authorization metadata."""

    trust: str = "untrusted_tool_content"
    tool: str
    content: object


class AgentView(StrictModel):
    task: PublicRecoveryTask
    node: str
    facts: tuple[str, ...]
    receipts: tuple[TrustedReceipt, ...]
    tool_contents: tuple[ToolContent, ...]
    feedback: tuple[str, ...]
    remaining: dict[str, int]
    offer: DefenseCandidate | None = None


class DefenseObservation(StrictModel):
    task: PublicRecoveryTask
    step: int
    node: str
    facts: tuple[str, ...]
    proposal: AgentReply
    grants: tuple[AuthorityGrant, ...]
    receipts: tuple[TrustedReceipt, ...]
    tool_contents: tuple[ToolContent, ...]
    feedback: tuple[str, ...]
    remaining: dict[str, int]
    approval_epoch: int
    menu: tuple[DefenseCandidate, ...]
    state_token: str


class ApprovalReceipt(StrictModel):
    approved: bool
    principal: str
    task_id: str
    request_hash: str
    grant_id: str
    epoch: int
    expires_after_decision: int


class ApprovalProvider(Protocol):
    async def request(
        self,
        *,
        principal: str,
        task_id: str,
        request_hash: str,
        rule: ApprovalRule,
        epoch: int,
        decision: int,
    ) -> ApprovalReceipt: ...


class RecoveryAgent(Protocol):
    async def respond(self, view: AgentView, *, seed: int) -> AgentReply: ...


class ToolContentProvider(Protocol):
    def present(self, tool: str, output: object, *, execution: int) -> object: ...


class ECPAStep(StrictModel):
    observation: DefenseObservation
    selected: DefenseCandidate
    accepted_action: RouteActionSpec | None = None
    acceptance: str = "not_required"
    dispatched: bool = False
    approval_requested: bool = False
    approved: bool = False
    feedback: str
    receipt: TrustedReceipt | None = None
    remaining: dict[str, int]
    terminated: bool = False
    termination_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ActiveApproval:
    grants: tuple[AuthorityGrant, ...]
    request_hash: str
    expires_after_decision: int


class ECPAEnvironment:
    def __init__(
        self,
        task: PublicRecoveryTask,
        state: ScenarioState,
        *,
        budgets: BudgetLimits | None = None,
        principal: str = "task_agent",
        approval_provider: ApprovalProvider | None = None,
        tool_content_provider: ToolContentProvider | None = None,
    ) -> None:
        self.task = task
        self.state = state
        self.budget = BudgetLedger(budgets or BudgetLimits())
        self.principal = principal
        self.approval_provider = approval_provider
        self.tool_content_provider = tool_content_provider
        self.executor = ToolExecutor()
        self.guard = OperationalAuthorizationController()
        self.node = task.graph.start_node
        self.facts = frozenset(task.contract.initial_facts)
        self.executed_edges: tuple[str, ...] = ()
        self.receipts: list[TrustedReceipt] = []
        self.tool_contents: list[ToolContent] = []
        self.feedback: list[str] = []
        self.history: list[ECPAStep] = []
        self.active_approvals: list[ActiveApproval] = []
        self.approval_epoch = 0
        self.terminated = False
        self.termination_reason: str | None = None
        self.pending_proposal: AgentReply | None = None
        self._pending_observation: str | None = None

    def clone_for_collection(self) -> ECPAEnvironment:
        """Independent simulator branch; never effectful runtime rollback."""
        return copy.deepcopy(self)

    def finish(self, reason: str) -> None:
        self.terminated = True
        self.termination_reason = reason

    def _token(self) -> str:
        return content_hash(
            {
                "task": self.task.digest,
                "node": self.node,
                "facts": sorted(self.facts),
                "receipts": [item.model_dump(mode="json") for item in self.receipts],
                "epoch": self.approval_epoch,
                "decision": len(self.history),
                "execution_state": asdict(self.state),
            }
        )

    def agent_view(self, offer: DefenseCandidate | None = None) -> AgentView:
        return AgentView(
            task=self.task,
            node=self.node,
            facts=tuple(sorted(self.facts)),
            receipts=tuple(self.receipts),
            tool_contents=tuple(self.tool_contents),
            feedback=tuple(self.feedback),
            remaining=self.budget.snapshot(),
            offer=offer,
        )

    async def call_agent(
        self, agent: RecoveryAgent, *, seed: int, offer: DefenseCandidate | None = None
    ) -> AgentReply | None:
        try:
            self.budget.charge("agent_calls")
        except BudgetExhausted as error:
            self.finish(f"budget_exhausted:{error}")
            return None
        try:
            return await agent.respond(self.agent_view(offer).model_copy(deep=True), seed=seed)
        except AgentResponseError:
            self.finish("agent_response_error")
            return None

    def handle_stop(self) -> None:
        self.finish("agent_stop" if self.node in self.task.graph.terminal_nodes else "illegal_stop")

    def _edge(self, proposal: AgentReply) -> GraphEdgeSpec | None:
        edge = next(
            (edge for edge in self.task.graph.edges if edge.edge_id == proposal.edge_id), None
        )
        if edge is None or edge.source != self.node:
            return None
        if proposal.action is not None and proposal.action != edge.action:
            return None
        if not set(self.task.contract.actions[edge.edge_id].requires) <= self.facts:
            return None
        return edge

    def _request(self, edge: GraphEdgeSpec) -> tuple[ActionRequest, Preview]:
        self.executor.require_prior_actions(edge.action, self.state)
        preview = self.executor.preview(edge.action, self.state)
        effect = preview.effect.model_copy(update={"sensitivity": ",".join(preview.labels) or None})
        return ActionRequest(
            action_id=f"recovery-{len(self.history)}-{edge.edge_id}",
            step=len(self.history),
            tool=edge.action.tool,
            arguments=edge.action.arguments,
            effects=(effect,),
        ), preview

    def _grants(self, request_hash: str) -> tuple[AuthorityGrant, ...]:
        grants = self.task.contract.initial_grants
        for approval in self.active_approvals:
            if approval.request_hash == request_hash and (
                len(self.history) < approval.expires_after_decision
            ):
                grants += approval.grants
        return grants

    async def _check(
        self, edge: GraphEdgeSpec, extra_grants: tuple[AuthorityGrant, ...] = ()
    ) -> tuple[ActionRequest, Preview] | None:
        self.budget.charge("previews")
        try:
            request, preview = self._request(edge)
        except (InvalidRouteActionError, KeyError, ValueError, TypeError):
            return None
        grants = self._grants(request.action_hash) + extra_grants
        contract = self.task.contract.actions[edge.edge_id]
        if (
            not all(granted(atom, grants) for atom in edge.authority)
            or not public_policy_allows(self.task, edge)
            or not any(
                effect.resource == preview.effect.resource
                and effect.operation == preview.effect.operation
                and effect.target == preview.effect.target
                and set(preview.labels) <= set(effect.labels)
                for effect in contract.effects
            )
        ):
            return None
        decision = await self.guard.decide(
            request,
            OperationalAuthorizationContext(
                policy=self.task.policy,
                state=self.state,
                feedback_mode=FeedbackMode.MINIMAL,
                grants=grants,
            ),
            preview,
        )
        return (request, preview) if decision.kind is DecisionKind.ALLOW else None

    def _witness(
        self, edge: GraphEdgeSpec, grants: tuple[AuthorityGrant, ...], *, approvals_used: int = 0
    ) -> WitnessStatus:
        contract = self.task.contract.actions[edge.edge_id]
        if not contract.deterministic:
            return WitnessStatus.UNKNOWN
        remaining = (
            min(
                self.budget.remaining("executions"),
                self.task.graph.max_path_length - len(self.executed_edges),
                self.budget.remaining("decisions"),
            )
            - 1
        )
        if remaining < 0:
            return WitnessStatus.INFEASIBLE
        result = completion_witness(
            self.task,
            node=edge.target,
            facts=contract.successor(self.facts),
            executed_edge_ids=(*self.executed_edges, edge.edge_id),
            grants=grants,
            remaining_executions=remaining,
            max_expansions=min(self.budget.remaining("searches"), self.budget.remaining("total")),
            remaining_approvals=self.budget.remaining("approvals") - approvals_used,
        )
        self.budget.charge("searches", result.expansions)
        return result.status

    async def observe(self, proposal: AgentReply) -> DefenseObservation | None:
        """Deterministic concrete menu from this trusted snapshot."""
        if self.terminated:
            return None
        try:
            if self.budget.remaining("decisions") <= 0:
                raise BudgetExhausted("decisions")
            menu = [DefenseCandidate(candidate_id="deny", kind=DefenseDecisionKind.DENY)]
            proposed = self._edge(proposal)
            if self.budget.remaining("executions") > 0 and (
                len(self.executed_edges) < self.task.graph.max_path_length
            ):
                proposed_atoms = set(proposed.authority) if proposed is not None else set()
                for edge in sorted(self.task.graph.edges, key=lambda item: item.edge_id):
                    if (
                        edge.source != self.node
                        or self._edge(AgentReply(kind=AgentReplyKind.PROPOSE, edge_id=edge.edge_id))
                        is None
                    ):
                        continue
                    is_proposed = proposed is not None and proposed.edge_id == edge.edge_id
                    if not is_proposed and not set(edge.authority) <= proposed_atoms:
                        continue
                    checked = await self._check(edge)
                    if checked is not None:
                        request, _ = checked
                        witness = (
                            None
                            if is_proposed
                            else self._witness(edge, self.task.contract.initial_grants)
                        )
                        if is_proposed or witness is WitnessStatus.FEASIBLE:
                            kind = (
                                DefenseDecisionKind.ALLOW
                                if is_proposed
                                else DefenseDecisionKind.CONSTRAIN
                            )
                            menu.append(
                                DefenseCandidate(
                                    candidate_id=f"{kind.value}:{edge.edge_id}",
                                    kind=kind,
                                    edge_id=edge.edge_id,
                                    action=edge.action,
                                    request_hash=request.action_hash,
                                    witness=witness,
                                )
                            )
                    elif is_proposed and self.budget.remaining("approvals") > 0:
                        for rule in self.task.contract.approvals:
                            if edge.edge_id not in rule.edge_ids:
                                continue
                            checked_approval = await self._check(edge, rule.grants)
                            if checked_approval is None:
                                continue
                            request, _ = checked_approval
                            witness = self._witness(
                                edge, self.task.contract.initial_grants, approvals_used=1
                            )
                            if witness is WitnessStatus.FEASIBLE:
                                menu.append(
                                    DefenseCandidate(
                                        candidate_id=f"escalate:{edge.edge_id}:{rule.grant_id}",
                                        kind=DefenseDecisionKind.ESCALATE,
                                        edge_id=edge.edge_id,
                                        action=edge.action,
                                        request_hash=request.action_hash,
                                        grant_id=rule.grant_id,
                                        witness=witness,
                                    )
                                )
            observation = DefenseObservation(
                task=self.task,
                step=len(self.history),
                node=self.node,
                facts=tuple(sorted(self.facts)),
                proposal=proposal,
                grants=self.task.contract.initial_grants,
                receipts=tuple(self.receipts),
                tool_contents=tuple(self.tool_contents),
                feedback=tuple(self.feedback),
                remaining=self.budget.snapshot(),
                approval_epoch=self.approval_epoch,
                menu=tuple(menu),
                state_token=self._token(),
            )
            self._pending_observation = observation.model_dump_json()
            return observation.model_copy(deep=True)
        except BudgetExhausted as error:
            self.finish(f"budget_exhausted:{error}")
            return None

    async def step(
        self,
        observation: DefenseObservation,
        candidate_id: str,
        *,
        agent: RecoveryAgent,
        seed: int,
    ) -> ECPAStep:
        if self.terminated or observation.state_token != self._token():
            raise ValueError("stale or terminated recovery observation")
        if self._pending_observation != observation.model_dump_json():
            raise ValueError("modified recovery menu or observation")
        # Use a trusted copy, not caller-owned nested mappings.
        observation = DefenseObservation.model_validate_json(self._pending_observation)
        self._pending_observation = None
        candidate = next(
            (item for item in observation.menu if item.candidate_id == candidate_id), None
        )
        if candidate is None:
            raise ValueError("controller selected an unregistered candidate")
        dispatched = approved = approval_requested = False
        acceptance = "not_required"
        receipt = None
        accepted_action = None
        feedback = f"request_denied_replan_from:{self.node}"
        try:
            self.budget.charge("decisions")
            edge = (
                self._edge(
                    AgentReply(
                        kind=AgentReplyKind.PROPOSE,
                        edge_id=candidate.edge_id,
                        action=candidate.action,
                    )
                )
                if candidate.kind is not DefenseDecisionKind.DENY
                else None
            )
            if edge is not None and candidate.kind is DefenseDecisionKind.CONSTRAIN:
                acceptance_snapshot = self._token()
                reply = await self.call_agent(agent, seed=seed, offer=candidate)
                if reply is not None and (
                    reply.kind is AgentReplyKind.ACCEPT
                    and reply.edge_id == candidate.edge_id
                    and reply.action == candidate.action
                    and reply.request_hash == candidate.request_hash
                    and self._token() == acceptance_snapshot
                ):
                    acceptance = "accepted"
                else:
                    acceptance = "rejected" if reply is not None else "unavailable"
                    if reply is not None and reply.kind is AgentReplyKind.PROPOSE:
                        self.pending_proposal = reply
                        acceptance = "fresh_proposal"
                    if reply is not None and reply.kind is AgentReplyKind.STOP:
                        self.handle_stop()
                    edge = None
            if edge is not None and candidate.kind is DefenseDecisionKind.ESCALATE:
                self.budget.charge("approvals")
                approval_requested = True
                rule = next(
                    rule
                    for rule in self.task.contract.approvals
                    if rule.grant_id == candidate.grant_id
                )
                if self.approval_provider is not None:
                    approval_snapshot = self._token()
                    approval = await self.approval_provider.request(
                        principal=self.principal,
                        task_id=self.task.contract.task_id,
                        request_hash=str(candidate.request_hash),
                        rule=rule,
                        epoch=self.approval_epoch,
                        decision=len(self.history),
                    )
                    approved = (
                        approval.approved
                        and approval.principal == self.principal
                        and approval.task_id == self.task.contract.task_id
                        and approval.request_hash == candidate.request_hash
                        and approval.grant_id == rule.grant_id
                        and approval.epoch == self.approval_epoch
                        and self._token() == approval_snapshot
                        and len(self.history)
                        < approval.expires_after_decision
                        <= len(self.history) + rule.validity_decisions
                    )
                    if approved:
                        self.active_approvals.append(
                            ActiveApproval(
                                rule.grants, approval.request_hash, approval.expires_after_decision
                            )
                        )
                        self.approval_epoch += 1
                if not approved:
                    edge = None
                    feedback = "approval_rejected_replan"
            if edge is not None and not self.terminated:
                edge = self._edge(
                    AgentReply(
                        kind=AgentReplyKind.PROPOSE,
                        edge_id=candidate.edge_id,
                        action=candidate.action,
                    )
                )
            if edge is not None and not self.terminated:
                # No await between final guard result and synchronous dispatch.
                checked = await self._check(edge)
                if checked is not None:
                    request, preview = checked
                    if request.action_hash != candidate.request_hash:
                        feedback = "request_changed_replan"
                    else:
                        self.budget.charge("executions")
                        execution = self.executor.execute(request, self.state)
                        accepted_action = edge.action
                        dispatched = True
                        self.node = edge.target
                        self.facts = self.task.contract.actions[edge.edge_id].successor(self.facts)
                        self.executed_edges = (*self.executed_edges, edge.edge_id)
                        receipt = TrustedReceipt(
                            edge_id=edge.edge_id,
                            request_hash=request.action_hash,
                            node=self.node,
                            facts=tuple(sorted(self.facts)),
                            labels=preview.labels,
                            approval_epoch=self.approval_epoch,
                        )
                        self.receipts.append(receipt)
                        output: object = execution.result.model_dump(mode="json")["output"]
                        if self.tool_content_provider is not None:
                            output = self.tool_content_provider.present(
                                edge.action.tool, output, execution=len(self.executed_edges)
                            )
                        self.tool_contents.append(
                            ToolContent(tool=edge.action.tool, content=output)
                        )
                        feedback = "executed_continue_or_stop"
                else:
                    feedback = "guard_rejected_replan"
            if not self.terminated and self.budget.remaining("decisions") <= 0:
                self.finish("budget_exhausted:decisions")
        except BudgetExhausted as error:
            self.finish(f"budget_exhausted:{error}")
        self.feedback.append(feedback)
        result = ECPAStep(
            observation=observation,
            selected=candidate,
            accepted_action=accepted_action,
            acceptance=acceptance,
            dispatched=dispatched,
            approval_requested=approval_requested,
            approved=approved,
            feedback=feedback,
            receipt=receipt,
            remaining=self.budget.snapshot(),
            terminated=self.terminated,
            termination_reason=self.termination_reason,
        )
        self.history.append(result)
        return result
