# Scenario Schema v3

Schema v4 adds the candidate-graph planning contract documented in
`docs/schemas/scenario-v4.md`. This file remains the taxonomy contract inherited by v4.

Schema v3 extends the executable v2 scenario with explicit atomic effects, assigned
single or compound targets, and auditable taxonomy profiles. Existing v2 development
scenarios remain loadable but do not count toward v3 taxonomy coverage.

`policy.yaml` separates atomic effects from assigned targets:

```yaml
forbidden_effects:
  - goal_id: observe_protected_value
    description: Observe a protected value.
    resource: secret-store
    operation: read
    scope: protected-value
    protected_labels: [protected]

targets:
  - target_id: assigned_observation_target
    effect_goal_ids: [observe_protected_value]
```

A compound target lists two or three atomic `effect_goal_ids`. Its attack verifier must
require every component effect.

`scenario.yaml` contains one profile for every target ID. This example is structural;
it is not a benchmark item or fixture:

```yaml
schema_version: 3
scenario_id: manually_authored_dev_001
title: Manually authored development scenario
split: dev
template_family_id: tf_dev_single_record_report
primary_target_id: assigned_observation_target
supported_conditions: [benign, fixed, adaptive_blackbox]

case_profiles:
  assigned_observation_target:
    target_composition: g1_atomic
    primary_effect_family: f1_unauthorized_observation
    effect_families: [f1_unauthorized_observation]
    primary_asset_type: a2_credentials_secrets
    asset_types: [a2_credentials_secrets]
    coupling: r0_independent
    route_length: l1_two_actions
    primary_topology: t4_conditional_adaptive
    route_topologies: [t0_order_only, t4_conditional_adaptive]
    primary_permission_dimension: p4_data_scope
    permission_dimensions: [p4_data_scope]
    primary_tool_surface: u3_secrets_environment
    tool_surfaces: [u3_secrets_environment]
    primary_attack_mechanism: m1_parameter_scope_substitution
    attack_mechanisms: [m0_fixed, m1_parameter_scope_substitution]
```

The loader rejects:

- targets that reference undeclared atomic effects;
- route, verifier, or profile keys that do not exactly match target IDs;
- a missing or undeclared `primary_target_id`;
- a v3 scenario without a `template_family_id`;
- a formal `split: test` scenario without an `allocation_slot_id`, or a development
  scenario that attempts to consume a formal slot;
- a G1/G2/G3 label inconsistent with one/two/three component effects;
- an L1/L2/L3 label inconsistent with the reference action count;
- adaptive tags without `adaptive_blackbox`, or `adaptive_blackbox` without an adaptive
  topology or M1-M5 mechanism;
- duplicate tags or a primary label absent from its complete tag list;
- any case profile that omits the M0 fixed control.

After loading, the formal inventory audit additionally rejects primary F/A/U triples
that are absent from `configs/benchmark/v1-compatibility.yaml`. This compatibility rule
is versioned separately from the structural schema.

All 776 formal cases use `split: test`. Each binds exactly one `rbv1-fN-NNN`
`allocation_slot_id` and one held-out test family from
`configs/benchmark/v1-splits.yaml`. Schema-v3 development cases remain valid but are
reported separately and never count toward the 776-case precision denominator. Renamed
or parameter-substituted variants remain in their original semantic template family.

The five-file layout, deterministic fixture hashing, trusted tool registry, and state
assertion rules remain the same as v2.
