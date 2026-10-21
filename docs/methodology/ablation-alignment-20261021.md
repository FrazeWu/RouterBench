# Existing ablation alignment audit

As of 2026-10-21. This analysis reads the historical 96-case, five-condition
diagnostic and its 2,400 saved attempts. It starts no model inference, changes no
formal scenario and never rewrites original labels. All seven saved outcome flags
were reproduced without mismatch using trusted in-memory execution.

## Findings from actual materials

| Intervention | Graphs changed | Public exact answer set changed | Interpretation |
|---|---:|---:|---|
| Dangerous decoys removed | 1/96 | 0/96 | Near-null; insufficient to estimate a general distractor effect. |
| Functional alternatives pruned | 15/96 | 1/96 | One original tie is removed; 14 changed cases retain the answer set. |
| Dependencies stripped | 78/96 | 0/96 | Every terminal-path outcome is unchanged; requirements are redundant for these enumerated routes. |
| Authority contrast flattened | 93/96 | 52/96 | Answer sets expand, mixing information removal with easier correctness labels. |

The complete condition has one public-exact tie, not 96 unique solutions. After
authority flattening, 53 cases have public-exact ties. The total number of accepted
paths rises from 97 to 149. Of the saved flattened selections, **64/480** were
accepted under flattened labels but not under the base labels. This is a same-route
label exposure check, not a counterfactual model run; do not subtract these labels
to manufacture a corrected treatment effect. No selection was newly rejected.

All 96 reference certificates remain accepted in every condition. Certificate
acceptance alone therefore cannot establish an unchanged answer set. The evaluator
actually awards primary credit using eligible public-exact optima, including ties,
not only identity with the hidden reference. This audit does not change that rule.

The flattening script intends to drop private costs. Actual private-cost maps change
in 58/96 cases, not every case. Under the public contract those costs are not the
primary label rule. The dangerous and functional projections preserve the shared
path semantics; functional pruning changes private maps in 8 cases by filtering
removed edges. Script intent must not replace checking materialized artifacts.

## Existing outcomes remain descriptive

Effective-subset membership is defined from material differences, never model score.
All five presentation seeds stay within each case during paired bootstrap. The
analysis uses 10,000 draws, PCG64, seed 20261021 XOR comparison-label CRC32. Intervals
are exploratory and not multiplicity adjusted.

- Functional-alternative pruning: 14 changed, strictly answer-preserving cases;
  optimal difference +5.71 pp, 95% interval [0.00, 12.86]. Small, selected subset.
- Authority flattening: 41 changed, strictly answer-preserving cases; optimal
  difference -3.90 pp [-9.76, 1.46]; unsafe-branch difference +2.44 pp [-0.98, 6.35].
  This subset does not support a clear unsafe-branch effect. The whole-subset
  +5.83 pp is a mixed-intervention diagnostic, not a clean fixed-objective estimate.
- Dependency stripping preserves outcomes on all enumerated paths. It can test
  sensitivity to redundant dependency annotations, not a causal execution-dependency
  hardness effect. This replaces the earlier untested possibility of feasibility
  changes for this particular 96-case materialization.

The strict fixed-objective screen requires identical tasks, policies, verifiers,
fixtures, certificates, retained bindings, common-path outcomes, eligible sets and
public-exact sets. Passing it does not establish full causal isolation. A new
candidate-count experiment may intentionally change nonoptimal eligible alternatives;
its gate should preserve the optimum and common-path semantics, not require identical
candidate sets. Length interventions need an explicitly checked path mapping.

## Reproduction

From a committed clean revision with analysis dependencies installed:

```bash
PYTHONPATH=src python scripts/report_ablation_alignment.py \
  --artifacts-root /absolute/path/to/existing/artifacts/private \
  --output-root artifacts/private/ablation-alignment-UNIQUE-ID
```

The output root must not exist. Reports contain only aggregate statistics and
private material flags/digests, not model responses or reference routes. Provenance
records the analysis revision, dirty flag, source hashes and input record digests.

## Next diagnostic gate

Author new development-only matched tasks, separately from the held-out 776 cases.
Manually bind registered adapters/providers/resources, planning skills and workflow.
Before inference, require a measurable intended factor change, unchanged legitimate
goal and forbidden effects, executable reference and attack witnesses, a unique
public optimum and invariant mapped optimal answer set. Freeze this as a new
diagnostic identity; do not relabel the old runs.
