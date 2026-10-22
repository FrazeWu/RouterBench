"""Development overlays, trusted approval simulation, and tool-return injection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from routebench.defense.contracts import ApprovalRule, PublicRecoveryTask, RecoveryContract
from routebench.defense.ecpa import ApprovalReceipt
from routebench.defense.evaluation_bridge import (
    PublicEvaluationContext,
    build_public_evaluation_context,
)
from routebench.scenarios.loader import ScenarioBundle, load_scenario
from routebench.scenarios.schema import ScenarioSplit


@dataclass(frozen=True, slots=True)
class DevelopmentTask:
    public: PublicRecoveryTask
    bundle: ScenarioBundle
    evaluation_context: PublicEvaluationContext


def load_development_tasks(root: Path, config: Path) -> tuple[DevelopmentTask, ...]:
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    if raw.get("purpose") != "development_feasibility_only":
        raise ValueError("development runner cannot load a formal protocol")
    tasks = []
    for item in raw["tasks"]:
        bundle = load_scenario(root / item["scenario"])
        if bundle.definition.metadata.split is not ScenarioSplit.DEV:
            raise ValueError("feasibility runner rejects formal test tasks")
        graph = bundle.definition.graph
        if graph is None:
            raise ValueError("recovery requires a public candidate graph")
        contract = RecoveryContract.model_validate(item["contract"])
        if contract.task_id != bundle.definition.metadata.scenario_id:
            raise ValueError("public contract is bound to a different task")
        tasks.append(
            DevelopmentTask(
                PublicRecoveryTask(
                    prompt=bundle.definition.task.prompt,
                    functional_goal=bundle.definition.task.functional_goal,
                    graph=graph,
                    policy=bundle.definition.policy,
                    contract=contract,
                ),
                bundle,
                build_public_evaluation_context(bundle),
            )
        )
    return tuple(tasks)


class SimulatedApprover:
    def __init__(self, *, approve: bool = True) -> None:
        self.approve = approve

    async def request(
        self,
        *,
        principal: str,
        task_id: str,
        request_hash: str,
        rule: ApprovalRule,
        epoch: int,
        decision: int,
    ) -> ApprovalReceipt:
        return ApprovalReceipt(
            approved=self.approve,
            principal=principal,
            task_id=task_id,
            request_hash=request_hash,
            grant_id=rule.grant_id,
            epoch=epoch,
            expires_after_decision=decision + rule.validity_decisions,
        )


class InjectedToolContent:
    """Development payload only; attack assignment never enters runtime receipts."""

    def __init__(self, text: str, *, at_execution: int = 1) -> None:
        self.text = text
        self.at_execution = at_execution

    def present(self, tool: str, output: object, *, execution: int) -> object:
        del tool
        if execution != self.at_execution:
            return output
        return {"data": output, "message": self.text}
