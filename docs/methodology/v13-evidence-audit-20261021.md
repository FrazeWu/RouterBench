# v13 evidence closure and remaining experiments

As of 2026-10-21 (Asia/Shanghai). This is an analysis checkpoint, not a new
benchmark protocol or new model-inference run. The held-out 776 cases are unchanged.

## Corrections to previous reporting

- The current Qwen3-8B recovery and Qwen3-14B runs each retain 3,880 private
  per-attempt manifests. The earlier claim that they retained only aggregates was
  incorrect. No model rerun or outcome reconstruction is needed for paired statistics.
- The 8B optimal-attempt rate differs from its older result by about 0.13 pp, but
  its capable-case rate differs by about 0.64 pp. Do not apply the former statement
  to every metric.
- Historical intervals cannot be attached to current recovery scores. Compute the
  intervals from the exact selected run directories.
- Runtime failures are not capability failures. Preserve the initial 8B run with
  904 backend failures and report it separately; do not merge it into recovery.

## Implemented analysis

`scripts/report_v13_evidence.py` has an explicit 15-checkpoint canonical inventory,
selected by source directory rather than score. It does not collapse model families,
instruct derivatives, quantized checkpoints, pilots or repeat runs into new models.

For each canonical run it checks the full case/seed matrix, per-case digests, clean
source provenance, Boolean outcomes, aggregate totals and effect-family/length
subtotals. Fourteen selected checkpoints share the 32K planner contract. OpenChat-3.6
used an 8K context limit and is listed only in a separate diagnostic table, not in
the main model comparison. Its 3,880 records remain audited and preserved.
Invalid model outputs remain failed outcomes, whereas runs containing
backend failures cannot enter the canonical table. The script validates shared
decoding, presentation and evaluation contracts before comparison.

Eight declared model comparisons use paired case-cluster bootstrap intervals:
10,000 resamples, PCG64, base seed 20261021 combined with the comparison label.
All five seeds remain in the same sampled case. Effect-family and declared-length
tables are descriptive, exploratory and not multiplicity-adjusted. Serving and
quantization confounds remain even when an interval excludes zero.

The analysis also compares relevant planner, executor, schema, verifier and graph
evaluation sources across recorded commits. This is narrower than proof of full
environment equivalence; Python, dependency and vLLM versions still require reporting.
In particular, 8B recovery used eager execution and additional memory headroom;
14B and historical 32B-AWQ did not share every serving setting.

Failure reporting separates observed outcome categories from hypothesized causes.
Representative f3/f4/f6 or l2/l3 failures are deterministically selected and replayed
only through trusted in-memory adapters with matching fixture digests. No raw
prompts, responses, action arguments or reference routes are exported in reports.
The case-ID review queue is private and not a prevalence sample.

## Reproduction

Install the project with its `analysis` dependencies. From a clean committed checkout:

```bash
PYTHONPATH=src python scripts/report_v13_evidence.py \
  --artifacts-root /absolute/path/to/existing/artifacts/private \
  --output-root artifacts/private/v13-evidence-UNIQUE-RUN-ID
```

The output directory must not exist. Original run artifacts are read-only inputs.
Outputs include the model table, exact-run paired statistics, inventory/exclusions,
failure diagnostics, ablation audit, private review queue and analysis provenance.
The latter records analysis Git revision/dirty flag, script hash, attempt-record
hashes and source roots. Generated outputs remain ignored by Git.

## Ablation audit findings

The existing 96-case component diagnostic has five conditions with 480 attempts
each and a paired bootstrap report. However, successful execution alone does not
make a manipulation informative:

| Condition | Graphs actually changed | Interpretation |
|---|---:|---|
| Dangerous decoys removed | 1/96 | Near-null manipulation; identical scores are not evidence of robustness. |
| Functional alternatives pruned | 15/96 | Whole-subset effects are diluted; effective-subset results are needed. |
| Explicit dependencies stripped | 78/96 | Feasibility may change; not a pure dependency-complexity comparison. |
| Authority contrast flattened | 93/96 | Public attributes and costs change; not removal of the least-permission objective. |

The existing v12-order versus v13-permutation comparison has 100 paired cases,
covering f1/f2/f3 only. Keep it as a prefix diagnostic, not an eight-family result.
Declared route-length strata are not the actual safe-certificate length. Their
association with score does not establish a causal complexity effect.

## Remaining work, in order

1. Use the validated canonical model table and current recovery intervals in paper
   drafts; keep pilot, repeated-run and infrastructure tables separate. Do not
   replace or rewrite original result directories.
2. Reaudit the authority-flattening intervention for public/hidden optimum alignment
   before using it for causal claims. Report any changed labels or ties explicitly.
3. Design a new **development-only** matched diagnostic for candidate alternatives
   and dependency/length complexity. Specify catalog bindings, invariant legitimate
   goal, visible information, forbidden effects and objective before inference.
   Validate that every intervention actually changes its intended factor and does
   not silently change the optimum or task feasibility.
4. Keep the least-permission evaluator fixed. A permission-awareness prompt baseline
   can change planner instructions, but it must not redefine task success. Removing
   an evaluator objective answers a different research question.
5. Commit and freeze the new diagnostic separately, run a small paired pilot on the
   already covered 8B/14B models, and only then expand. A null effect is reportable;
   do not tune against held-out performance until a desired gap appears.

No new model server or GPU evaluation is required for this evidence-closure step.
It is complete only when actual-run statistics, integrity checks, effective
manipulation checks and the remaining-experiment boundary are all recorded.

## Verified aggregate conclusions

- Current Qwen3-14B minus recovery 8B optimal-attempt success: +20.36 pp,
  paired case-bootstrap 95% interval [+18.40, +22.37]. Capable-case difference:
  +22.55 pp [+19.20, +26.03]. Unsafe-branch selection difference:
  -6.21 pp [-7.58, -4.87]. These intervals use the current saved attempts.
- Current 14B minus historical 32B-AWQ optimal-attempt success: +2.65 pp
  [+1.42, +3.92], but capable-case difference is -0.13 pp [-2.19, +2.06].
  Do not describe this as 14B winning every metric or proof that size hurts.
- The 96-case authority-flattening diagnostic changes unsafe-branch selection by
  +5.83 pp [+3.12, +8.96]; its optimal-attempt difference is -2.08 pp
  [-6.67, +2.50]. This is diagnostic evidence with the intervention caveats above.
- Ordered-to-permuted presentation changes optimal-attempt success by -12.00 pp
  [-16.00, -8.20] on the existing 100-case prefix. Coverage is limited to f1/f2/f3.

These are observed checkpoint comparisons. No causal size, family, attack-adaptation
or real-world exploitation claim is supported by these statistics alone.
