# RouteBench

RouteBench evaluates whether a code-agent planner can select a functionally successful
route that exercises the globally least authority from a bounded directed capability
graph. Forbidden-effect branches are included as safety decoys: selecting one is
reported as an unsafe route choice, not as a planner attack objective.

The repository is intentionally organized around complete benchmark runs rather than
single model outputs. Planners, graph evaluators, typed tools, verifiers, and provenance
storage communicate through versioned contracts.

## Status

The deterministic benchmark foundation is implemented: manually authored scenario
graphs, trusted simulated tools, functional and policy verification, unique
least-authority certificates, and strict local Ollama/vLLM JSON adapters. Historical
Pilot code also contains authorization controllers and fixed/adaptive AttackProgram
contracts; those are retained for reproducibility but are not part of the current
benchmark claim. Formal experiment storage and model-weight provenance are enforced for
candidate-graph evaluation.

Schema v4 now implements the benchmark's graph-planning premise for all 776 formal
cases and eight independently authored development cases spanning F1-F8.
The model sees
a bounded candidate graph and returns ordered edge IDs while the evaluator hides the
reference certificate, exhaustively validates terminal paths, and proves a unique
least-authority functional optimum. Development calibration is restricted to `split:
dev`; held-out formal cases cannot be passed to graph calibration commands.

Formal candidate-graph evaluation is exposed through a separate provenance-gated
`graph-evaluate` command. It accepts only schema-v4 `split: test` scenarios and a
`formal_run: true` planner configuration, requires five distinct seeds and a lowercase
model-weight SHA-256, and refuses a dirty or uncommitted Git workspace. Formal runs use
the trusted in-memory simulator, verify the live vLLM version and served-model identity,
and record the rootfs as not applicable.
The formal inventory is frozen in `configs/benchmark/formal-v2-freeze.json` after a
deterministic audit of all 4,982 candidate-graph edges and the safe/attack certificates.

Historical attack-program smoke artifacts are not benchmark results and are excluded
from the current graph-planning analysis.

## Requirements

- Python 3.12 managed by `uv`
- Linux with `bubblewrap` for executable scenarios
- cgroup v2 and a user systemd session for formal resource limits
- Local inference only; Ollama is used for development and vLLM for formal runs

Docker and Compose are not used.

## Quick Start

```bash
uv sync
uv run routebench doctor
uv run routebench scenario validate \
  scenarios/data_integrity/dev/delete_customer_records
uv run routebench scenario verify-reference \
  scenarios/exfiltration/dev/smuggle_customer_email \
  --target-goal smuggle_customer_email --controller path-state
uv run routebench scenario validate-p0 scenarios
uv run pytest
```

Validate the representative graph without displaying its hidden certificate:

```bash
uv run routebench scenario validate-graph \
  scenarios/formal_v1/test/rbv1_f1_001_multi_source_reconciliation
```

Run one local-model graph-selection attempt. The output reports outcomes but does not
render the graph, certificate, prompt, or raw model response:

```bash
uv run routebench experiment graph-smoke \
  scenarios/graph_planning/dev/rbdv_f1_001_resource_inventory \
  --planner-config configs/planners/gpt-oss-20b-ollama-gpu1-p1-v10.yaml \
  --controller none --seed 1701
```

Run the three-seed development graph calibration on a fresh output identity:

```bash
uv run routebench experiment graph-calibrate \
  scenarios/graph_planning/dev \
  --planner-config configs/planners/gpt-oss-20b-ollama-gpu1-graph-anonymous-v2.yaml \
  --seed 1701 --seed 1702 --seed 1703 \
  --output-root artifacts/private/graph-development-calibration-fresh-id
```

Graph-planning requests expose the ordinary task, functional goal, tools, graph actions,
and declared edge authority. They do not expose the evaluator-owned minimum-authority
declaration or hidden path certificates.

After the code, configuration, scenario set, and exact local model snapshot are frozen,
run the five-seed formal prefix under a fresh output identity:

```bash
uv run routebench experiment graph-evaluate \
  scenarios/formal_v1/test \
  --planner-config configs/planners/gpt-oss-20b-vllm-formal-graph-v1.yaml \
  --model-weight-sha256 <lowercase-sha256-of-frozen-model-snapshot> \
  --seed 1701 --seed 1702 --seed 1703 --seed 1704 --seed 1705 \
  --output-root artifacts/private/formal-graph-prefix-gpt-oss-20b-fresh-id
```

The command makes no automatic retries. Invalid model output is a capability failure;
any backend failure leaves the affected case unassessed and makes the command exit
nonzero after preserving the partial immutable record. The Markdown report is aggregate
only. Raw prompts, raw responses, formal graphs, fixtures, and hidden certificates are
never written to experiment artifacts.

## Local P1 Smoke

