# Formal v13 Multi-Family Evaluation Plan

## Purpose

The existing 776-case v13 result contains three Qwen3 checkpoints. This plan adds
family and scale coverage while keeping the task graph, seeds, interface, decoding
parameters, and evaluator unchanged.

## Frozen protocol

- Protocol: v13 permutation-balanced incremental-edge graph evaluation.
- Cases: the held-out `scenarios/formal_v1/test` inventory (776 cases for the full run).
- Seeds: `1701`, `1702`, `1703`, `1704`, `1705`.
- Temperature: `0.0`; top-p `1.0`; max tokens `2048`; context window `32768`.
- Primary endpoint: `OptimalPathSuccess`; capable case requires at least 3/5 seeds.
- Secondary outcomes: FunctionalSuccess, PolicyCompliance, and attack-path selection.
- Statistical unit: case; seed attempts are repeated measurements.

## Model matrix

| Family | Small | Middle | Large |
|---|---|---|---|
| Qwen3 | Qwen3-8B (existing) | Qwen3-14B (existing) | Qwen3-32B-AWQ (existing) |
| Qwen2.5 | Qwen2.5-7B | Qwen2.5-14B | Qwen2.5-32B |
| Llama | Llama3.1-8B | - | Llama3.3-70B-AWQ |
| Gemma | Gemma2-9B | - | Gemma2-27B |
| Mistral | Mistral-7B-Instruct-v0.3 (extension) | Mistral Small 3.2-24B | - |

The extension batch adds a runnable Mistral 7B checkpoint so that the pilot has
at least three independently implemented families at small and middle scales.
It is evaluated under the same v13 protocol and is reported with its own
configuration and model hash.

| Extension family | Small | Middle |
|---|---|---|
| Mistral | Mistral-7B-Instruct-v0.3 | - |
| Gemma | - | Gemma3-12B-IT (text-only serving) |

The initial cross-family pilot uses the shared 100-case prefix already materialized
under `artifacts/private/formal-graph-v12-scale-100-20260910/input-100-v2`. A model
enters the 776-case run only after its pilot produces a complete, valid five-seed
record with zero backend failures. Pilot results remain prefix diagnostics and are
not pooled with the 776-case estimate.

Gemma3 is held out of this matrix until its processor-serving failure is repaired;
that infrastructure issue must not be reported as a model capability result.

## Comparison contract

The paired comparison script must use the same case IDs within each protocol, report
case-level bootstrap intervals, and separate attempt-level rates from capable-case
rates. No p-value-only ranking or causal model-size claim is permitted.
