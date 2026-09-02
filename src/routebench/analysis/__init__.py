"""Aggregate RouteBench coverage and result analysis."""

from routebench.analysis.allocation import (
    PrimaryCaseSlot,
    allocate_primary_case_slots,
    summarize_primary_case_allocation,
)
from routebench.analysis.compatibility import (
    CompatibilityContract,
    audit_inventory_compatibility,
    load_compatibility_contract,
)
from routebench.analysis.coverage import (
    FormalSamplingContract,
    PrimaryCoverageAxis,
    audit_inventory_against_sampling_contract,
    estimate_binomial_cases_per_stratum,
    estimate_total_independent_cases,
    load_sampling_contract,
    summarize_benchmark_inventory,
)
from routebench.analysis.split import (
    BenchmarkSplitContract,
    TemplateFamilyAssignment,
    TemplateFamilySpec,
    allocate_template_families,
    audit_formal_authorship,
    load_split_contract,
    summarize_template_family_allocation,
)

__all__ = [
    "BenchmarkSplitContract",
    "CompatibilityContract",
    "FormalSamplingContract",
    "PrimaryCaseSlot",
    "PrimaryCoverageAxis",
    "TemplateFamilyAssignment",
    "TemplateFamilySpec",
    "allocate_primary_case_slots",
    "allocate_template_families",
    "audit_formal_authorship",
    "audit_inventory_against_sampling_contract",
    "audit_inventory_compatibility",
    "estimate_binomial_cases_per_stratum",
    "estimate_total_independent_cases",
    "load_compatibility_contract",
    "load_sampling_contract",
    "load_split_contract",
    "summarize_benchmark_inventory",
    "summarize_primary_case_allocation",
    "summarize_template_family_allocation",
]
