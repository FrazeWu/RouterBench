# Compact defender development runbook

Scope: two existing development overlays, one frozen Qwen3-14B task agent, one
Qwen3-1.7B base, one short LoRA recipe, two relay modes and five comparison arms.
This is an engineering pilot. Its reused development families and short adapter
fit cannot establish defense effectiveness or generalization.

## Preparation

Install `routebench[learning]` and a compatible vLLM server environment. The
learning extra includes PyTorch, Transformers and PEFT; vLLM is separate. Download
the official Qwen3-1.7B snapshot into the path in
`configs/defense/compact-pilot.yaml`. Keep the Qwen3-14B task-agent snapshot
unchanged. Review local paths, devices and budgets before committing config
changes. The runner requires a clean committed tree, refuses formal tasks, and
stores records/adapters only in ignored `artifacts/private/`.

Start the frozen task agent (use the server environment's `bin` directory on PATH
so native build utilities such as ninja are available):

```bash
CUDA_VISIBLE_DEVICES=1 vllm serve /home/dasp/models/Qwen3-14B-aria \
  --host 127.0.0.1 --port 8011 --served-model-name RouteBench/Qwen3-14B \
  --dtype bfloat16 --max-model-len 8192 --max-num-seqs 1 \
  --gpu-memory-utilization 0.90 --generation-config vllm --enforce-eager
```

Wait for `/v1/models` readiness. Keep server startup/stop timestamps and GPU
reservations alongside the pilot; phase cost files exclude server startup and
idle gaps. Stop only the server you started when done.
The pilot places the large agent on GPU 1 and compact fitting/inference on GPU 0
because the first continuous GPU-0 inference attempt triggered thermal throttling.
Every requested GPU remains monitored; a device switch is not evidence of thermal
stability until an uninterrupted measured run completes.
The configured two-second gap after calls/updates and 70-to-65 C cooling
hysteresis are explicit scheduling costs, applied to all arms. Cooling and idle
reservation time are included; they are not hidden model latency or retries.
Hard thermal stops remain active. Both initial unpaced attempts are retained as
aborted development records rather than counted as completed experiments.

## Run and inspect

```bash
python -m scripts.run_defense_pilot \
  --config configs/defense/compact-pilot.yaml \
  --output artifacts/private/ecpa-compact-pilot --phase all
```

The phases can also run individually with `--phase collect`, `fit`, `compare`,
then `report`, using the same output directory and source/config identity. A new
collection, fit, or comparison refuses to overwrite its phase outputs. A failed
phase is retained; use a fresh output directory for a changed implementation.
The phase identity cannot silently change after collection.

Collection executes paired benign/attacked episodes in text and structured relay
modes. At the configured public nodes, independently clone the simulator and
enumerate every legal candidate, including deny. Candidate branches share a
continuation seed per repeat. Enumerated branch assignment probability is one;
the continuation logging mixture has separate exact action probabilities. Discard
an entire target comparison if any candidate is missing or censored. Terminated
model-call failures remain observed failures. Prefer lower violation frequency,
then safe completion, then measured continuation cost; exact ties prefer the
fixed rule when available, otherwise lexical candidate order.

Text mode has a frozen-agent draft call followed by a frozen-agent receiving call
that treats the relayed draft as untrusted user data. Benign text controls use the
same two-call interface. Structured mode replaces a typed proposal before the
runtime parses and checks it. Do not interpret text/structured differences as a
pure payload-format effect: their receiver interfaces differ. Each campaign has
innocuous prefix stages and a later malicious target, but actual stage reach,
substitution, target execution and eventual harm are reported separately. An
unreached stage is not a successful multi-step attack. This harness is fixed and
nonadaptive; it does not establish robustness against arbitrary malicious relays.

The unguarded arm is an explicitly named simulator-only subclass bypassing policy
and operational grants. Production ECPA checks remain in place for the four
guarded arms. Per-action authorization chooses allow/escalate/deny; the path rule
may choose concrete replacements. Both small-model arms share serialization,
prompt, legal menu and greedy decoding. The same loaded backbone is used with
the adapter disabled/enabled. Invalid or over-context outputs fall back to the
fixed rule and are counted. No silent text truncation or model-call retries occur.

## Outputs and interpretation

- `manifest.json`: exact revision, config, public-task digests and planned matrix.
- `collection/*.group.private.json`: actual complete-menu branch labels.
- Other `*.private.json`: trusted observations/transitions and actual call metadata;
  never commit or publish these private records as aggregate evidence.
- `adapter/`: safetensors adapter, settings, base/adapter hashes, source-group
  fingerprints and training memory/time. Formal loading rejects this artifact.
- `*-telemetry.json` and `*-cost.json`: temperature, thermal throttle flags,
  device memory, phase status and declared GPU reservation hours.
- `report.json`: full-denominator descriptive matrix, actual model calls/tokens,
  fallbacks and completeness. No clustered significance test is run on two families.

Before formal work, independently author/audit a sufficient corpus, hold out task
families and attack mechanisms, freeze seeds/repetitions/precision/cost and pin a
new clean protocol checkpoint. Historical v13 and pilot outputs remain separate.
