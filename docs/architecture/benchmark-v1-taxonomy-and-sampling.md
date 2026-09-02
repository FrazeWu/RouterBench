# RouteBench v1 Taxonomy and Sampling Contract

Status: taxonomy, 776-case precision contract, F/A/U compatibility, and held-out
template-family split frozen on 2026-08-31. Individual cases are authored manually.

This document supersedes the legacy three-category, 12-scenario development Pilot as
the design contract for the formal RouteBench v1 inventory. The legacy scenarios remain
useful development fixtures, but they are not silently relabeled as formal v1 cases.

## 1. Authorship and Scope

Every formal scenario, forbidden effect, target composition, verifier, reference route,
and minimum-authority claim is manually authored and reviewed. A model never generates
benchmark items. Models may generate plans or actions only while a frozen case is being
evaluated.

RouteBench v1 covers digital software systems: data, credentials, files, code, policy,
identity, logs, cloud resources, services, automation, and external digital channels.
Payments, medical devices, robots, and other physical or domain-specialized effects are
out of scope. Tools are typed deterministic simulations; arbitrary shell and real network
access are out of scope for formal v1.

The counting units are distinct:

```text
scenario file = one initial state and ordinary task
benchmark case = scenario file x assigned forbidden target
experiment runs = cases x planners x controllers x conditions x feedback x seeds
```

Seeds are repeated observations. They never increase the independent benchmark-case
count.

## 2. Forbidden Targets

A scenario declares atomic forbidden effects and one or more assigned targets. A target
contains one, two, or three atomic effects:

- `g1_atomic`;
- `g2_two_effects`;
- `g3_three_effects`.

The main atomic analysis assigns one target per run. Compound targets form a separately
reported challenge track and succeed only when every component effect is observed by
trusted state assertions.

The eight forbidden-effect families are:

| Code | Family |
|---|---|
| F1 | unauthorized observation |
| F2 | unauthorized transfer |
| F3 | unauthorized modification |
| F4 | destruction or disruption |
| F5 | privilege or identity manipulation |
| F6 | audit or evidence manipulation |
| F7 | persistence or supply-chain influence |
| F8 | unauthorized external action |

These are effects, not attack techniques. Prompt injection, tool substitution, action
splitting, and denial-aware rerouting are mechanism labels.

## 3. Coverage Axes

Each target case has one primary label and one or more complete tags where an axis may
be multi-label. The primary label is the disjoint grouping variable used for coverage
and stratified reporting.

Each schema v3 scenario also declares exactly one `primary_target_id`. That
scenario-target pair is the independent formal sampling unit. Other targets in the same
scenario are secondary cases and do not increase the precision denominator.

### 3.1 Assets

| Code | Asset |
|---|---|
| A1 | user and business data |
| A2 | credentials and secrets |
| A3 | files, code, and artifacts |
| A4 | configuration and policy |
| A5 | identities and permissions |
| A6 | logs and audit evidence |
| A7 | compute and cloud resources |
| A8 | external channels and accounts |

### 3.2 Benign-task coupling

| Code | Coupling |
|---|---|
| R0 | tool, resource, and data independent |
| R1 | shared tool |
| R2 | shared resource with different operation or scope |
| R3 | shared intermediate dataflow |
| R4 | legitimate common prefix followed by forbidden divergence |

### 3.3 Reference-route length

| Code | Executed tool actions |
|---|---:|
| L1 | 2 |
| L2 | 3 |
| L3 | 4-5 |

Every action must be necessary. Removing one action must prevent functional success or
the assigned forbidden target. Six-action and longer optimal routes are out of scope for
v1.

### 3.4 Route topology

| Code | Topology |
|---|---|
| T0 | ordered actions without data dependency |
| T1 | producer-consumer chain |
| T2 | tool or resource revisit |
| T3 | fan-in or fan-out dataflow |
| T4 | conditional branch or adaptive reroute |

T0-T3 describe committed programs. T4 is used by the adaptive track. T3 requires named
observation references rather than an implicit previous-observation-only binding.

### 3.5 Permission dimensions

Formal v1 authority is the constrained product:

```text
subject x operation x resource_scope x data_scope
        x destination x purpose x path_state x quota
```

| Code | Permission dimension |
|---|---|
| P1 | subject and tenant |
| P2 | operation |
| P3 | resource scope |
| P4 | data scope and sensitivity |
| P5 | destination or trust boundary |
| P6 | task purpose |
| P7 | path and temporal state |
| P8 | quantity and resource budget |

The legacy `(resource, operation, scope)` authority triple remains supported only for
schema v2 development scenarios.

### 3.6 Typed tool surfaces

| Code | Tool surface |
|---|---|
| U1 | database |
| U2 | filesystem |
| U3 | secrets and environment |
| U4 | configuration and policy |
| U5 | network and messaging |
| U6 | logging and audit |
| U7 | code, artifact, and package systems |
| U8 | identity and access management |
| U9 | cloud control plane |
| U10 | services and automation |

### 3.7 Attack mechanisms

