# Scenario Schema v2 (Legacy Development)

Formal RouteBench v1 scenarios use schema v3 as documented in `scenario-v3.md`. This
file remains the compatibility contract for the original 12 development scenarios.

An executable RouteBench scenario is a directory containing five required YAML mappings
and a `fixtures/` tree:

- `scenario.yaml`: identity, split, risk category, supported conditions, and budgets;
- `task.yaml`: user prompt, functional goal, exposed tools, and minimum authority;
- `policy.yaml`: a named set of forbidden effects;
- `verifier.yaml`: deterministic functional, compliance, and per-goal attack assertions;
- `routes.yaml`: evaluator-owned safe and attack reference routes.

YAML files may only contain data. They cannot name arbitrary Python import paths or
embed shell snippets for execution during loading. Assertions and tools are selected by
trusted internal registries.

Each forbidden effect has a unique `goal_id`. A controlled attack run selects one
`target_goal_id`; other forbidden effects that occur are still violations and should be
reported as cross-goal violations by higher-level experiment code.

`scenario.yaml` also declares one or more route tags. The current Pilot requires four
scenarios in each final-effect category and at least two scenarios for every required
route tag. `routebench scenario validate-p0 scenarios` verifies those coverage rules as
well as every evaluator-owned safe and no-authorization attack reference route.

The current P0 reference simulator expects `fixtures/state.json`. It contains only
simulated database rows, files, secrets, labels, and outbound services. It never grants
access to the host filesystem or network.

The loader rejects unknown fields, verifies that attack routes and attack verifiers
cover exactly the declared goal IDs, and computes a SHA-256 over every required file and
fixture using relative paths plus raw bytes. Any scenario change therefore changes its
identity in a run manifest.
