# Visualization Preview

When creating or updating an HTML visualization for the user, start a local static HTTP service that exposes the generated artifact and provide its `http://localhost/...` URL. Do not rely only on a filesystem link or the Codex file preview.

Use an unused local port, keep the service scoped to the artifact directory, and verify the page returns HTTP 200 before reporting it.

# Capability-Routing Authoring

For every new capability-routing task, manually select primitive adapters, a concrete provider-resource-mode binding from `capability_binding_pools`, planning skills, and a workflow template from `catalog/capability_universe.yaml`. `catalog/capability_catalog.yaml` is only the executor-level adapter registry. Do not invent unregistered capabilities or disclose the selected reference route, private cost labels, or certificates in the task prompt. Use the selected catalog items to create multiple viable, dependency-constrained paths before defining the evaluator-owned optimum.

# Git Workflow

Use Git as the provenance boundary for benchmark and experiment changes.

- Before editing or committing, run `git status --short` and preserve existing user changes. Never use `git reset --hard`, `git clean -fd`, or `git checkout --` to make the tree appear clean.
- A clean worktree means all intentional source, catalog, scenario, configuration, documentation, and test changes are committed. Runtime outputs under `artifacts/` remain ignored and must not be force-added.
- Group one coherent benchmark/protocol change into one checkpoint commit. Use an explicit prefix such as `bench:`, `eval:`, `fix:`, `test:`, or `docs:` and include the protocol or batch name in the subject.
- Before committing, inspect `git diff --cached --stat`, `git diff --cached --check`, and the staged file list. Reject credentials, tokens, private model responses, raw prompts, fixtures containing secrets, and generated runtime artifacts.
- Run the relevant tests and linters before the commit. After committing, verify `git status --short` is empty and record `git rev-parse HEAD` in the experiment provenance.
- Never amend, rebase, force-push, or rewrite a published benchmark checkpoint. Push only when explicitly requested; ordinary development checkpoints are local until reviewed.
- A formal evaluation may start only from the committed, clean revision recorded in its run manifest. If new code or scenario changes are needed, create a new checkpoint and freeze a new protocol identity instead of modifying a prior result.
