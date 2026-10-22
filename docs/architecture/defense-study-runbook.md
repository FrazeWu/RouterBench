# Frozen compact-defense study execution

Status, 2026-10-23: collection, fitting and matched-comparison tooling implemented
and tested with clearly identified transport/simulator fixtures. **No formal protocol or production
StudySpec exists; no formal model collection or training has started.** The real
corpus still has 6/40 candidate test family labels and zero independent acceptances.
Completing code does not supply those missing sources or reviews.

## Boundaries and order

1. Complete the task sources and genuine independent semantic/contract review.
   Commit the exact family allocation, one-presentation schedule, recipe, three
   adapter seeds, resource reservations, thermal limits, budgets and original
   success criteria. Do not copy TEST fixtures into the research configuration.
2. From that clean checkpoint, rerun the authoring/tokenizer audits and use
   scripts.freeze_defense_study to write the source/model-bound manifest. This
   identity must include the implementation used for collection and fitting.
3. Run scripts.run_defense_study --phase collect with that manifest and a new
   ignored private directory. Its own local vLLM subprocess serves the frozen
   task-model path; an existing endpoint cannot silently substitute a model.
4. Inspect the completed phase, actual target-kind counts and retained failures.
   Fitting refuses aborted phases, changed artifacts, a missing candidate/repeat
   or absent realized allow/constrain/escalate/deny targets. Menu availability
   alone does not pass. Do not fabricate labels or add post-outcome task cases.
5. Use --phase fit with the verified collection and another new output directory.
   The runner fits all three prespecified LoRA seeds, with one fixed recipe and
   update count. Fitting alone cannot establish defense effectiveness.
6. Use --phase tune with --fit pointing to that completed phase. All seven arms
   run: four shared controls and all three trained seeds. Choose the comparator
   only from the three guarded controls using the declared lexicographic rule.
7. Use --phase calibration with the same --fit and completed --tune directories.
   Audit the fixed selection, retaining failures and uncertainty. Do not retune,
   choose a seed, or condition whether tests run on the calibration outcome.
8. Use --phase test with the same --fit, --tune and completed --calibration.
   Persist all fresh cases, then report pooled, mode-stratified and per-seed
   family-clustered comparisons. Completion does not imply statistical success.

If collection lacks a required target, preserve the result and report the failed
coverage gate. A justified source/protocol change requires a new committed
checkpoint and protocol identity; it cannot repair an old result in place.

## Collection schedule and outcomes

Enumerate every frozen train task once in each relay mode and benign/attacked
condition, in manifest/mode order. No tune/calibration/test task is collected for
training. Task acquisition is an enumerated inclusion probability of one, not an
inferred sampling propensity. Uniform/diagnostic acquisition is a separate study.

After completing a logging parent, uniformly select up to the prespecified number
of its encountered multi-choice states. Clone simulator and consumed relay state
independently for every menu candidate/repeat. Candidates share a continuation
seed within a repeat. Retain the logging action probabilities, state-inclusion
probabilities, common continuation seeds, exact acceptance/approval outcomes,
sticky episode violations and actual evaluator outcomes.

Persist each finished parent/branch immediately, so an interruption cannot erase
already completed continuations. Every group includes the complete candidate
menu; failures remain outcomes and censoring excludes the entire comparison.
Stage telemetry separates inherited relay events from newly reached stages.
Current-continuation dispatch is not historical prefix dispatch or proof of
eventual harm; report the separate outcome flags.

Identical public selector inputs within the same effective attack condition are
deduplicated by the first scheduled occurrence, before consulting branch labels.
Retain all raw copies and report the duplicate IDs. Exact ties use the established
rule-preference/lexical tie break; no evaluator route is an input to the model.
Structural matching does not make different task families independent.

## Matched comparison and fixed selection

The schedule uses seeded arm blocks so each compact model is loaded once per
split. Within each arm, enumerate every task, mode and benign/attacked condition
once. The four shared controls are not rerun for each adapter seed. The same
episode seed is used for every arm and condition at a given task/mode; response
histories may diverge after interventions. Arm order is frozen before outcomes.
Blocking saves load cost, but it does not randomize away all temporal effects;
report reservation time and thermal telemetry for each complete phase.

Tuning ranks per-action authorization, the path rule and the prompted compact
base by violation rate, safe completion and online budget units, in that order.
Each semantic family contributes an equally weighted within-family mean across
all modes, conditions and task variants. Exact ties use the explicit comparator
order in StudySpec. The unguarded simulator is descriptive, never a candidate
for the primary guarded comparator. Adapter seeds and update count are not
selected. Online budget units are a prespecified tie breaker, not a GPU-time or
latency claim; actual model calls, tokens, selector fallbacks and time remain
separate measurements.

Calibration and test reload the completed fitted adapters and recompute the
tuning decision from the complete recorded tuning schedule. Prerequisite hashes
bind the same fit, collection and source identity through all stages. Calibration
records do not alter that decision or provide a pass/fail gate for running the
test. Every learned seed is paired with its already collected shared comparator;
family resampling retains those repetitions rather than treating them as new
families. Zero-width intervals and fewer than twenty independent families cannot
pass the prespecified joint rule. The source-review gate remains mandatory.

## Cost, context and thermal accounting

Count each actual HTTP request, including draft, receiving and offer acceptance,
against a shared acquisition ledger. Tokenize the exact messages locally; refuse
over-context calls without truncating. Before sending, reserve one full frozen
context as a conservative cap, then reconcile valid reported prompt/completion
usage. Missing usage or transport failure consumes the full reservation; excessive
reported usage aborts. Calls are neither retried nor dropped to meet the budget.

