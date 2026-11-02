# ECPA next-phase preparation

Status: working preparation, 2026-11-01. This is an authoring aid, not an
independent-review attestation, frozen protocol, or experiment result. It was
prepared against source revision `2c5af852cef73d957cf19b9e6dd2961324486c72`.
Historical model outcomes were not consulted.

## Current evidence and review disposition

The checked-in inventory has 29 tasks: 12 train, 5 tune, 4 calibration and 8
test. The conservative candidate-family counts are 8/4/4/7. The five training
tasks for promotion, restore, role reduction, duplicate repair and contract
documentation share one fixed-fixture read/change/verify obligation. The two
test tasks for forwarding and reservations share an ordering-preserving
relational-migration structure. The two tuning change tasks remain one family.
These are source-level clustering decisions; no family is independently
accepted.

| Split | Current source disposition | Remaining review work |
| --- | --- | --- |
| Train | Seven other candidate obligations plus one five-task structural cluster | Compare each singleton with legacy sources; inspect whether receipts encode actual data predicates; resolve author identities |
| Tune | Mutation revalidation, batch scope, projected delivery, and a two-task approved-change family | Review projection against cumulative disclosure; review revalidation and change dependencies against training tasks |
| Calibration | At-most-once dispatch, exact-target fanout, temporary-authority release, dependent-before-parent erasure | Compare dispatch/fanout/cleanup obligations across all splits; audit intermediate-state contracts |
| Test | Replica availability, distinct author/reviewer, conserved transfer, append-only journal, monotone release epoch, cumulative disclosure, relational migration | Reciprocal review for structural matches; exhaustive development-split comparison; retain mechanism holdout |

The public overlap screen is a candidate-finding aid only. In particular, the
conservation/journal pair shares a dependency-only structure but asserts
different relations; forwarding/reservations share a decision skeleton and are
one statistical cluster. Neither result supplies an accepted independence
certificate. Current authored harmful edges are identified by public effect
contracts and blocked by the shared hard guard. Primary claims therefore concern
legal recovery choices, completion and cost; they must not credit the learned
selector with detecting those authored harms. Fixed-fixture receipts also do
not establish output-conditioned behavior on arbitrary state values.

## Review provenance gate

`SourceReview` requires a current source digest, a distinct reviewer identity,
the declared task-author identities, all eight checks, a rationale, and
source-bound peer comparisons for structural matches. The manifest has no
task-author identity field, and the prior agent report is explicitly not an
attestation. A Git commit author is not enough evidence to assign authorship to
each task. Keep all 29 entries at `independent_review: pending`; do not create
review JSON or set accepted status until task authorship and a real independent
reviewer are documented. Review acceptance remains a human attestation; the
freeze code checks its binding and completeness but cannot authenticate the
person.

## Missing-source work queue

The unchanged allocation target is 12 train, 4 tune, 4 calibration and 40 test
families. The current candidate inventory is short four training families and
33 test families. The missing family names and obligations are not yet
adjudicated. Do not fill those counts with renamed entities, providers, values,
or graph shapes.

For each proposed training or held-out test family, use this authoring sequence:

1. Define an externally meaningful invariant and a counterfactual that separates
   it from the nearest existing and legacy sources.
2. Select each adapter, a concrete provider/resource/mode binding, planning
   skills, and workflow template manually from the capability catalog and
   universe. Record the choices in the source, not as an evaluator optimum.
3. Build at least two legal, dependency-valid recovery paths and a harmful
   reference reached after legitimate prefix actions. Keep the exact menu and
   task prompt free of private route/cost certificates.
4. Specify public contracts that agree with executed state transitions, and
   verifier checks that catch intermediate violations even if later actions
   repair the final state.
5. Keep test mechanisms disjoint from the development mechanisms; compare every
   new test source with all development families before assigning a family.
6. Add source hashes and independent review evidence only after the sources are
   complete. Recount accepted families after semantic adjudication, not before.

