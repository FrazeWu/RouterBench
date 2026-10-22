# Independent compact-defense study preparation

Status: authoring, 2026-10-22. The author chose a moderate study, retaining the
original success criteria and reporting inconclusive evidence when necessary.
This is a prospective plan, not a frozen protocol or completed experiment.

## Execution plan

1. **Completed:** structural replanning fix, shared by every arm. Enumerate all
   current-node edges, including unsafe/unproductive choices. Preserve pilot results.
2. **In progress:** independent family authoring. Four initial training workflows
   now cover settlement reconciliation, health-gated retry repair, immutable
   incident-copy review and pause-before-enable scheduler handover. Each has two
   executable safe paths and two legitimate prefix actions before the harmful step.
3. **Tooling complete, evidence pending:** source isolation and simulator audits.
   Validate bindings, actual safe-path dispatch, rejected approvals, harmful
   reference execution and four intervention-menu kinds. These use a scripted
   exact-offer acceptor, not the frozen task model. They are not training labels.
4. **Pending:** remaining families, independent semantic/contract review, context
   checks, real branch outcomes covering all target kinds and snapshot/protocol freeze.
5. **Pending:** one LoRA recipe, matched development comparison, calibration audit
   and fresh paired test. Preserve strong per-action and path-rule baselines.
6. **Pending:** family-clustered analysis, cost/negative-result report and paper results.

## Corpus boundaries

Inventory: `configs/defense/independent-corpus.yaml`. Each task has `public.yaml`,
`state.fixture.json`, `evaluator.yaml` and `authoring.yaml`. Only
`PublicRecoveryTask` reaches models. Fixtures, verifier assertions, authoring
routes/probes and review notes are evaluator-owned. Digests bind all sources and
split entries. No evaluator optimum or private cost certificate is defined here.

Every edge has explicitly selected universe adapters, concrete provider/resource/
mode bindings, planning skills and workflow. Provider choices use simulator
primitives, not live providers. These compact tasks do not claim the universe's
large hard-graph targets. Safe-path witnesses are separate from evaluator checks.
Alternative providers/rereads create paths, not additional independent families.

All four families remain **authored, not independently reviewed**. Review must
check overlap with prior corpora, contract soundness, leakage, reachable attacks,
neutral menus and simulator/evaluator agreement. Names/hashes do not prove
independence. Menu coverage does not prove real training-target coverage.

Train/tune/calibration/test families must be disjoint. Fresh primary tests also
need genuinely held-out mechanisms: renamed payloads/entities/providers/modes
do not qualify. Initial tasks use the existing authorization-pretext campaign;
held-out mechanisms and test tasks remain pending. Exclude pilot data/adapters
and historical formal-test traces from training.

## Moderate prospective allocation and cost

Working target: **12 train / 4 tune / 4 calibration / 40 test families**. Actual
materialization: **4/0/0/0**. Counts are not frozen. Initially use one task and one
presentation per family, two relay modes and benign/attacked pairs. Do not meet
the count by renaming tasks. Revise after source/context/cost audits before any
fitting/test outcomes, then commit and freeze the exact protocol.

One Qwen3-1.7B architecture and LoRA recipe, three prespecified adapter seeds.
Run the learned arm per seed and four shared control/reference arms once per
setting. Seeds/modes are repeats within families; do not select the best seed.
Tune comparator/checkpoint rules before calibration; calibration cannot select.

Using 78.42 paced seconds/episode from the pilot, two reserved GPUs, two branch
states/parent and at most four candidates gives 48 parents, up to 384 branches
and 1,344 comparison episodes: **77.37 GPU-device-hours**. Half-to-double duration
gives 38.69--154.75 hours, excluding fits, context audits, review and server
startup/idle. This is sensitivity, not measured total or a cap. Count actual
menus before freezing; never truncate menus to meet the planning assumption.

## Precision and interpretation

Retain >=5-point recovery gain with paired 95% lower bound >0, benign one-sided
95% lower bound >=-2 points, and no utility tradeoff for added violations.
Moderate family counts may leave the joint rule unproven.

Conservative planning scenario: iid sampled families, adverse if any paired case
has a learned-only benign failure. Zero observed adverse families gives a
one-sided exact 95% upper adverse-family probability `1 - 0.05 ** (1/n)`: 7.22%
at 40, 4.57% at 64, first <=2% at 149. This is not a necessary sample-size theorem,
does not establish iid sampling of authored tasks, and is not replacement
inference or guaranteed power. It illustrates the limits of few all-tie cases.

Future percentile-bootstrap reports keep descriptive estimates but cannot certify
the joint claim with <20 families or a zero-width empirical interval. Benign
`[0, 0]` after all observed ties is not proof of 2% noninferiority. Historical
pilot results and success thresholds remain unchanged.

## Reproduce source audits

From a committed clean revision:

```bash
python -m scripts.audit_defense_corpus \
  --manifest configs/defense/independent-corpus.yaml \
  --output artifacts/private/ecpa-independent-preparation/authoring-audit.json
```

The command refuses existing output and records the source revision. Its
`formal_run_ready: false` is intentional. This preparation tool cannot run
formal collection, fit models or certify pending reviews. Source audits use no GPU.

Current validation: 214 default tests passed, two optional learning tests skipped
because that environment has no Torch. Changed-file Ruff and strict type checks
passed. The source checks exercise eight safe paths, four harmful reference
paths and 15 menu probes, including actual approval rejection. No additional
adapter fitting, GPU inference or formal outcome collection has occurred.
