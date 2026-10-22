# Source-bound independent defense study freeze

Status: tooling implemented, 2026-10-23. **No formal protocol is frozen.**
The current corpus has two of forty planned test candidates and no accepted
independent reviews. Formal collection, fitting and efficacy comparison remain
pending. This gate supplies provenance checks, not reviewer attestations.

## Preconditions and identities

The entry point is scripts.freeze_defense_study. It takes a checked-in StudySpec,
an authoring audit and a tokenizer/context audit, then exclusively creates a new
manifest below artifacts/private. It does not start inference, accept a review,
select a checkpoint or overwrite old results. No formal StudySpec is committed
yet: the data, explicit learning recipe and resource plan are still being settled.

The gate requires:

- A clean committed revision and tracked configuration, catalog, task sources
  and review evidence. Supplied objects are compared with freshly loaded sources;
  only the fresh objects enter the frozen payload.
- The exact prespecified family allocation and accepted review for every task.
  A JSON SourceReview binds the four task sources plus its split/family/mechanism
  assignment, avoiding circular dependence on acceptance fields or review paths.
- A reviewer ID different from declared author IDs, nonempty rationale, and pass
  attestations for all eight checks in REVIEW_CHECKS: semantics, legacy comparison,
  contract, isolation, reachability, neutral menu, evaluator and text-operator scope.
  Matching public structures in distinct families require reciprocal peer-source
  dispositions. Same-family variants remain one cluster.
- Fresh source and context evidence for this exact revision/corpus. Context rows
  must match the frozen completion reserves, include the actual operator and
  retained-draft sensitivity checks, and show no overflow. Tokenizer file hashes
  must match both local model snapshots.
- Hashes of both complete local safetensors snapshots, selector input schema,
  actual source files and evidence objects. Changing model weights changes the
  protocol identity; a changed tokenizer requires new context evidence.

IDs and records are attestations, not identity authentication or a machine proof
of semantic independence. The code cannot manufacture the review evidence that
is currently missing. An absence of structural matches never substitutes for it.

## Prespecified experiment fields

StudySpec makes all LoRA recipe fields explicit instead of silently inheriting
the disposable pilot's defaults. It records three distinct adapter seeds, matched
agent/defender context budgets, both relay modes, presentations, rollout/order/
state-selection/continuation seeds, logging mixture, branch states/repeats, episode
budgets and acquisition call/token caps. No production values are chosen by the
unit-test fixture.

The tuning comparator rule first minimizes observed violations, then maximizes
safe completion, then compares cost. The single update count is prespecified;
calibration does not select a new checkpoint or comparator. Keep the recovery
gain at five points, benign loss margin at two points and minimum inference
family requirement at least twenty. Report inconclusive evidence when needed.
Structured mode explicitly retains shared proposal substitution, with no
held-out-mechanism claim.

The manifest's protocol_id hashes its full content. Persisting checks both that
identity and the still-clean revision, and uses exclusive creation. Training,
adapter and outcome flags remain false. A subsequent runner still must enforce
the frozen inputs, acquisition/thermal accounting, exact stage records and
realized complete-menu target coverage before fitting. This tool does not claim
that runner is complete.

## Validation boundary

Unit tests use temporary Git repositories, visibly fake weight bytes and TEST
reviewer records; none are accepted research reviews, model inference or labels.
They exercise success, self-review, stale sources, missing checks and overlap
dispositions, dirty revisions, stale audit/tokenizer identities, relaxed criteria,
model-weight identity changes, tampered payloads and attempted output overwrites.
The real corpus remains unaccepted and fails the freeze preconditions.

Validation on 2026-10-23: the complete default suite passes **258 tests**, with
two existing optional Torch tests skipped in the default environment. All fourteen
freeze tests pass. Changed-file Ruff and strict mypy pass. These checks exercise
the tooling only; they supply no research review, training label or model outcome.
The source/context reports retained under ecpa-relay-preparation remain evidence
for clean source revision 826bb196794d42b8fad0a2664ff1624506d78667; adding this
gate does not retroactively change their recorded revision.
