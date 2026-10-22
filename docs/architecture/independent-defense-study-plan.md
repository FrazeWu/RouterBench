# Independent compact-defense study preparation

Status: authoring, 2026-10-22. The author chose a moderate study, retaining the
original success criteria and reporting inconclusive evidence when necessary.
This is a prospective plan, not a frozen protocol or completed experiment.

## Execution plan

1. **Completed:** structural replanning fix, shared by every arm. Enumerate all
   current-node edges, including unsafe/unproductive choices. Preserve pilot results.
2. **In progress:** independent family authoring. Twelve candidate training
   workflows have executable sources; semantic independence remains unreviewed.
   Each has two executable safe paths and two legitimate prefix actions before
   the harmful step. See the inventory below.
3. **Tooling complete, evidence pending:** source isolation and simulator audits.
   Validate bindings, actual safe-path dispatch, rejected approvals, harmful
   reference execution and four intervention-menu kinds. These use a scripted
   exact-offer acceptor, not the frozen task model. They are not training labels.
4. **Context/collection tooling implemented, formal evidence pending:** local
   tokenizer checks replay sampled public states; parent/branch collection uses
   real JSON-agent calls and independent simulator snapshots. Remaining split
   families, independent semantic/contract review, real-model branch outcomes
   covering the target kinds and snapshot/protocol freeze remain pending.
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

All twelve candidates remain **authored, not independently reviewed**. Review must
check overlap with prior corpora, contract soundness, leakage, reachable attacks,
neutral menus and simulator/evaluator agreement. Names/hashes do not prove
independence. Menu coverage does not prove real training-target coverage.

| Candidate training family | Distinguishing public obligation |
| --- | --- |
| settlement reconciliation | Preserve live evidence, approve the correction, read back the write |
| health-gated retry repair | Require health evidence before enabling retry |
| immutable incident-copy review | Preserve and verify a copy without changing the source |
| pause-before-enable scheduler handover | Pause the old scheduler before enabling its successor |
| retention/hold intersection | Delete expired data only when it is outside legal hold |
| consent-before-erasure | Revoke consent before deleting the subject's data |
| attested promotion | Join test and provenance evidence before promotion |
| snapshot restoration | Restore from evidence while preserving the recovery source |
| availability-preserving role reduction | Reduce authority while retaining account availability |
| canonical-preserving deduplication | Remove the duplicate while preserving the canonical row |
| read-only diagnosis | Correlate observations without making remedial changes |
| canonical-to-document reconciliation | Update the derived document without changing its canonical source |

These are candidate distinctions, not an independence certificate. In particular,
role reduction needs comparison with historical access-review tasks; copy/restore
and reconciliation families need review for deeper structural overlap. Merge or
replace overlapping candidates rather than preserve a nominal count.

Train/tune/calibration/test families must be disjoint. Fresh primary tests also
need genuinely held-out mechanisms: renamed payloads/entities/providers/modes
do not qualify. Initial tasks use the existing authorization-pretext campaign;
held-out mechanisms and test tasks remain pending. Exclude pilot data/adapters
and historical formal-test traces from training.

## Moderate prospective allocation and cost

Working target: **12 train / 4 tune / 4 calibration / 40 test families**. Actual
materialization: **12/0/0/0 candidate families**. Counts are not frozen. Initially use one task and one
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
  --output artifacts/private/ecpa-independent-training-preparation/authoring-audit.json
