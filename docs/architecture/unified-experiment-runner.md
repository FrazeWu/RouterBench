# Unified Experiment Runner

`routebench experiment suite` is the single bookkeeping entry point for a dry-run
experiment pass. It validates scenario material, audits v4 candidate graphs, and
summarizes existing aggregate result files. It never invokes a model, writes prompts,
or reads raw model responses.

## Small validation

Run one development graph before any model-backed evaluation:

```bash
uv run routebench experiment suite \
  --scenario-root scenarios/graph_planning/dev/rbdv_f1_001_resource_inventory \
  --artifacts-root artifacts/private \
  --output-root artifacts/private/unified-suite-smoke
```

The command writes `unified-experiment-report.json` and
`unified-experiment-report.md`. Use `--limit N` to validate a bounded prefix and
`--split dev|test` to select a split before applying the limit.

## Formal model evaluation

The suite is deliberately separate from model execution. After the smoke report is
reviewed, use the existing frozen commands for the declared protocol:

```bash
uv run routebench experiment graph-calibrate ...
uv run routebench experiment graph-evaluate ...
```

Their immutable run manifests and aggregate summaries are automatically collected by
the suite for cross-run analysis.
