# RouteBench Manuscript Audit

Date: 2026-10-19. This is a working-paper audit, not a claim that the study is
ready for submission. Scope: integrate the existing frozen evaluation artifacts
without running new model evaluations, changing frozen scenarios, or inventing
results.

## Author-Confirmed Decisions (2026-10-08)

- Repair the stop/continue interface and public credit wording under a new protocol
  identity. Historical results remain unchanged. Implementation and freezing are pending.
- Keep RouteBench as the primary contribution and defense as an auxiliary extension.
- Plan four minimum conditions: no defense, strong public-input deterministic rules,
  uniform-collection CQL, and diagnostic-guided CQL, with matched guarded information,
  menus, permissions, approvals, and collection budgets.
- Build independent training, tuning, and calibration data; reserve test cases for
  assessment and hold out semantic families for defense generalization.
- Use the local two A100 GPUs; resource inspection confirmed two A100-PCIe-40GB cards,
  approximately 196 GiB host RAM, about 700 GB free disk, and no NVLink connection.
  Proposed inference settings and existing CQL defaults are recorded in
  `docs/architecture/rl-defense-protocol.md`; they are not measured performance.
- Public code, synthetic task data, and evaluation scripts, including an anonymous
  review version, are authorized. Original code and self-authored task files use
  GPL-3.0-only, with canonical GPLv3 text in `LICENSE`. Third-party licenses remain
  unchanged. Archives and publication have not occurred.
- All self-authored scenario content is synthetic. The author reports a completely
  random 10% manual sample, one reviewer, and no issues found. Exact sample size,
  identifiers, selection seed, and review notes were not provided. Do not infer an
  exact count from 776 or claim validation of every case or inter-rater agreement.
- Do not add a manuscript discussion of author verification. This preference is
  not an attestation that all prose/references were read or independently verified.
- No submission deadline or ARR cycle is set.
- The strict safety comparison requires a one-sided 95% upper limit on the
  learned-minus-rule violation difference below zero and a lower limit on the
  benign-success difference at least -0.02. The strongest rule comparator is frozen
  from tuning data. Diagnostic-guided versus uniform CQL remains a separate comparison.
  Family-cluster uncertainty retains repeated presentations and all training seeds.
- If common sound guards give all guarded controllers zero violations, additional
  violation reduction is unachievable. Report utility/cost results separately and
  do not claim the strict safety criterion was met. No result was generated here.

## Deliverables and Evidence Boundary

- `main.tex` remains the document in the current editor.
- The official `acl.sty` is embedded unchanged for single-file compilation.
- `references.bib` holds 19 citation records; the official ACL-formatted
  bibliography is embedded in `main.tex`. Future citation changes must update
  both representations.
- Abstract, introduction, related work, formal problem, benchmark construction,
  evaluation contract, diagnostic design, auxiliary defense, discussion,
  conclusion, limitations, ethics, and implementation appendices are written.
- The experiments section now reports existing formal v13, difficulty-stratified,
  component-ablation, model-free baseline, ordering anti-leakage, and checkpoint
  stability artifacts. No new run was started.
- The current benchmark and a trusted ECPA intervention-boundary scaffold are
  implemented. Counterfactual diagnostics, persistent diagnostic monitors, the
  learned controller, its training corpus, and defense results remain unvalidated.
- ECPA needs a separately frozen interleaved execution/replanning protocol;
  v13's pre-replay route selection is not itself the proposed RL environment.
- The runtime/transition appendix specifies stateless planner calls, accepted
  replacement requests, post-intervention completion witnesses, fixed approval
  semantics, bounded decisions, and actual intervention-dependent rollouts. The
  trusted ECPA scaffold now implements the guard, witness, approval, replanning,
  probability-accounted collection helper, and value-free transition-record
  boundary; a task corpus, learning, and empirical validation remain pending.
- The selectability-repair appendix defines a proposed explicit stop/continue
  interface and its validation requirements. It is not implemented by this edit.

## Implementation Alignment

The benchmark source revision inspected is
`d09969477826a8913905613a76199eeb0a37fee5`. The paper worktree is modified;
this is not a clean formal-evaluation checkpoint. Existing user changes to
`main.tex` were preserved. No new formal experiment was started.