GPU IDs are physical indices with PCI_BUS_ID ordering. The runner requires no
CUDA_VISIBLE_DEVICES override, and the owned server receives its assigned GPU
explicitly. Monitor all declared reserved devices, apply the prespecified call/
update gap and cooling thresholds, and abort on thermal throttling or telemetry
failure. Started server processes are cleaned up with their own process group.
Do not terminate other jobs. Reservation time includes server startup, cooling,
idle and shutdown within the phase; external environment setup and model hashing
are excluded and must be reported separately in total study cost.

The per-phase acquisition ledger charges collection and comparison calls. Local
selector invocations share the phase's hard call/token cap with HTTP task-agent
requests. Measured selector tokens are reconciled; errors and overflow fallbacks
retain the full context reservation and their outcomes. Training reports its
own actual processed tokens, update time and memory through train_lora; a zero
HTTP count during fitting is not a zero-cost training claim. No global GPU-hour
ceiling is introduced by these tools.

## Interface and private outputs

The implementation requires the RouteBench learning dependencies and vLLM in the
same Python environment for collection. Run from the project root with a clean
tree. --help is available without loading weights. After a real freeze, provide
its path as --manifest, choose collect, fit, tune, calibration or test with --phase,
and select a new
artifacts/private path with --output. Fitting additionally takes --collection
pointing to the previous phase's collection subdirectory.

No usable production manifest is supplied in this document. The CLI cannot
bypass the incomplete corpus/review gate by accepting only a protocol-ID string.

Outputs include phase-manifest.json, phase-result.json, telemetry.json, private
per-call accounting, the owned task-server command/PID/log, individual private
rollouts, all group files and collection.json. Completed phase results bind
collection-file hashes. Fitting verifies those identities and actual target
coverage again before allocating the compact model. Three adapter directories
retain base/adapter hashes and their source-group provenance.
Comparison phases additionally persist the exact schedule, each row and raw
rollout, mode-specific descriptive totals, immutable tuning decision and the
fixed-policy analysis. Their successful measured phase binds every output file;
an aborted or changed phase cannot supply later-stage evidence.

These are ignored runtime artifacts. Never commit raw model data, server logs,
generated records, adapters or the TEST-only review attestations used by unit
tests. The previously completed pilot and its disposable adapter remain separate.

## Engineering validation

At collection/fitting checkpoint 9ac3c68e721b4deaf7c61d7cf036733b83e6f64b,
on 2026-10-23 the full default suite passes **272 tests**, with two existing
optional Torch cases skipped because this environment lacks Torch. Changed-file
Ruff and strict mypy pass. Eleven new study tests exercise real simulator menus
with MockTransport/fake tokenizer fixtures: per-call charging, missing/excess
usage, pre-request context/thermal stops, train-only collection, incomplete target
coverage, source/artifact integrity, exact menu/repeat schedules and a successful
TEST-only provenance load. Freeze tests additionally reload the saved manifest
and reject changed local model bytes. No GPU model inference is performed here.

The paper compiles to fourteen pages; changed pages 5 and 13 are rendered and
visually checked, with no clipping/overlap, overfull boxes or unresolved references.
Validation details and hashes of the tested sources are retained under ignored
artifacts/private/ecpa-study-tooling-preview/validation.json. The freeze-only
checkpoint is d2294089bc5d47bf1ec3dfc6d8b338c6a5f6d9a4. Older source/context audits
remain evidence for their originally recorded revisions; none is relabeled to
the new implementation checkpoint. Formal evidence is still pending.

The subsequent conserved-transfer/append-only candidate batch passes **283
tests**, with the same two optional Torch skips. Changed-file Ruff and strict
mypy pass. Its source engineering check exercises 25 tasks, 50 safe witnesses,
25 harmful references, 76 relay stages per transport and 69 menu probes. These
counts describe authored reachability, not model outcomes or accepted independent
families. The updated fourteen-page paper compiles; page 13 is rendered and
visually checked without clipping or overlap. Fresh clean-revision source and
tokenizer audits are recorded separately after committing this batch.

Those audits now bind clean candidate checkpoint
2ae819579841c9574e94318f73348f0109aa315e under ignored
artifacts/private/ecpa-relational-checkpoint. They confirm 25 source tasks and
1,060 actual tokenizer measurements plus 250 separate planning estimates, with
no sampled overflow at 8,192 tokens. No model weights were loaded and no model
rollouts were performed. They do not bind later comparison-tooling changes.

The matched-comparison implementation passes the complete default suite on
2026-10-23: **293 tests passed, two optional Torch tests skipped**. Changed-file
Ruff and strict mypy pass. Ten comparison tests exercise exact arm/seed schedules,
common episode seeds, safety-first equal-family comparator selection, retained
HTTP failures, fixed-policy precision limits, raw/row/phase integrity, collection
and adapter recipe bindings, unchanged tuning/calibration decisions and selector
cost/fallback accounting. Mock HTTP, fake adapter records and invented labels are
explicit TEST fixtures only. No model weights or formal inference are used.
The fourteen-page paper compiles; pages 13 and 14 are rendered and visually
checked, with no clipping, overlap, overfull boxes or unresolved references.

The monotone-epoch/cumulative-disclosure candidate batch passes **308 tests,
two optional Torch tests skipped** on 2026-10-23. Changed-file Ruff and strict
mypy pass. The source engineering check exercises 27 tasks, 54 safe witnesses,
27 harmful references, 83 relay stages per transport and 73 menu probes. New
checks replay transient epoch decreases and aggregate distinct disclosed keys;
the same two-field payload is compliant before prior disclosure and violates
the cumulative budget afterward. These are simulator checks, not model outcomes.
The fourteen-page paper compiles; the changed page 13 is rendered and visually
checked without clipping or overlap. A fresh clean-revision source/tokenizer
audit is required after committing this batch; earlier reports do not bind it.