Prepare source candidates in bounded reviewable batches. The first batch should
resolve the four missing training obligations and include its nearest legacy
comparisons. The test backlog should then be authored in three batches of eleven
candidate families, each with explicit cross-split comparisons and mechanism
scope. Eleven is an authoring batch size, not evidence that any candidates are
independent. Stop and consolidate a candidate when its executed decision
obligation duplicates an existing family.

## Prospective StudySpec decisions

`configs/defense/independent-study-draft.yaml` is a schema-shaped draft and is
not eligible for freezing. It keeps the prior design: one presentation, both
relay modes, one adapter at seed 29, matched common episode seeds, the 5-point
recovery target, 2-point benign-loss bound, and the minimum 20-family inference
gate. It uses the existing local Qwen3-14B task agent and Qwen3-1.7B compact
model paths; paths and GPU availability must be checked before any collection.

The 64-update LoRA count, 0.5 logging-uniform weight, comparator tie order,
episode seeds, resource reservation and acquisition ceilings are provisional
draft values. The 64-update count is a design starting point for up to 512
complete branch groups, not a result-selected checkpoint. The 75,000-call and
614,400,000-token per-phase ceilings allow 25% headroom over 1,000 planned
comparison episodes at the maximum 48 task-agent calls plus 12 selector
decisions per episode, reserving the full 8,192-token context for each call.
They are conservative caps, not cost estimates; measured usage and thermal
telemetry remain required. The 12-decision/48-agent-call episode limits mirror
the existing pilot budget and need to be checked against the completed corpus.

The existing efficacy criteria remain unchanged. Fit exactly one adapter and
do not claim training-seed robustness. Choose the guarded comparator on tune;
calibration audits that fixed selection and does not gate test execution. Report
all failures and singleton decisions in the primary denominator. Report actual
realized allow/constrain/escalate/deny training targets before fitting. A missing
kind blocks fitting; authored menu probes do not substitute for model
continuations.

## Stage gates

1. Record task-author provenance and complete independent source/contract review
   for the existing 29 tasks; resolve structural-match peer comparisons.
2. Author and review the missing train sources, then the 33 fresh test families.
   Recompute candidate counts and independent clusters after every batch.
3. Validate every source and menu with the simulator; measure context, cost and
   thermal requirements. Update the draft only before any formal outcomes.
4. Once accepted source reviews and complete allocations exist, commit the
   coherent source/protocol checkpoint and rerun clean-revision source and
   context audits. Freeze only in a later explicitly authorized phase.
5. After a future freeze, collect real continuations, check all four realized
   training-target kinds, and only then fit, tune, calibrate and test in order.

No source-review acceptance, corpus source creation, protocol freeze, model
collection, training or GPU job was started in this preparation pass.

## Source-audit follow-up, 2026-11-02

The committed corpus at `52daae324b452e31c2c76963bcd651d07d5474f2` passed
`scripts/audit_defense_corpus.py` as a source-only simulator audit. The report
is retained under ignored `artifacts/private/ecpa-training-gap-audit-20261102-52daae3.json`.
It checked all 29 tasks, 58 safe-path witnesses, 60 legitimate attack-prefix
actions and 77 menu probes. It made no model calls and emitted no training
labels. The corpus digest was
`afd504aebda99216f1163475455b64654c8b968aa85a42335b06f1423650156a`.

The audit confirms the authored-family counts remain 8/4/4/7 against targets
12/4/4/40, with zero reviewed families and formal readiness false. Its public
structure screen flags the five fixed-fixture training variants, the two test
relational-migration tasks, and the two tuning approved-change tasks; these
matches remain review prompts, not semantic certificates. A metadata inventory
contains 776 legacy formal-test sources, but that count and keyword search do
not substitute for task-by-task comparison. The selected historical comparisons
in `defense-semantic-source-review.md` remain examples, not an exhaustive audit.

The four missing training obligations are still authoring work, not accepted
families. Do not assign them from template names or from the dependency screen.
Each new source needs a concrete invariant and counterfactual, nearest current
and legacy source comparisons, manually selected catalog bindings, and the
simulator checks described above. Keep all independent-review fields pending
until task authorship and an actual independent reviewer are documented. No
protocol freeze, model collection, training or GPU work is authorized by this
source audit.