| Statement | Authority / qualification |
| --- | --- |
| 776 cases and 4,982 edges | `configs/benchmark/formal-v2-freeze.json` |
| 761 unique exact optima; 15 equal-rank cases | Same freeze; do not claim universal uniqueness |
| Four public ordinal dimensions, lexicographic endpoint | `src/routebench/runtime/graph.py` and `src/routebench/evaluation/graph_selection.py` |
| Pareto status is secondary in the scorer | Planner payload and protocol prose conflict; the two sets coincide in this inventory, not necessarily future ones |
| v13 stops at the first terminal | `src/routebench/planners/local_json.py` |
| Path planning occurs before replay | Do not describe v13 as observation-driven execution |
| Five seeds and at least 3/5 exact successes | Protocol endpoint; seeds are within-case measurements |
| Static minimum-authority baseline | Privileged evaluator information, not a deployable public-input baseline |
| Grant attenuation and recovery | Established control ideas; no first-invention claim |
| Offline CQL | Existing algorithm, not a new RL algorithm |

The formal inventory has only 3--6 terminal paths per case. Safe certificates
have 1--5 actions. Five nominal length bands are defined, but only three are
populated. The current development directory has 11 cases and does not supply
the public ordinal attributes of the formal inventory. It is not assumed to be
sufficient RL training data.

## Integrated Results Audit

The historical results inserted into `main.tex` retain their original protocol
identities:

- `artifacts/private/formal-v13-multifamily-paired-bootstrap-20261005.md`:
  776 cases, five paired models, five repeated seeds, and 10,000 paired case
  bootstrap resamples. The paper reports aggregate rates and selected paired
  differences; six additional full-v13 model rows are sourced from their
  publishable run reports and use the same scenario inventory and seed protocol.
- `artifacts/private/formal-v13-ablation-20261003/qwen3-14b-v12-order/experiment-report.md`
  and `artifacts/private/formal-v13-ablation-20261003/qwen3-14b-v13-permuted/experiment-report.md`:
  paired 100-case ordering check. The original ordering gives 460/500 exact
  attempts, 92 capable cases, and no attack paths; the permuted ordering gives
  400/500 exact attempts, 85 capable cases, and 27 attack-path selections.
- `artifacts/private/local-v13-recovery-20261008/qwen3-14b/formal/experiment-report.md`:
  full 776-case recovery-checkpoint run used only as checkpoint stability, not
  as a new independent model row.
- `artifacts/private/formal-v3-776-20260929/failure-difficulty-analysis.md`:
  Qwen3-14B route-length, effect-family, graph-horizon, candidate-path, and
  simulator-error diagnostics. The main text retains route-length/effect-family
  results; the appendix retains the remaining tables.
- `artifacts/private/component-ablation-v1-fixed-paired-bootstrap-20261004.md`:
  96 paired cases, five graph variants, and 2,400 valid attempts. This is labeled
  as a controlled diagnostic subset, not a representative replacement for the
  formal benchmark.
- `artifacts/private/formal-v3-776-20260929/deterministic-baselines.md`:
  model-free negative controls. The original-order first-declared result is
  labeled as a presentation-leak diagnostic, not a capability baseline. The
  ordering ablation makes the leak explicit and documents the v13 permutation.

The paper explicitly states that no RL, learned ECPA, or defense-improvement
experiment has been run. The trusted scaffold is a simulator boundary, not a
learned controller. Result tables and machine-readable CSV inputs are present under
`paper/figures/`; the model CSV now contains all eleven full-v13 model rows,
and `formal_diagnostics.pdf` visualizes the model, route-length, and component
ablation results. The plotting source uses Python/matplotlib; vector, raster,
alignment, text-size, and collision checks pass.

## Interface Validity Finding

Bounded enumeration permits a path to continue through a terminal; v13 does
not. Checking every candidate route, rather than certificates alone, yields:

```text
cases: 776
no_v13_reachable_exact_optimum: 45
no_v13_reachable_safe_functional_route: 45
no_v13_reachable_attack_route: 279
```

Certificate-only counts are different: 45 safe certificates and 341 attack
certificates contain an interior terminal. Alternate attack routes explain why
341 is not the number of cases without a reachable unsafe alternative.

Reproduction from the repository root, using the existing environment:

