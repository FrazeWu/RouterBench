"""Compatibility contract for manually authored F x A x U case triples."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from routebench.scenarios.loader import ScenarioBundle
from routebench.scenarios.schema import ScenarioSplit
from routebench.scenarios.taxonomy import AssetType, ForbiddenEffectFamily, ToolSurface


class CompatibilityContract(BaseModel):
    """Factorized allowlist for primary effect, asset, and tool labels."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    minimum_primary_cases_per_allowed_triple: int = Field(gt=0)
    effect_assets: dict[ForbiddenEffectFamily, tuple[AssetType, ...]] = Field(min_length=1)
    effect_tools: dict[ForbiddenEffectFamily, tuple[ToolSurface, ...]] = Field(min_length=1)
    asset_tools: dict[AssetType, tuple[ToolSurface, ...]] = Field(min_length=1)

    @model_validator(mode="after")
    def require_complete_unique_allowlists(self) -> Self:
        if set(self.effect_assets) != set(ForbiddenEffectFamily):
            raise ValueError("effect_assets must declare every forbidden-effect family")
        if set(self.effect_tools) != set(ForbiddenEffectFamily):
            raise ValueError("effect_tools must declare every forbidden-effect family")
        if set(self.asset_tools) != set(AssetType):
            raise ValueError("asset_tools must declare every asset type")
        for name, mapping in (
            ("effect_assets", self.effect_assets),
            ("effect_tools", self.effect_tools),
            ("asset_tools", self.asset_tools),
        ):
            for key, values in mapping.items():
                if not values:
                    raise ValueError(f"{name}[{key.value}] must not be empty")
                if len(values) != len(set(values)):
                    raise ValueError(f"{name}[{key.value}] must not contain duplicates")
        for effect in ForbiddenEffectFamily:
            if not any(
                self.allows(effect, asset, tool)
                for asset in AssetType
                for tool in ToolSurface
            ):
                raise ValueError(f"{effect.value} must admit at least one asset-tool pair")
        return self

    def allows(
        self,
        effect: ForbiddenEffectFamily,
        asset: AssetType,
        tool: ToolSurface,
    ) -> bool:
        return (
            asset in self.effect_assets[effect]
            and tool in self.effect_tools[effect]
            and tool in self.asset_tools[asset]
        )

    @property
    def allowed_triple_count(self) -> int:
        return sum(
            self.allows(effect, asset, tool)
            for effect in ForbiddenEffectFamily
            for asset in AssetType
            for tool in ToolSurface
        )

    @property
    def minimum_required_primary_cases(self) -> int:
        return self.allowed_triple_count * self.minimum_primary_cases_per_allowed_triple


def load_compatibility_contract(path: str | Path) -> CompatibilityContract:
    contract_path = Path(path).expanduser().resolve(strict=True)
    with contract_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"compatibility contract must contain a YAML mapping: {contract_path}")
    return CompatibilityContract.model_validate(raw)


def audit_inventory_compatibility(
    bundles: tuple[ScenarioBundle, ...], contract: CompatibilityContract
) -> dict[str, object]:
    """Report aggregate compatibility without exposing scenario or target identities."""
    primary_checked = 0
    primary_compatible = 0
    development_primary_checked = 0
    development_primary_compatible = 0
    secondary_checked = 0
    secondary_compatible = 0
    primary_incompatible_by_effect: Counter[str] = Counter(
        {effect.value: 0 for effect in ForbiddenEffectFamily}
    )
    primary_triple_counts: Counter[
        tuple[ForbiddenEffectFamily, AssetType, ToolSurface]
    ] = Counter()

    for bundle in bundles:
        metadata = bundle.definition.metadata
        if metadata.schema_version < 3:
            continue
        for target_id, profile in metadata.case_profiles.items():
            compatible = contract.allows(
                profile.primary_effect_family,
                profile.primary_asset_type,
                profile.primary_tool_surface,
            )
            if target_id == metadata.primary_target_id:
                if metadata.split is ScenarioSplit.DEV:
                    development_primary_checked += 1
                    development_primary_compatible += int(compatible)
                    continue
                primary_checked += 1
                primary_compatible += int(compatible)
                if compatible:
                    primary_triple_counts[
                        (
                            profile.primary_effect_family,
                            profile.primary_asset_type,
                            profile.primary_tool_surface,
                        )
                    ] += 1
                else:
                    primary_incompatible_by_effect[profile.primary_effect_family.value] += 1
            else:
                secondary_checked += 1
                secondary_compatible += int(compatible)

    minimum = contract.minimum_primary_cases_per_allowed_triple
    triples_meeting_minimum = 0
    replication_deficit_total = 0
    replication_deficit_by_effect: Counter[str] = Counter(
        {effect.value: 0 for effect in ForbiddenEffectFamily}
    )
    for effect in ForbiddenEffectFamily:
        for asset in AssetType:
            for tool in ToolSurface:
                if not contract.allows(effect, asset, tool):
                    continue
                observed = primary_triple_counts[(effect, asset, tool)]
                if observed >= minimum:
                    triples_meeting_minimum += 1
                    continue
                deficit = minimum - observed
                replication_deficit_total += deficit
                replication_deficit_by_effect[effect.value] += deficit

    has_incompatible_cases = (
        primary_checked != primary_compatible or secondary_checked != secondary_compatible
    )
    status = (
        "incompatible"
        if has_incompatible_cases
        else "complete"
        if replication_deficit_total == 0
        else "undercovered"
    )
    return {
        "status": status,
        "allowed_primary_triples": contract.allowed_triple_count,
        "minimum_primary_cases_per_allowed_triple": minimum,
        "minimum_required_triple_coverage_cases": contract.minimum_required_primary_cases,
        "triples_meeting_minimum": triples_meeting_minimum,
        "primary_replication_deficit": replication_deficit_total,
        "primary_replication_deficit_by_effect": dict(
            sorted(replication_deficit_by_effect.items())
        ),
        "primary_cases_checked": primary_checked,
        "compatible_primary_cases": primary_compatible,
        "incompatible_primary_cases": primary_checked - primary_compatible,
        "development_primary_cases_checked": development_primary_checked,
        "compatible_development_primary_cases": development_primary_compatible,
        "incompatible_development_primary_cases": (
            development_primary_checked - development_primary_compatible
        ),
        "secondary_cases_checked": secondary_checked,
        "compatible_secondary_cases": secondary_compatible,
        "incompatible_secondary_cases": secondary_checked - secondary_compatible,
        "primary_incompatible_by_effect": dict(sorted(primary_incompatible_by_effect.items())),
    }
