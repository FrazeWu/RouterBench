"""Declarative scenario schemas and loading."""

from routebench.scenarios.loader import ScenarioBundle, load_scenario
from routebench.scenarios.schema import (
    AuthorityAtom,
    CandidateGraph,
    CapabilityBindingSpec,
    ForbiddenTarget,
    GraphEdgeSpec,
    GraphNodeSpec,
    GraphPathSpec,
    ReferenceRoutes,
    ScenarioDefinition,
    ScenarioSplit,
)
from routebench.scenarios.taxonomy import (
    AssetType,
    AttackMechanism,
    BenchmarkCaseProfile,
    DenialFeedbackLevel,
    ForbiddenEffectFamily,
    PermissionDimension,
    RouteLengthBand,
    RouteTopology,
    TargetComposition,
    TaskGoalCoupling,
    ToolSurface,
)

__all__ = [
    "AssetType",
    "AttackMechanism",
    "AuthorityAtom",
    "BenchmarkCaseProfile",
    "CandidateGraph",
    "CapabilityBindingSpec",
    "DenialFeedbackLevel",
    "ForbiddenEffectFamily",
    "ForbiddenTarget",
    "GraphEdgeSpec",
    "GraphNodeSpec",
    "GraphPathSpec",
    "PermissionDimension",
    "ReferenceRoutes",
    "RouteLengthBand",
    "RouteTopology",
    "ScenarioBundle",
    "ScenarioDefinition",
    "ScenarioSplit",
    "TargetComposition",
    "TaskGoalCoupling",
    "ToolSurface",
    "load_scenario",
]