```bash
.venv/bin/python - <<'PY'
from collections import Counter
from pathlib import Path
from routebench.scenarios.loader import load_scenario
from routebench.runtime.graph import evaluate_candidate_paths, public_route_optimality

counts = Counter()
for root in sorted(Path("scenarios/formal_v1/test").iterdir()):
    if not (root / "scenario.yaml").is_file():
        continue
    bundle = load_scenario(root)
    graph = bundle.definition.graph
    edges = {edge.edge_id: edge for edge in graph.edges}
    terminals = set(graph.terminal_nodes)

    def reachable(path):
        return not any(edges[edge].target in terminals for edge in path[:-1])

    paths = evaluate_candidate_paths(bundle)
    optimum = public_route_optimality(bundle, paths)
    counts["cases"] += 1
    counts["no_v13_reachable_exact_optimum"] += not any(
        reachable(path) for path in optimum.exact_optimal_edge_ids
    )
    counts["no_v13_reachable_safe_functional_route"] += not any(
        path.functional_success and path.policy_compliance
        and not path.attack_target_ids and reachable(path.edge_ids)
        for path in paths
    )
    counts["no_v13_reachable_attack_route"] += not any(
        path.attack_target_ids and reachable(path.edge_ids) for path in paths
    )
print(dict(counts))
PY
```

This is a deterministic structural/replay audit, not a model experiment.
Do not attribute unavailable optima to model incapability or unavailable unsafe
branches to successful defense. The finding remains in the main text.
Filtered analyses need distinct identities and explicit denominators. A repaired
stop/continue protocol requires a new checkpoint, freeze, and fresh measurement;
old cases, manifests, and results must not be silently rewritten.

## Public Credit-Contract Audit

The current public payload contains both
`comparison: lexicographic_minimize_exposure_scope_evidence_interaction` and
`tie_policy: all_public_pareto_optimal_paths_receive_primary_credit`.
`src/routebench/planners/local_json.py` supplies this payload to both full-path
and incremental selection. However, `GraphSelectionResult.optimal_path_success`
in `src/routebench/evaluation/graph_selection.py` uses exact optimality.
The prose in `docs/architecture/capability-routing-v2-public-contract.md` also
describes Pareto-primary credit. This is a genuine contract inconsistency,
not merely a stale document that models cannot see.

A deterministic full-inventory set comparison on the unchanged source yields:

```text
cases: 776
pareto_differs_from_exact: 0
cases_with_v13_reachable_pareto_nonexact: 0
extra_pareto_paths: 0
v13_reachable_extra_pareto_paths: 0
```

Thus there is no scoring-set difference within the current frozen cases. This
does not establish that contradictory wording has no effect on model behavior,
and cannot justify the same contract for future graphs with genuine trade-offs.
The manuscript discloses the inconsistency and the coincident sets. The proposed
repair requires explicit exact-primary/Pareto-secondary prompt/scorer agreement.

Reproduction uses the same scenario-loader/replay loop as the interface audit:
compare `set(optimum.pareto_optimal_edge_ids)` with
`set(optimum.exact_optimal_edge_ids)` for each bundle, and check interior
terminals for any set difference. Only aggregate counts were printed; no model
was called, no fixture/prompt/response was exported, and no frozen file changed.

## Citation Verification

This was a targeted related-work search, not an exhaustive systematic review.
Primary metadata and relevant claims were checked during this writing session.
Human author verification remains required.

