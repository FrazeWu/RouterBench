"""Strict schema for executable RouteBench scenarios."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from routebench.contracts import AttackCondition, BudgetSpec, DecisionKind, RiskCategory
from routebench.scenarios.taxonomy import (
    AttackMechanism,
    BenchmarkCaseProfile,
    RouteTopology,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScenarioSplit(StrEnum):
    DEV = "dev"
    TEST = "test"


class AuthorityGrant(StrictModel):
    resource: str = Field(min_length=1)
    operations: tuple[str, ...] = Field(min_length=1)
    scope: str = Field(min_length=1)


class TaskSpec(StrictModel):
    prompt: str = Field(min_length=1)
    functional_goal: str = Field(min_length=1)
    tools: tuple[str, ...] = Field(min_length=1)
    minimum_authority: tuple[AuthorityGrant, ...] = Field(min_length=1)


class ForbiddenEffect(StrictModel):
    goal_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1)
    resource: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    protected_labels: tuple[str, ...] = ()
    intervention: DecisionKind = DecisionKind.DENY


class ForbiddenTarget(StrictModel):
    """One atomic or compound target selected for an evaluation run."""

    target_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    effect_goal_ids: tuple[str, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def require_unique_effects(self) -> ForbiddenTarget:
        if len(self.effect_goal_ids) != len(set(self.effect_goal_ids)):
            raise ValueError("forbidden target effect goal IDs must be unique")
        return self


class PolicySpec(StrictModel):
    forbidden_effects: tuple[ForbiddenEffect, ...] = Field(min_length=1)
    targets: tuple[ForbiddenTarget, ...] = ()

    @model_validator(mode="after")
    def require_unique_goal_ids(self) -> PolicySpec:
        goal_ids = [effect.goal_id for effect in self.forbidden_effects]
        if len(goal_ids) != len(set(goal_ids)):
            raise ValueError("forbidden effect goal IDs must be unique")
        target_ids = [target.target_id for target in self.targets]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("forbidden target IDs must be unique")
        unknown_effects = {
            goal_id for target in self.targets for goal_id in target.effect_goal_ids
        } - set(goal_ids)
        if unknown_effects:
            raise ValueError(
                f"forbidden targets reference unknown effects: {sorted(unknown_effects)}"
            )
        return self

    @property
    def target_ids(self) -> tuple[str, ...]:
        if self.targets:
            return tuple(target.target_id for target in self.targets)
        return tuple(effect.goal_id for effect in self.forbidden_effects)

    def target_effects(self, target_id: str) -> tuple[ForbiddenEffect, ...]:
        effects = {effect.goal_id: effect for effect in self.forbidden_effects}
        if not self.targets:
            try:
                return (effects[target_id],)
            except KeyError as error:
                raise ValueError(f"unknown forbidden target: {target_id}") from error
        target = next((item for item in self.targets if item.target_id == target_id), None)
        if target is None:
            raise ValueError(f"unknown forbidden target: {target_id}")
        return tuple(effects[goal_id] for goal_id in target.effect_goal_ids)


class AssertionSpec(StrictModel):
    assertion: str = Field(min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)


class VerifierSpec(StrictModel):
    functional: tuple[AssertionSpec, ...] = Field(min_length=1)
    compliance: tuple[AssertionSpec, ...] = Field(min_length=1)
    attack: dict[str, tuple[AssertionSpec, ...]] = Field(min_length=1)


class PriorActionRequirement(StrictModel):
    """A prior successful action required before a route action may run."""

    tool: str = Field(min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)


class RouteActionSpec(StrictModel):
    tool: str = Field(min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)
    requires_prior_actions: tuple[PriorActionRequirement, ...] = ()


class RouteSpec(StrictModel):
    actions: tuple[RouteActionSpec, ...] = Field(min_length=1)


class AuthorityAtom(StrictModel):
    """One exact authority exercised by a graph edge."""

    resource: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    target: str = Field(min_length=1)


class GraphNodeSpec(StrictModel):
    node_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1)


class CapabilityBindingSpec(StrictModel):
    """Public author-selected provider binding for one graph transition."""

    binding_id: str = Field(
        pattern=(
            r"^[a-z0-9_]+::[a-z0-9_]+(?:\.[a-z0-9_]+){4}::[a-z0-9_]+$"
        )
    )
    adapter: str = Field(min_length=1)
    skill_ids: tuple[str, ...] = Field(min_length=1)
    workflow_template: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_skills(self) -> CapabilityBindingSpec:
        if len(self.skill_ids) != len(set(self.skill_ids)):
            raise ValueError("capability binding skill_ids must be unique")
        return self


class PublicRouteAttributes(StrictModel):
    """Prompt-visible ordinal properties used by the v2 route preference contract."""

    exposure: Literal["isolated", "delegated", "session", "standing_credential"]
    authority_scope: Literal["exact", "bounded", "workspace", "environment"]
    evidence_loss: Literal["primary", "corroborated", "rendered", "inferred"]
    interaction: Literal["direct", "mediated", "interactive", "manual"]


class GraphEdgeSpec(StrictModel):
    edge_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    source: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    target: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1)
    action: RouteActionSpec
    authority: tuple[AuthorityAtom, ...] = Field(min_length=1)
    capability_binding: CapabilityBindingSpec | None = None
    public_route_attributes: PublicRouteAttributes | None = None

    @model_validator(mode="after")
    def require_unique_authority_atoms(self) -> GraphEdgeSpec:
        if len(self.authority) != len(set(self.authority)):
            raise ValueError("graph edge authority atoms must be unique")
        if (
            self.capability_binding is not None
            and self.capability_binding.adapter != self.action.tool
        ):
            raise ValueError("capability binding adapter must match the graph edge action tool")
        return self


class CandidateGraph(StrictModel):
    """Model-visible bounded directed graph; reference certificates live elsewhere."""

    start_node: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    terminal_nodes: tuple[str, ...] = Field(min_length=2)
    max_path_length: int = Field(gt=0, le=16)
    nodes: tuple[GraphNodeSpec, ...] = Field(min_length=3)
    edges: tuple[GraphEdgeSpec, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_graph_structure(self) -> CandidateGraph:
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("candidate graph node IDs must be unique")
        edge_ids = [edge.edge_id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("candidate graph edge IDs must be unique")
        known_nodes = set(node_ids)
        unknown_nodes = {
            endpoint
            for edge in self.edges
            for endpoint in (edge.source, edge.target)
            if endpoint not in known_nodes
        }
        if unknown_nodes:
            raise ValueError(
                f"candidate graph edges reference unknown nodes: {sorted(unknown_nodes)}"
            )
        if self.start_node not in known_nodes:
            raise ValueError("candidate graph start_node must name a declared node")
        if len(self.terminal_nodes) != len(set(self.terminal_nodes)):
            raise ValueError("candidate graph terminal nodes must be unique")
        unknown_terminals = set(self.terminal_nodes) - known_nodes
        if unknown_terminals:
            raise ValueError(
                "candidate graph terminal_nodes reference unknown nodes: "
                f"{sorted(unknown_terminals)}"
            )
        if self.start_node in self.terminal_nodes:
            raise ValueError("candidate graph start_node cannot be terminal")
        out_degree: dict[str, int] = {}
        for edge in self.edges:
            out_degree[edge.source] = out_degree.get(edge.source, 0) + 1
        has_stop_or_continue = any(node_id in out_degree for node_id in self.terminal_nodes)
        if not any(degree >= 2 for degree in out_degree.values()) and not has_stop_or_continue:
            raise ValueError("candidate graph must contain at least one genuine branch")
        attributes_present = [edge.public_route_attributes is not None for edge in self.edges]
        if any(attributes_present) and not all(attributes_present):
            raise ValueError(
                "public route attributes must be present on every edge or on no graph edges"
            )
        return self

    @property
    def uses_public_route_contract(self) -> bool:
        return bool(self.edges) and all(
            edge.public_route_attributes is not None for edge in self.edges
        )

    def actions_for_path(
        self, edge_ids: tuple[str, ...], *, require_terminal: bool = True
    ) -> tuple[RouteActionSpec, ...]:
        if not edge_ids:
            raise ValueError("graph path must contain at least one edge")
        if len(edge_ids) > self.max_path_length:
            raise ValueError("graph path exceeds max_path_length")
        edges = {edge.edge_id: edge for edge in self.edges}
        current = self.start_node
        actions: list[RouteActionSpec] = []
        for edge_id in edge_ids:
            try:
                edge = edges[edge_id]
            except KeyError as error:
                raise ValueError(f"graph path references unknown edge: {edge_id}") from error
            if edge.source != current:
                raise ValueError(
                    f"graph path is discontinuous at {edge_id}: expected source {current}, "
                    f"found {edge.source}"
                )
            actions.append(edge.action)
            current = edge.target
        if require_terminal and current not in self.terminal_nodes:
            raise ValueError(f"graph path does not end at a terminal node: {current}")
        return tuple(actions)


class GraphPathSpec(StrictModel):
    edge_ids: tuple[str, ...] = Field(min_length=1)


class EdgeRouteCost(StrictModel):
    """Private per-edge costs for scenarios that evaluate capability routing."""

    security_risk: int = Field(ge=0)
    privilege_scope: int = Field(ge=0)
    evidence_gap: int = Field(ge=0)
    execution_cost: int = Field(ge=0)


class ReferencePathCertificates(StrictModel):
    safe: GraphPathSpec
    attack: dict[str, GraphPathSpec] = Field(min_length=1)


class ReferenceRoutes(StrictModel):
    safe: RouteSpec
    attack: dict[str, RouteSpec] = Field(min_length=1)
    certificates: ReferencePathCertificates | None = None
    edge_route_costs: dict[str, EdgeRouteCost] = Field(default_factory=dict)


class ScenarioMetadata(StrictModel):
    schema_version: int = Field(ge=1)
    scenario_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    title: str = Field(min_length=1)
    risk_category: RiskCategory | None = None
    split: ScenarioSplit
    template_family_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    allocation_slot_id: str | None = Field(default=None, pattern=r"^rbv[12]-f[1-8]-\d{3}$")
    route_tags: tuple[str, ...] = ()
    primary_target_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    case_profiles: dict[str, BenchmarkCaseProfile] = Field(default_factory=dict)
    supported_conditions: tuple[AttackCondition, ...] = Field(min_length=2)
    budgets: BudgetSpec

    @model_validator(mode="after")
    def require_benign_condition(self) -> ScenarioMetadata:
        if AttackCondition.BENIGN not in self.supported_conditions:
            raise ValueError("every scenario must support the benign condition")
        if self.schema_version < 3:
            if self.risk_category is None:
                raise ValueError("schema v1/v2 scenarios require risk_category")
            if not self.route_tags:
                raise ValueError("schema v1/v2 scenarios require route_tags")
            if self.template_family_id is not None or self.allocation_slot_id is not None:
                raise ValueError("schema v1/v2 scenarios cannot bind v3 authorship metadata")
        else:
            if not self.case_profiles:
                raise ValueError("schema v3 scenarios require case_profiles")
            if self.primary_target_id is None:
                raise ValueError("schema v3 scenarios require one primary_target_id")
            if self.template_family_id is None:
                raise ValueError("schema v3 scenarios require one template_family_id")
            if self.split is ScenarioSplit.TEST and self.allocation_slot_id is None:
                raise ValueError("schema v3 test scenarios require one allocation_slot_id")
            if self.split is ScenarioSplit.DEV and self.allocation_slot_id is not None:
                raise ValueError("schema v3 development scenarios cannot consume formal slots")
        return self


class ScenarioDefinition(StrictModel):
    metadata: ScenarioMetadata
    task: TaskSpec
    policy: PolicySpec
    verifier: VerifierSpec
    routes: ReferenceRoutes
    graph: CandidateGraph | None = None

    @model_validator(mode="after")
    def require_attack_routes_and_verifiers(self) -> ScenarioDefinition:
        target_ids = set(self.policy.target_ids)
        missing_routes = target_ids - set(self.routes.attack)
        missing_verifiers = target_ids - set(self.verifier.attack)
        unknown_routes = set(self.routes.attack) - target_ids
        unknown_verifiers = set(self.verifier.attack) - target_ids
        if missing_routes or unknown_routes:
            raise ValueError(
                "attack routes must match forbidden goals: "
                f"missing={sorted(missing_routes)}, unknown={sorted(unknown_routes)}"
            )
        if missing_verifiers or unknown_verifiers:
            raise ValueError(
                "attack verifiers must match forbidden goals: "
                f"missing={sorted(missing_verifiers)}, unknown={sorted(unknown_verifiers)}"
            )
        if self.metadata.schema_version >= 3:
            if not self.policy.targets:
                raise ValueError("schema v3 scenarios must declare policy.targets explicitly")
            profile_ids = set(self.metadata.case_profiles)
            if profile_ids != target_ids:
                raise ValueError(
                    "case profiles must match forbidden targets: "
                    f"missing={sorted(target_ids - profile_ids)}, "
                    f"unknown={sorted(profile_ids - target_ids)}"
                )
            if self.metadata.primary_target_id not in target_ids:
                raise ValueError("primary_target_id must name one declared forbidden target")
            adaptive = AttackCondition.ADAPTIVE_BLACKBOX in self.metadata.supported_conditions
            targets = {target.target_id: target for target in self.policy.targets}
            for target_id, profile in self.metadata.case_profiles.items():
                target = targets[target_id]
                if profile.target_composition.effect_count != len(target.effect_goal_ids):
                    raise ValueError(
                        f"case profile {target_id!r} target composition does not match "
                        "its component effect count"
                    )
                action_count = len(self.routes.attack[target_id].actions)
                if not profile.route_length.accepts(action_count):
                    raise ValueError(
                        f"case profile {target_id!r} route length band does not accept "
                        f"{action_count} actions"
                    )
                has_adaptive_tags = (
                    RouteTopology.CONDITIONAL_ADAPTIVE in profile.route_topologies
                    or any(
                        mechanism is not AttackMechanism.FIXED
                        for mechanism in profile.attack_mechanisms
                    )
                )
                if adaptive != has_adaptive_tags:
                    raise ValueError(
                        f"case profile {target_id!r} adaptive tags must match the "
                        "adaptive_blackbox supported condition"
                    )
        if self.metadata.schema_version < 4:
            if self.graph is not None or self.routes.certificates is not None:
                raise ValueError("candidate graphs and path certificates require schema v4")
        else:
            if self.graph is None or self.routes.certificates is None:
                raise ValueError("schema v4 scenarios require a graph and path certificates")
            if self.graph.max_path_length > self.metadata.budgets.max_tool_executions:
                raise ValueError("candidate graph max_path_length exceeds the tool budget")
            certificate_targets = set(self.routes.certificates.attack)
            if certificate_targets != target_ids:
                raise ValueError(
                    "attack path certificates must match forbidden targets: "
                    f"missing={sorted(target_ids - certificate_targets)}, "
                    f"unknown={sorted(certificate_targets - target_ids)}"
                )
            safe_actions = self.graph.actions_for_path(self.routes.certificates.safe.edge_ids)
            if safe_actions != self.routes.safe.actions:
                raise ValueError("safe path certificate does not match the safe reference route")
            for target_id, certificate in self.routes.certificates.attack.items():
                attack_actions = self.graph.actions_for_path(certificate.edge_ids)
                if attack_actions != self.routes.attack[target_id].actions:
                    raise ValueError(
                        f"attack path certificate {target_id!r} does not match its reference route"
                    )
            if self.routes.edge_route_costs:
                graph_edge_ids = {edge.edge_id for edge in self.graph.edges}
                cost_edge_ids = set(self.routes.edge_route_costs)
                if cost_edge_ids != graph_edge_ids:
                    raise ValueError(
                        "edge_route_costs must cover exactly the candidate graph edges: "
                        f"missing={sorted(graph_edge_ids - cost_edge_ids)}, "
                        f"unknown={sorted(cost_edge_ids - graph_edge_ids)}"
                    )
        return self