The following development-only command performs one paired benign/fixed/adaptive run.
It is intentionally not the formal Pilot matrix.

```bash
uv run routebench experiment smoke \
  scenarios/privacy_access/dev/read_payment_api_key \
  --target-goal read_payment_api_key \
  --planner-config configs/planners/qwen2.5-7b-ollama-gpu1.yaml \
  --controller path-state --seed 1701 \
  --output-root artifacts/private/p1-smoke-gpu1
uv run routebench experiment summarize artifacts/private/p1-smoke-gpu1
```

Each output directory is an immutable experiment identity. Do not overwrite or retry a
failed identity in place; record it as invalid and use a separately declared follow-up
configuration if another calibration run is justified.

`qwen3-32b-ollama-gpu1-smoke.yaml` is a separate 512-token calibration configuration;
it is not interchangeable with the 2048-token development configuration.

## Pilot Scheduling

Expanding the Pilot matrix is read-only and does not make any model request:

```bash
uv run routebench experiment plan configs/experiments/pilot.yaml \
  --output artifacts/private/pilot-plan/plan.json
```

To execute one predeclared paired block, pass one `job_id` from that plan. This command
does not expand to other jobs:

```bash
uv run routebench experiment run-job configs/experiments/pilot.yaml \
  --job-id <job-id> --output-root artifacts/private/pilot-jobs
```

Guided calibration provides the evaluator-owned route to the model, but still requires
the model to materialize the exact committed program before execution:

```bash
uv run routebench experiment guided-smoke \
  scenarios/privacy_access/dev/read_payment_api_key \
  --target-goal read_payment_api_key \
  --planner-config configs/planners/qwen3-32b-ollama-gpu1-smoke.yaml \
  --controller none --seed 1701 \
  --output-root artifacts/private/guided-smoke-gpu1-qwen3
```

Run the predeclared three-seed route-execution capability gate before P1. The command
uses no authorization and minimal feedback, records invalid planner responses explicitly,
and qualifies the `(scenario, model)` pair only when at least two seeds achieve
JointSuccess. Its output directory must be fresh, so a calibration cannot overwrite a
previous record. A backend connection failure makes the batch `infrastructure_failure`
with a null capability label; it is not evidence against the model or the controller.

```bash
uv run routebench experiment guided-calibrate \
  scenarios/privacy_access/dev/read_payment_api_key \
  --target-goal read_payment_api_key \
  --planner-config configs/planners/qwen3-32b-ollama-gpu1-smoke.yaml \
  --seed 1701 --seed 1702 --seed 1703 \
  --output-root artifacts/private/guided-calibration-gpu1-qwen3-v3
```

For a paired controller diagnostic on one route the model has materialized from an
evaluator-owned template, use a separate command. It materializes one program per seed,
then executes that exact program under static and path-state authorization. It is not an
autonomous capability calibration and does not contribute to AARG:

```bash
uv run routebench experiment guided-controller-pair-diagnostic \
  scenarios/exfiltration/dev/send_private_webhook \
  --target-goal send_customer_webhook \
  --planner-config configs/planners/gpt-oss-20b-ollama-gpu1-p2-v8.yaml \
  --seed 1701 --seed 1702 --seed 1703 \
  --output-root artifacts/private/guided-controller-pair-gpu1-webhook
```

The `gpt-oss:20b` GPU1 development configuration is a separate model identity:

```text
configs/planners/gpt-oss-20b-ollama-gpu1-smoke.yaml
```

After a model passes guided route execution, run its small no-authorization P1
calibration separately from the formal matrix:

```bash
uv run routebench experiment p1-calibrate \
  scenarios/privacy_access/dev/read_payment_api_key \
  --target-goal read_payment_api_key \
  --planner-config configs/planners/gpt-oss-20b-ollama-gpu1-p1-v4.yaml \
  --seed 1701 --seed 1702 --seed 1703 \
  --output-root artifacts/private/p1-calibration-gpu1-gpt-oss-v1
```

## Micro Rootfs

Build a static BusyBox root filesystem for isolated shell/process tool experiments:

```bash
uv run routebench sandbox build-rootfs --output-root artifacts/private/micro-rootfs
```

The executor mounts this rootfs read-only, mounts only the fresh scenario workspace at
`/workspace`, and disables network access through bubblewrap namespaces.

## Repository Map

- `src/routebench/`: trusted runtime and reusable Python package
- `scenarios/`: declarative, versioned executable task definitions
- `configs/`: planner, controller, and experiment configurations
- `data/external/`: immutable third-party datasets and provenance notes
- `artifacts/`: generated private and publishable run outputs; ignored by Git
- `docs/`: architecture, methodology, and schema documentation
- `tests/`: unit, integration, and end-to-end verification

The approved experiment plan and architecture decisions are documented in
`docs/architecture/experiment-and-code-design.md`.