| Work | Primary record / depth used |
| --- | --- |
| Saltzer and Schroeder | Crossref DOI `10.1109/PROC.1975.9939`; metadata |
| Sabelfeld and Myers | Crossref DOI `10.1109/JSAC.2002.806121`; metadata |
| InjecAgent | https://aclanthology.org/2024.findings-acl.624/ |
| AgentDojo | arXiv `2406.13352`; abstract, metadata, Crossref venue |
| ToolEmu | arXiv `2309.15817`; abstract/metadata, authors' repository citation |
| AgentHarm | arXiv `2410.09024`; metadata and ICLR acceptance comment |
| Agent-SafetyBench | arXiv `2412.14470`; metadata, authors' repository citation |
| ToolPrivBench | arXiv `2606.20023`; metadata and relevant HTML main text |
| StruQ | https://www.usenix.org/conference/usenixsecurity25/presentation/chen-sizhe |
| CaMeL | arXiv `2503.18813`; abstract/metadata, not a successful full-text check |
| Progent | arXiv `2504.11703`; current revision and relevant HTML main text |
| AgentGuard | arXiv `2605.28071`; abstract/metadata |
| APPA | arXiv `2607.24625`; relevant HTML main text |
| CONTINUITY | arXiv `2609.05269`; abstract/metadata |
| RACG | arXiv `2606.13884`; relevant HTML main text |
| Shielding | arXiv `1708.08611`, Crossref DOI `10.1609/aaai.v32i1.11797` |
| CQL | https://papers.nips.cc/paper/2020/hash/0d2b2061826a5df3221116a5085a6052-Abstract.html |
| CPO | https://proceedings.mlr.press/v70/achiam17a.html |
| Sentence-BERT | https://aclanthology.org/D19-1410/ |

RACG's abstract and available HTML differed; claims follow the inspected main
text, not the inconsistent generic abstract. Progent uses its original arXiv
year, 2025, while the comparison uses the inspected current revision. Unverified
refereed versions are not invented. The proposed MiniLM checkpoint's exact
snapshot and license still need confirmation before use.

## ACL Format Gates

Official sources checked for this draft:

- https://aclrollingreview.org/cfp
- https://aclrollingreview.org/authorchecklist
- https://acl-org.github.io/ACLPUB/formatting.html
- https://aclrollingreview.org/responsibleNLPresearch
- https://github.com/acl-org/acl-style-files

Use the unmodified ACL review style: A4, two columns, anonymized authors, page
and line numbers, embedded fonts. A long paper allows at most eight content
pages through the conclusion. Dedicated limitations and ethics follow the
conclusion and do not count toward that limit; references and double-column
appendices follow. The abstract limit is 200 words.

Compile the existing main document locally:

```bash
cd /home/dasp/projects/RouteBench/paper
/home/dasp/.local/bin/tectonic --keep-logs --keep-intermediates main.tex
```

Inspect `main.log`, `pdfinfo main.pdf`, `pdffonts main.pdf`, text extraction,
and rendered pages. Local build products and visual-review images are ignored
runtime outputs, not benchmark source. The editor's built-in compile must be
reported separately: a pending request is not a successful compilation.

Checks completed for the current source:

- Tectonic 0.17.0 compiled the same main document and generated `paper/main.pdf`;
  the current recheck completed on 2026-10-19.
- Main text through the conclusion occupies eight pages after integrating the
  existing results; the complete draft is fourteen pages including references
  and appendices. The eight-page ACL content budget is currently met.
- The abstract contains 135 whitespace-delimited words.
- All 19 cited keys have metadata and embedded entries. The embedded
  bibliography matches the official BST-generated `main.bbl`; labels are unique.
- The embedded ACL style is byte-identical to the sibling official `acl.sty`.
- No unresolved citations/references or overfull boxes remain. All PDF fonts
  are embedded. Rendered pages were visually inspected.
- A local single-file TeX check hid sibling style, bibliography, BST, BBL, AUX,
  and OUT inputs. The first-pass log confirmed creation of `./acl.sty` from the
  embedded block; the converged check succeeded without unresolved references.
  It generated only ignored XDV/log outputs, not another PDF or document.
- Built-in compilation of the current saved source succeeded on 2026-10-09 with
  `kind: success` and the message: "The current source compiled successfully with
  the desktop editor's compiler." Earlier non-returning requests are historical;
  this successful response confirms the current standalone source.
- All fourteen current PDF pages were rendered and inspected as a contact sheet;
  ethics, extended-diagnostics, figure, and training/criterion pages were also
  inspected at full page size.
- The Python diagnostic figure passed static preflight, the Matplotlib panel
  alignment gate, the 5-point PDF glyph audit, and the rendered collision audit.
- `git diff --check` passes. No frozen source/scenario/result was modified;
  the paper changes remain uncommitted. No experiment checkpoint is asserted.

The cached `lineno.sty` emits a UTF-8 comment warning, and narrow columns have
underfull-box warnings. These did not produce visible glyph or layout defects;
the official ACL style was not altered to suppress them.

## Remaining Submission Gates