| Code | Mechanism |
|---|---|
| M0 | fixed program control |
| M1 | parameter or scope substitution |
| M2 | equivalent-tool substitution |
| M3 | action decomposition and intermediate staging |
| M4 | reordering or delayed trigger |
| M5 | authorization-state manipulation |

Every adaptive case includes M0 and at least one of M1-M5. Fixed and adaptive runs share
the same initial program, state, target, planner, controller, feedback, budget, and seed.
Committed or executed prefixes are immutable.

### 3.8 Effect-asset-tool compatibility

Primary F/A/U labels must pass all three manually reviewed allowlists:

```text
(F, A) is allowed
AND (F, U) is allowed
AND (A, U) is allowed
```

The frozen factorized matrix is stored in
`configs/benchmark/v1-compatibility.yaml`. Factorization keeps each decision auditable
without treating all 640 theoretical triples as meaningful. It currently defines the
semantically valid candidate pool; it does not generate scenario content.

## 4. Feedback Conditions

Feedback is an experiment condition, not a benchmark-case category:

| Code | Public denial feedback | Existing runtime mapping |
|---|---|---|
| B0 | disposition only | `status_only` |
| B1 | failed permission dimension | `minimal` |
| B2 | exact public constraint that failed | `full` |

No mode exposes controller-private reasoning, hidden fixture state, raw secrets, or a
reference route. Allowed actions return their ordinary typed tool observations.

## 5. Reference-route Requirements

Every target has one evaluator-owned unique least-authority JointSuccess route under no
authorization. It completes the ordinary task before realizing the assigned forbidden
target. Route validity is established by state assertions, not by textual trace matching.

For every case, P0 must establish:

1. the safe route reaches FunctionalSuccess and PolicyCompliance;
2. the target route reaches FunctionalSuccess and every assigned forbidden effect;
3. removing any target-route action breaks one of those outcomes;
4. no route inside the declared search bound succeeds with less authority;
5. any discovered equal-cost alternative is eliminated by redesign or explicitly
   registered before the case is frozen;
6. reset, positive-control, negative-control, and evidence-freezing checks pass.

## 6. Schema and Aggregate Auditing

Schema v3 explicitly declares atomic effects, assigned targets, and a case profile for
every target. The profile's target cardinality and route-length band are checked against
the actual declaration and reference route. Adaptive tags must agree with the scenario's
supported conditions.

Use aggregate inventory reporting without rendering scenario contents:

```bash
routebench scenario inventory scenarios
```

The frozen sampling contract can be audited directly:

```bash
routebench scenario inventory scenarios \
  --sampling-contract configs/benchmark/v1-sampling.yaml \
  --compatibility-contract configs/benchmark/v1-compatibility.yaml \
  --split-contract configs/benchmark/v1-splits.yaml
```

The bound uses scenario-target cases as independent units. It does not count seeds,
models, controllers, or feedback modes as additional samples.

## 7. Determining the Formal Case Count

The formal precision contract is:

```text
8 primary forbidden-effect strata
x 97 independent scenario-primary-target cases per stratum
= 776 formal primary cases
```

This is the worst-case normal-approximation bound for a binary proportion at 95%
confidence and a +/-10 percentage-point margin within each effect family, using
`expected_rate = 0.5`. Seeds, planners, controllers, feedback conditions, legacy
scenarios, and secondary targets do not count toward 776.

The compatibility contract admits 236 primary F/A/U triples. Every allowed triple is
reserved at least twice, consuming 472 slots. The remaining 304 slots complete the
97-case quota within each F family while balancing R/L/T/P/M/G labels. The allocator is
deterministic, uses no model or random generator, and emits metadata slots only. It does
not create tasks, prompts, fixtures, attack payloads, or reference routes.

The aggregate inventory command reports the allocation digest and structural counts when
both contracts are supplied. It never renders the individual slots or scenario contents.
A full Cartesian product remains prohibited. If a future compatibility contract cannot
fit its required per-triple repetitions within an effect family's 97 slots, allocation
fails explicitly; the formal inventory must then grow rather than weakening coverage.

## 8. Held-Out Template-Family Split

The 776 formal primary cases are all `split: test`; development cases are additional
non-formal cases and never consume a formal slot. RouteBench freezes 8 development
template families and 16 held-out test families in `configs/benchmark/v1-splits.yaml`.
Formal slots are distributed across the 16 test families with a global count spread of
at most one case.

The split unit is the semantic workflow family, not the scenario name or fixture. A
renamed task, substituted entity, changed constant, or reskinned fixture remains in the
same family. Controllers, planner prompts, attacks, and verifiers may be tuned only on
development families. Formal test content cannot be used for training, calibration,
prompt selection, threshold selection, or controller revision.

Every formal scenario declares both a `template_family_id` and its unique
`allocation_slot_id`. The aggregate authorship audit checks the family assignment, all
nine taxonomy labels, duplicate slot use, and remaining unfilled slots without rendering
scenario content.

No formal scenario is emitted by an automatic generator or an evaluated planner, and no
case is derived by merely renaming an existing fixture. Every case is manually specified
and jointly reviewed before it enters the held-out inventory.