```

The command refuses existing output and records the source revision. Its
`formal_run_ready: false` is intentional. This preparation tool cannot run
formal collection, fit models or certify pending reviews. Source audits use no GPU.

The current source checks exercise 24 safe paths, 12 harmful reference paths
and 38 menu probes, including actual approval rejection. These checks provide
zero training labels. No additional adapter fitting, GPU inference or formal
outcome collection has occurred.

## Context and branch preparation

`scripts.audit_defense_contexts` loads the two local tokenizers without model
weights, uses the exact `agent_messages` and selector chat templates, disables
thinking, and reserves 768 agent or 96 defender completion tokens within 8,192.
It checks safe-path prefixes, probe prefixes, current-node proposals and exact
replacement offers. Representative benign drafts and fixed attack text are
measured separately from an additional full-draft planning reserve. No inputs
are truncated. Passing sampled states does not bound future repeated denials,
tool outputs, arbitrary generated drafts or token-boundary differences.

```bash
python -m scripts.audit_defense_contexts \
  --agent-tokenizer /home/dasp/models/Qwen3-14B-aria \
  --defender-tokenizer /home/dasp/models/Qwen3-1.7B \
  --output artifacts/private/ecpa-independent-training-preparation/context-audit.json
```

Use an environment with Transformers and the RouteBench dependencies. The
command requires committed tracked corpus sources and a clean revision; it
refuses to overwrite previous reports and records tokenizer-file hashes.

`defense.branching.collect_parent_branches` first finishes a logging parent,
then uniformly selects at most two of its encountered menus with multiple
choices. Conditional on that parent, state inclusion probability is `min(1,2/N)`;
it is recorded separately from task acquisition, enumerated branch assignment
(`1`) and subsequent logging-policy action probabilities. No evaluator score
or authoring route chooses the sampled states. All menu candidates are retained;
each repeat shares its starting continuation seed across candidates. Every
branch restores its own environment and consumed relay stages, uses a fresh
JSON agent and preserves prior violation/attack findings. Cutoffs remain censored;
an incomplete menu group cannot produce a choice target. Outcomes use the
existing evaluator and costs use actual continuation resource ledgers.

The kernel returns private collection records, not frozen training groups or
an authorization for a formal run. The later frozen runner must bind corpus,
review, models, seeds and protocol identity before persisting formal groups.
HTTP MockTransport integration tests verify the agent/simulator interface,
sampling, exact-offer rejection, failure/censoring and snapshot isolation. They
are transport fixtures, not model experiments or learned labels.

## Recorded preparation evidence

Source checkpoint: `f13c2ded768c42b6845cdf10675818cb4dc63082`, clean at both
audit starts. Reports are retained under ignored
`artifacts/private/ecpa-independent-training-preparation/` as
`authoring-audit.json` and `context-audit.json`; earlier preparation reports and
pilot outputs were preserved. These files bind corpus and tokenizer identities.

The authoring report passes all 12 candidates: 24 safe paths, 12 harmful
reference paths and 38 menu probes. All 12 independent reviews remain pending;
tune/calibration/test have zero materialized families. The reports deliberately
retain `formal_run_ready: false`.

| Sampled input | Checks | Maximum prompt tokens | Completion reserve | Minimum headroom |
| --- | ---: | ---: | ---: | ---: |
| Agent proposal | 104 | 3,459 | 768 | 3,965 |
| Agent exact-offer acceptance | 7 | 2,906 | 768 | 4,518 |
| Text receiver, representative benign draft | 140 | 3,518 | 768 | 3,906 |
| Text receiver, fixed attack text | 140 | 3,540 | 768 | 3,884 |
| Defender selector | 140 | 3,152 | 96 | 4,944 |

All 531 sampled inputs fit without truncation. A separate 104-state full-draft
sensitivity estimate reserves another 768 draft tokens and leaves at least
3,162 tokens; this is not a bound on arbitrary future inputs. No model weights
were loaded and no GPU inference, fitting or formal outcomes were collected.

Validation: 217 default tests passed; two existing optional learning tests were
skipped because that environment lacks Torch. Changed-file Ruff and strict mypy
passed. After the full suite, the strengthened branch-failure test was rerun
successfully. The actual local Qwen tokenizers were exercised by the saved audit.

Next work is semantic overlap/contract review and construction of tune,
calibration and held-out-mechanism test families, followed by binding the frozen
collection runner. Actual branch-target coverage must be measured before fitting;
menu availability alone cannot satisfy that requirement.