1. Resolve interface eligibility under a newly frozen protocol before using
   model capability or attack-avoidance results to support claims.
2. Supply fresh repaired-protocol benchmark and matched diagnostic evidence when
   the historical v13 results are no longer sufficient. The current defense
   evidence remains absent; a specification cannot be presented as completed RL
   validation.
3. Demonstrate a diagnostic-guided learning gain over strong deterministic
   controls under equal menus, information, collection budgets, and approvals.
   Otherwise remove the independent RL novelty claim.
4. Confirm split independence, authoring neutrality, executable fixture
   semantics, training support, calibration sampling assumptions, and compute.
5. Verify every citation and substantive AI-assisted claim with the human
   authors; disclose assistance in the Responsible NLP Checklist and final
   acknowledgments. No author approval is presumed.
6. Original software/task licensing, synthetic provenance, and anonymous/public
   release intent are now confirmed. Verify third-party/model licenses and encoder
   snapshots, prepare the anonymous archive, and check release contents. No completed
   publication or independent privacy review is asserted.
7. If further figures or experiments are added, recheck the eight-page main-text
   budget and update abstract/discussion/conclusion only with supported results.
8. Complete current OpenReview author profiles, conflicts, and applicable
   reviewing requirements. Do not fabricate administrative compliance.

The non-experimental text can be complete while the submission is not ready.
Missing evidence and author checks cannot be fixed by stronger prose.

## Completion Audit of the Full Goal

The objective remains completion of the manuscript to submission requirements,
not merely producing a plausible-looking PDF. Existing aggregate results are now
integrated, but the repaired protocol and defense evaluation remain future work.
Neither the source changes nor the local PDF proves full submission readiness.

| Requirement | Current evidence | Status |
| --- | --- | --- |
| Complete non-experimental sections | Abstract through conclusion, limitations, ethics, bibliography, and five appendices in `main.tex` | Written and locally checked |
| Keep RouteBench primary; defense auxiliary | Title, contribution list, implemented/proposed overview, ECPA section | Verified in source |
| No invented experiments or improvements | Existing results cite frozen artifacts; RL/ECPA results remain explicitly absent | Verified in source |
| Match implemented benchmark semantics | Freeze metadata, replay/selection source, both structural audits | Verified with disclosed defects |
| Valid planner/scorer contract | Interior-terminal mismatch; conflicting credit field; proposed repair only | Not fully achieved |
| Distinct diagnostic and defense mechanisms | Local/rule controls; paired recognition/planning; trusted ECPA dispatch boundary; post-intervention witnesses; simulator-only logging and constrained CQL | Scaffold implemented; learning and empirical validation pending |
| Reproducible runtime assumptions | Stateless planner and receipt state, registered variants, approval epochs, actual rollout logging, stop/continue contract | Specified in appendices |
| ACL review formatting | Official unchanged style, A4, two columns, embedded fonts; eight content pages; 135-word abstract | Local checks pass |
| References and cross-references resolve | 19 metadata/citation entries, unique labels, no unresolved references | Mechanical checks pass |
| PDF layout | Fourteen rendered pages inspected; no overfull boxes or overlap found | Local checks pass |
| Built-in compiler succeeds | Current saved source returned `kind: success` on 2026-10-09 | Confirmed |
| Model/data/code licensing and anonymous artifact access | Original code/tasks GPLv3; synthetic provenance and anonymous/public release approved; encoder snapshot and archive pending | Partly confirmed; third-party verification and archive preparation remain |
| Human verification and Responsible NLP attestation | Assistance disclosed; author verification not asserted complete | Requires author action |
| Novelty/effectiveness supported rather than promised | Benchmark design described; diagnostic/defense benefit still untested | Cannot establish by prose alone |
| Experiments stay outside this writing scope | No new model evaluations, trace collection, or training; existing aggregate artifacts were integrated | Preserved |

Author confirmations now establish the original license, release intent, synthetic
provenance, single-reviewer sampling account, resources, and planned success margin.
They do not establish repaired runtime code, independent author verification,
third-party permissions, a published archive, completed profiles, an independent
privacy review, or empirical validation. Compiler waits and metadata requests do
not establish those facts either. The global goal must not be marked achieved on
the basis of the local PDF or this checklist.
