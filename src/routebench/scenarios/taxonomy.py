"""Frozen RouteBench v1 taxonomy for manually authored benchmark cases."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ForbiddenEffectFamily(StrEnum):
    UNAUTHORIZED_OBSERVATION = "f1_unauthorized_observation"
    UNAUTHORIZED_TRANSFER = "f2_unauthorized_transfer"
    UNAUTHORIZED_MODIFICATION = "f3_unauthorized_modification"
    DESTRUCTION_DISRUPTION = "f4_destruction_disruption"
    PRIVILEGE_IDENTITY_MANIPULATION = "f5_privilege_identity_manipulation"
    AUDIT_EVIDENCE_MANIPULATION = "f6_audit_evidence_manipulation"
    PERSISTENCE_SUPPLY_CHAIN = "f7_persistence_supply_chain"
    UNAUTHORIZED_EXTERNAL_ACTION = "f8_unauthorized_external_action"


class AssetType(StrEnum):
    USER_BUSINESS_DATA = "a1_user_business_data"
    CREDENTIALS_SECRETS = "a2_credentials_secrets"
    FILES_CODE_ARTIFACTS = "a3_files_code_artifacts"
    CONFIGURATION_POLICY = "a4_configuration_policy"
    IDENTITY_PERMISSIONS = "a5_identity_permissions"
    LOGS_AUDIT_EVIDENCE = "a6_logs_audit_evidence"
    COMPUTE_CLOUD_RESOURCES = "a7_compute_cloud_resources"
    EXTERNAL_CHANNELS_ACCOUNTS = "a8_external_channels_accounts"


class TaskGoalCoupling(StrEnum):
    INDEPENDENT = "r0_independent"
    SHARED_TOOL = "r1_shared_tool"
    SHARED_RESOURCE = "r2_shared_resource"
    SHARED_DATAFLOW = "r3_shared_dataflow"
    LEGITIMATE_PREFIX_DIVERGENCE = "r4_legitimate_prefix_divergence"


class RouteLengthBand(StrEnum):
    TWO_ACTIONS = "l1_two_actions"
    THREE_ACTIONS = "l2_three_actions"
    FOUR_TO_FIVE_ACTIONS = "l3_four_to_five_actions"

    def accepts(self, action_count: int) -> bool:
        if self is RouteLengthBand.TWO_ACTIONS:
            return action_count == 2
        if self is RouteLengthBand.THREE_ACTIONS:
            return action_count == 3
        return 4 <= action_count <= 5


class RouteTopology(StrEnum):
    ORDER_ONLY = "t0_order_only"
    PRODUCER_CONSUMER = "t1_producer_consumer"
    TOOL_RESOURCE_REVISIT = "t2_tool_resource_revisit"
    FAN_IN_OR_FAN_OUT = "t3_fan_in_or_fan_out"
    CONDITIONAL_ADAPTIVE = "t4_conditional_adaptive"


class PermissionDimension(StrEnum):
    SUBJECT_TENANT = "p1_subject_tenant"
    OPERATION = "p2_operation"
    RESOURCE_SCOPE = "p3_resource_scope"
    DATA_SCOPE = "p4_data_scope"
    DESTINATION_BOUNDARY = "p5_destination_boundary"
    TASK_PURPOSE = "p6_task_purpose"
    PATH_TEMPORAL_STATE = "p7_path_temporal_state"
    QUOTA_BUDGET = "p8_quota_budget"


class ToolSurface(StrEnum):
    DATABASE = "u1_database"
    FILESYSTEM = "u2_filesystem"
    SECRETS_ENVIRONMENT = "u3_secrets_environment"
    CONFIGURATION_POLICY = "u4_configuration_policy"
    NETWORK_MESSAGING = "u5_network_messaging"
    LOGGING_AUDIT = "u6_logging_audit"
    CODE_ARTIFACT_PACKAGE = "u7_code_artifact_package"
    IDENTITY_ACCESS = "u8_identity_access"
    CLOUD_CONTROL_PLANE = "u9_cloud_control_plane"
    SERVICE_AUTOMATION = "u10_service_automation"


class AttackMechanism(StrEnum):
    FIXED = "m0_fixed"
    PARAMETER_SCOPE_SUBSTITUTION = "m1_parameter_scope_substitution"
    EQUIVALENT_TOOL_SUBSTITUTION = "m2_equivalent_tool_substitution"
    DECOMPOSITION_STAGING = "m3_decomposition_staging"
    REORDER_DELAY = "m4_reorder_delay"
    AUTHORIZATION_STATE_MANIPULATION = "m5_authorization_state_manipulation"


class DenialFeedbackLevel(StrEnum):
    DENIAL_ONLY = "b0_denial_only"
    DIMENSION_REASON = "b1_dimension_reason"
    PUBLIC_CONSTRAINT = "b2_public_constraint"


class TargetComposition(StrEnum):
    ATOMIC = "g1_atomic"
    TWO_EFFECTS = "g2_two_effects"
    THREE_EFFECTS = "g3_three_effects"

    @property
    def effect_count(self) -> int:
        return {
            TargetComposition.ATOMIC: 1,
            TargetComposition.TWO_EFFECTS: 2,
            TargetComposition.THREE_EFFECTS: 3,
        }[self]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _require_unique[EnumT: StrEnum](name: str, values: tuple[EnumT, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicates")


class BenchmarkCaseProfile(_StrictModel):
    """Auditable coverage labels for one evaluator-owned target case."""

    target_composition: TargetComposition
    primary_effect_family: ForbiddenEffectFamily
    effect_families: tuple[ForbiddenEffectFamily, ...] = Field(min_length=1)
    primary_asset_type: AssetType
    asset_types: tuple[AssetType, ...] = Field(min_length=1)
    coupling: TaskGoalCoupling
    route_length: RouteLengthBand
    primary_topology: RouteTopology
    route_topologies: tuple[RouteTopology, ...] = Field(min_length=1)
    primary_permission_dimension: PermissionDimension
    permission_dimensions: tuple[PermissionDimension, ...] = Field(min_length=1)
    primary_tool_surface: ToolSurface
    tool_surfaces: tuple[ToolSurface, ...] = Field(min_length=1)
    primary_attack_mechanism: AttackMechanism
    attack_mechanisms: tuple[AttackMechanism, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_primary_labels(self) -> Self:
        tagged_fields = (
            ("effect_families", self.primary_effect_family, self.effect_families),
            ("asset_types", self.primary_asset_type, self.asset_types),
            ("route_topologies", self.primary_topology, self.route_topologies),
            (
                "permission_dimensions",
                self.primary_permission_dimension,
                self.permission_dimensions,
            ),
            ("tool_surfaces", self.primary_tool_surface, self.tool_surfaces),
            (
                "attack_mechanisms",
                self.primary_attack_mechanism,
                self.attack_mechanisms,
            ),
        )
        for name, primary, values in tagged_fields:
            _require_unique(name, values)
            if primary not in values:
                raise ValueError(f"primary label for {name} must be present in its tag list")
        if AttackMechanism.FIXED not in self.attack_mechanisms:
            raise ValueError("every case profile must include the fixed M0 control")
        return self
