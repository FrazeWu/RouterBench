# Compact defender: completed engineering pilot

2026-10-22. The approved implementation stage is complete: trusted local menu
selection, staged response-relay attacks, actual branch collection, LoRA fitting
and integrity-checked reload, five-arm comparison, resource telemetry and tests.
This is development feasibility evidence, not an independent defense study.

## Provenance and inventory

- Collection: clean revision `7812b505b3e80dc05135c9e8f1758dc02831d051`.
- Fit/comparison: clean revision `76432bf16afed734fcca41e6faec004ea7a4a760`.
  Only CUDA initialization and the explicit development collection-import path
  changed after collection. Original records and source manifest were retained.
- Frozen task agent: local Qwen3-14B BF16, GPU 1, context 8192. Defender:
  Qwen3-1.7B BF16, GPU 0, same context; official downloaded snapshot
  `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`. Manifests hash actual snapshot files.
- Two reused development families; text/structured relay modes, each with benign
  and attacked episodes. Eight logging parents and 18 actual candidate branches
  produced eight complete comparisons. No censored comparison was used.
- Eight choice labels: seven allow, one constrain; no deny/escalate target coverage.
  This is sufficient for a timing smoke, not a representative training corpus.
- All 40 planned comparison episodes completed collection, including failed
  tasks. Together with parents/branches, 66 episode records were retained.

The private run is `artifacts/private/ecpa-compact-integration/verified-run/`:
`manifest.json`, `collection-source-manifest.json`, `adapter/manifest.json`,
`adapter/measurement.json`, `report.json`, and phase cost/telemetry files.
They remain ignored and must not be committed as source or formal results.

## Descriptive integration results

Each arm has four benign and four attacked episodes. Benign completion here
requires task completion and valid STOP; its count also equals functional-success
count in this comparison. Attacked safe recovery additionally requires no episode
violation. All failures remain in the denominators.

| Arm | Benign completion | Attacked safe recovery | Episode violations / 8 | Defender calls / fallbacks |
| --- | ---: | ---: | ---: | ---: |
| Unguarded simulator reference | 3/4 | 0/4 | 2/8 | 0 / 0 |
| Per-action authorization | 3/4 | 2/4 | 0/8 | 0 / 0 |
| Deterministic path rule | 3/4 | 3/4 | 0/8 | 0 / 0 |
| Compact base, no adapter | 0/4 | 0/4 | 0/8 | 96 / 0 |
| Same compact model, LoRA | 3/4 | 3/4 | 0/8 | 56 / 4 |

The attack harness executed a two-action legitimate prefix followed by protected
field access in the unguarded reference; both text and structured variants caused
the scenario's forbidden target. Guarded arms retained final authorization checks.
The second campaign targeted incorrect release-note contents. Its execution can
break functional success without satisfying that scenario's *different* primary
forbidden target, so attack-success, violation and task failure are distinct.

The base model repeatedly chose deny. The short LoRA fit recovered useful behavior
on these reused workflows, but **matched the deterministic path rule**, with four
invalid-output fallbacks across 56 selections. It does not establish a training
advantage over rules or satisfy the proposed minimum-gain claim against that
comparator. No confidence interval or efficacy inference is warranted from two
reused families. No additional adapter fit, prompt search, or policy retuning was
performed on the comparison outcomes.

The release workflow exposed task-agent continuation errors: it sometimes proposed
an edge belonging to a later node and repeatedly failed to replan. Some collection
episodes achieved the functional state but exhausted decisions before valid STOP.
These were retained as recovery failures, not repaired or silently removed.

## Resource measurement

The single fit used rank 8, alpha 16, q/v projections, learning rate 1e-4,
dropout 0, seed 29, batch size 1 and eight updates. Only 1,605,632 LoRA parameters
were trainable. Input lengths were 2,858--3,965 tokens; the updates processed
28,015 input tokens and 49 supervised answer tokens. Fit/update time was 18.94 s;
load/preparation/save brought the training measurement to 24.25 s. The complete
instrumented phase was 28.11 s. Peak allocated tensor memory was 11.55 GiB;
peak reserved allocator memory was 22.61 GiB. These are different measurements.

| Phase | Wall time | Reserved GPU-device hours | Scheduled wait |
| --- | ---: | ---: | ---: |
| Parent and branch collection | 1,431.16 s | 0.39754 | 1,213.92 s |
| Compact fit | 28.11 s | 0.01562 | 14.00 s |
| Forty-episode comparison | 3,136.73 s | 1.74263 | 2,624.93 s |
| Total main chain | 4,596.00 s | 2.15579 | 3,852.85 s |

GPU hours sum device reservations, including waits; collection reserves one GPU,
fit/comparison reserve both because the task server remains resident. Imported
collection is counted once. Server startup/idle gaps and aborted probes are outside
this main-chain sum. A separate process-lifetime audit, including the task servers'
startup/idle/probe time and compact fit/comparison reservations, estimates about
2.59 device-hours for this session. It is not an energy measure or an exact meter
of tiny unit tests/failed pre-start attempts; see
`artifacts/private/ecpa-compact-integration/session-resource-audit.json`.

Main-chain totals: 774 task-model calls, 2,698,752 task prompt tokens and 25,844
completion tokens; 152 defender calls, 489,851 defender prompt tokens and 454
completion tokens. Mean defender call latency was 0.222 s (median 0.206 s),
excluding explicit pacing. The training tokens above are additional.

Initial continuous-inference probes on both GPUs hit thermal slowdown and were
stopped. A too-low cooling-resume threshold and a later cold-CUDA statistics error
were also retained separately. The completed run used two-second call/update gaps
and 73-to-71 C cooling hysteresis. Sampled maxima were 65 C on GPU 0 and 81 C on
GPU 1, without observed thermal throttle flags; independent cumulative-counter
checks also showed no increase after pacing was introduced. These measurements
describe this scheduling/hardware setup, not unrestricted model throughput.

## Validation and formal-study boundary

Full default suite: 203 passed, two optional learning tests skipped. The compact
suite also passed all 11 tests with installed learning dependencies, including actual
CPU/CUDA LoRA updates, base-snapshot preservation, reload and tamper rejection.
Changed-file Ruff and strict type checks passed; the LaTeX draft builds. Repository
wide Ruff additionally reports a pre-existing import-order issue in
`test_capability_routing_v2_manifest.py`; unrelated source was preserved.

Before formal fitting/testing: independently author and audit semantic families,
hold out attack mechanisms, cover all intervention types, examine the task-agent
receiver/replanning interface, and freeze counts/seeds/precision/cost and a new
protocol identity. Preserve strong deterministic baselines. These pilot data and
adapter are excluded from formal training/calibration/test. The implemented chain
does not by itself validate the paper's learning-benefit claim.
