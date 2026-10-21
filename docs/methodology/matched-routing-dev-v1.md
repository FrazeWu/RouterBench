# Matched routing development diagnostic v1

One manually selected development task, adapted from the existing public-contract
timeout repair example. This is a material/oracle smoke test, not new 776-case
evidence, and no model inference is started by preparation.

## Manual choices and conditions

The design in `configs/experiments/matched-routing-dev-v1.yaml` explicitly chooses
registered provider-resource-mode bindings, primitive adapters, planning skills and
the `production_bugfix` workflow from `catalog/capability_universe.yaml`. Every
inherited and new graph edge is checked by the runtime-binding validator. The
executor registry alone cannot authorize a provider-resource combination.

Three conditions share the same public task, fixtures, forbidden effects, verifier,
reference edge certificates and unique public-exact optimum. No selected reference
route or private cost label is included in the public task prompt.

| Condition | Edges | Bounded terminal paths | Safe functional paths | Public-exact optima |
|---|---:|---:|---:|---:|
| Base | 20 | 113 | 48 | 1 |
| Alternatives expanded | 24 | 366 | 180 | 1 |
| Dependencies active | 20 | 113 | 32 | 1 |

- **Alternatives**: adds manually selected source, runtime, configuration and
  verification options. Every base path remains available with identical execution
  outcomes. Added branches create viable nonoptimal alternatives; the optimal
  answer set does not change. Candidate multiplicity, prompt length and unsafe-path
  count increase together, so this is not an isolated effect of a scalar path count.
- **Dependencies**: keeps graph topology fixed but requires source-matched evidence
  before configuration changes. A mirror-source prefix can join a later state,
  but fails the active requirement. Sixteen previously functional paths become
  nonfunctional; 36 common-path outcomes change in total. All nonprobe outcomes
  and the unique optimum remain unchanged. The verifier is fixed, but eligibility
  changes intentionally: report that mechanism rather than claiming all labels
  are identical.

Public attributes make lower-exposure, narrower-scope evidence preferable; the
reference is checked only after multiple viable dependency-constrained paths exist.
All conditions retain executable legitimate and forbidden-effect witness paths.
Dependencies are executed by trusted in-memory adapters, not inferred from edge
distance or a proxy count of nonfunctional routes.

## Gates and reproducibility

```bash
PYTHONPATH=src python scripts/prepare_matched_routing_dev.py \
  --output-root artifacts/private/matched-routing-dev-v1-UNIQUE-ID
```

Use a committed clean revision for a frozen materialization or any future inference.
Output directories are immutable. The manifest records source/condition digests,
design/catalog/builder hashes, Git revision and dirty flag. Failed preparations
cannot produce a successful manifest. Nothing writes to the source example or
the held-out formal test scenarios. Generated fixtures remain private and ignored.

Tests reject absent factor changes, unregistered providers, held-out source
derivation and source-overlapping output paths. They verify deterministic digests,
unique unchanged answers and feasibility changes limited to the intended probe.

## Next inference boundary

The first future paired smoke test is Qwen3-8B/14B x three conditions x five
presentation seeds = **30 attempts**. It only checks that the model integration
and measured manipulations work. Five presentation seeds on one task are not five
independent tasks and cannot establish a general causal effect.

Before a paper-scale diagnostic, manually add independent development tasks from
several workflows and effect families under the same predeclared gates. Do not
select variants by model gap or tune the held-out 776 cases. Route-length
manipulation and permission-awareness prompting remain separate, unfinished
experiments; no repeated no-op chain counts as a validated length contrast.
