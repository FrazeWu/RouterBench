# Source-bound independent defense study freeze

Status: tooling implemented, 2026-10-23. **No formal protocol is frozen.**
The current corpus has eight of twelve planned training candidate families
(twelve tasks), seven of forty planned test candidate families (eight tasks),
and no accepted independent reviews. Formal collection, fitting and efficacy comparison remain
pending. This gate supplies provenance checks, not reviewer attestations.

## Corpus status update, 2026-11-02

The current 29-task inventory now has source-digest-bound AI review attestations
by `Codex-AI-Reviewer`, with `法宗` recorded as the author. The reviewed family
counts are 8/4/4/7, against planned counts of 12/4/4/40. Review is limited to
the fixed simulator sources and selected legacy comparisons; it does not
authenticate a human identity or establish arbitrary production behavior.
Four train families and thirty-three test families remain missing, so the
allocation precondition still blocks freezing. Model/tokenizer audits and
realized training-target coverage are also outstanding.

## Completed corpus update, 2026-11-02

The reviewed inventory now has 66 tasks and exactly 12/4/4/40 accepted families
across train/tune/calibration/test. The 37 new task sources use
`Codex-Scenario-Author` as their declared author and `Codex-AI-Reviewer` as the
designated non-author reviewer; the original 29 records continue to identify
`法宗`. Per the user's instruction, AI review is valid for this preparation
gate, but the identifier does not authenticate a human reviewer.

All 66 tasks pass the local source simulator and binding selection checks, and
the freeze source validator accepts the manifest plus source-bound reviews.
There are four public-structure match groups. The 37-member dependency-only
group has 1,332 reciprocal current-digest references across different families;
the other groups are the conserved-transfer/journal pair, the two same-family
tuning variants, and the five same-family training variants. The test retry
candidate and historical-overlapping archive-count candidate are excluded;
restore source identity and resource-capacity variants are conservatively
consolidated as recorded in the source-review report.

`configs/defense/study.yaml` is now the explicit pre-freeze recipe, carrying
forward the prior seed, update count, budgets and success thresholds. The
resource assignment reserves both GPUs, runs Qwen3-14B on GPU 0, and places the
Qwen3-1.7B selector on GPU 1, which had 14 GiB resident at preparation time.
No frozen manifest or formal model run exists yet. After the coherent commit,
rerun source/context audits, freeze this StudySpec, collect training episodes,
verify all four realized target kinds, then fit the adapter.

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
of semantic independence. The code cannot manufacture or authenticate review
evidence; a reviewer ID is a declared identity, not proof that the reviewer is
human. An absence of structural matches never substitutes for review.

## Prespecified experiment fields

StudySpec makes all LoRA recipe fields explicit instead of silently inheriting
the disposable pilot's defaults. It requires exactly one adapter seed matching
the recipe seed (planned: 29), matched
agent/defender context budgets, both relay modes, presentations, rollout/order/
state-selection/continuation seeds, logging mixture, branch states/repeats, episode
budgets and acquisition call/token caps. It now also requires explicit reserved
GPU IDs, thermal stop/cooling settings, the one-presentation enumerated training
schedule and all four required realized target kinds. No production values are
chosen by the unit-test fixture. Fit one Qwen3-1.7B LoRA adapter; retain the same
unfitted base as a control and the frozen Qwen3-14B task agent. Do not perform
training-seed or checkpoint sweeps. Family-level inference is conditional on
this single fit and cannot establish robustness to training randomness.

The tuning comparator rule first minimizes observed violations, then maximizes
safe completion, then compares cost. The single update count is prespecified;
calibration does not select a new checkpoint or comparator. The spec additionally
requires seeded arm-block scheduling, all three guarded comparator arms with an
explicit tie order, family-mean online-budget cost and fixed-policy calibration
without selection or an outcome-dependent test gate. Keep the recovery
gain at five points, benign loss margin at two points and minimum inference
family requirement at least twenty. Report inconclusive evidence when needed.
Structured mode explicitly retains shared proposal substitution, with no
held-out-mechanism claim.

The manifest's protocol_id hashes its full content. Persisting checks both that
identity and the still-clean revision, and uses exclusive creation. Training,
adapter and outcome flags remain false. The collection/fitting entry point is now
implemented in scripts.run_defense_study; see defense-study-runbook.md. It checks
the frozen sources/models, acquisition/thermal accounting and complete-menu
target coverage. The same runner now implements tuning, fixed-policy calibration
and fresh tests, retaining the sole adapter and exact prerequisite/file identities.
The actual tuning/calibration records and fresh efficacy study remain pending.
Neither entry point has run on formal model data.

## Validation boundary

Unit tests use temporary Git repositories, visibly fake weight bytes and TEST
reviewer records; none are accepted research reviews, model inference or labels.
They exercise success, self-review, stale sources, missing checks and overlap
dispositions, dirty revisions, stale audit/tokenizer identities, relaxed criteria,
model-weight identity changes, tampered payloads and attempted output overwrites.
At the 2026-10-23 status checkpoint, the real corpus had no accepted reviews and
failed the freeze preconditions.

Freeze checkpoint d2294089bc5d47bf1ec3dfc6d8b338c6a5f6d9a4 validation on
2026-10-23: the complete default suite passes **258 tests**, with
two existing optional Torch tests skipped in the default environment. All fourteen
freeze tests pass. Changed-file Ruff and strict mypy pass. These checks exercise
the tooling only; they supply no research review, training label or model outcome.
The source/context reports retained under ecpa-relay-preparation remain evidence
for clean source revision 826bb196794d42b8fad0a2664ff1624506d78667; adding this
gate does not retroactively change their recorded revision.
