# ECPA development implementation and pilot

The completed engineering stage below is followed by the active prospective
preparation in `independent-defense-study-plan.md`. New task authoring/audits are
separate from this pilot; its original measurements and adapter remain unchanged.

This is the implementation plan for the approved compact-defender experiment.
It is development work, not a formal defense-effectiveness study. Historical v13
results and tests are not training data. No new capability-routing tasks are
authored in this implementation: the two existing development overlays exercise
interfaces only and do not constitute an independent corpus.

Status, 2026-10-22: all six implementation deliverables below are complete. The
real-model pilot finished eight parent episodes, 18 branch continuations, one
disposable LoRA fit/reload and the full 40-episode comparison. See
`compact-defense-pilot-results.md` for provenance, measured costs, negative
results, tests and the boundary to the still-pending independent formal study.

## Deliverables and order

1. A shared, explicitly filtered public observation serializer and trusted local
   candidate-ID selector for frozen Qwen3-1.7B and its LoRA adapter. Reject excess
   context rather than truncate; invalid model outputs use the deterministic rule.
2. An external response-relay harness with staged text replacement and structured
   call forgery. The defender channel is separate. Pair each attack mode with its
   own benign transport path, count every receiving-agent inference, and record
   stages actually reached rather than assume a multi-step attack succeeded.
3. Actual menu-branch collection at encountered development states. Enumerate
   candidates from independent simulator copies with common continuation seeds,
   retain failure/censoring and exact assignment probabilities, and produce
   outcome-derived choice labels without exposing evaluator internals to models.
4. Single-recipe LoRA supervised choice training, answer-only loss, no silent
   truncation, adapter reload, artifact hashes and development/formal identity
   checks. Development timing adapters cannot enter formal evaluation.
5. A bounded development runner covering all five arms and paired benign/attacked
   episodes, plus GPU telemetry, thermal stop, per-phase costs and a reproducible
   aggregate report. An explicitly isolated simulator-only unguarded reference
   does not relax production runtime checks.
6. Meaningful tests of information boundaries, relay behavior, branch targets,
   censoring, identity checks and actual adapter updates/reload; lint and checkpoint
   the complete chain before measured runs. Record measured-run source revision.

## Pilot boundary

The operational pilot includes a disposable short adapter fit solely to measure
memory/time and verify update/reload. Neither its records nor adapter enter formal
training, tuning, calibration, testing, or efficacy estimates. Reusing the two
development families in this engineering smoke does not establish generalization.
Five-arm completion figures are descriptive integration checks only.

After actual measurements, a formal study still needs independently authored and
audited task families, held-out attack mechanisms, frozen model/adapter snapshots,
family counts, repetitions, seeds, precision/cost justification and a fresh clean
checkpoint. A timing pilot cannot by itself determine statistically adequate
sample size. No automatic formal run or efficacy claim is authorized by this plan.
