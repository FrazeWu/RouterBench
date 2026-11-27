# CapGraphBench Manuscript Audit

Date: 2026-11-23. This audit distinguishes manuscript formatting from empirical
and administrative submission readiness. The ACL revision makes the benchmark,
construction pipeline, evaluation contract, and historical measurements the main
paper. The latest layout also includes a main-text ECPA method section and reserves
two content pages for the ongoing defense comparison. Composition diagnostics
remain proposed; no completed defense effectiveness result is included.

The recovery inventory now has 66 source-reviewed tasks and 12/4/4/40 semantic
families for training/tuning/calibration/test. These are source-bound AI reviews,
not authenticated human review or exhaustive independence validation. On
2026-11-23, the author reported that the defense experiment is in progress.
Completed source/model-bound results have not yet been integrated; older status
documents do not establish its present execution phase. Historical benchmark
results and frozen scenarios are unchanged.

Earlier scope and design entries below record their original dates; current
manuscript and submission status are given in the ACL gates and completion audit.

## Author-Confirmed Recovery Design (2026-10-21)

This supersedes the older CQL-only/violation-superiority plan below.

- Train a concrete intervention scorer behind common immutable guards, with a frozen
  normal task agent attacked primarily through low-trust tool-return content.
- Compare long-term outcome supervision and multi-step offline RL using the same
  backbone/data/update budget. Training alone is not an innovation; report the winner
  and all negative results. RouteBench remains primary if learned value is absent.
- Explicit exact agent acceptance, actual request-bound scoped approval, public pure
  completion witnesses, final rechecks and explicit STOP are required. Hidden verifiers,
  reference paths/costs and evaluator minimum authority never inform runtime choices.
- Primary endpoint is safe completion over the entire fixed attacked normal-task set.
  Require point gain >=5 percentage points and paired 95% lower bound >0, with
  one-sided benign-success lower bound >=-2 points. More violations cannot be offset
  by utility. Family clusters contain all presentation and controller-seed repetitions.
- Hold out semantic families and attack mechanisms; use separate transfer agents and
  budgeted adaptive attackers. Diagnostics-guided acquisition is a separate hypothesis
  under equal total acquisition budgets including diagnostics, not only equal rollouts.
- Implementation and small development timing/training checks are authorized. A formal
  resource cap must follow concrete measurement/cost estimates before formal runs.
  Development results are not evidence of learned efficacy or sufficient training data.

## Historical Decisions (2026-10-08)

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
- `references.bib` holds 19 verified metadata records. Eighteen are cited and
  appear in the official ACL-formatted bibliography embedded in `main.tex`;
  the unused Sentence-BERT record remains in the database. Future citation
  changes must update both representations.
- Abstract, introduction, related work, formal problem, benchmark construction,
  evaluation contract, experiments, discussion/conclusion, limitations, ethics,
  and AI-use acknowledgements are written. ECPA has a concise main method
  section; its full design/protocol and proposed diagnostics remain in appendices.
- The experiments section now reports existing formal v13, difficulty-stratified,
  component-ablation, model-free baseline, ordering anti-leakage, and checkpoint
  stability artifacts. No run was started or altered by this writing revision.
- The benchmark, interleaved recovery runtime, real JSON-agent adapter, actual rollout
  traces, supervised candidate scorer and multi-step TD scorer are implemented.
  Counterfactual diagnostics, actual training outcomes, formal adaptive attacks,
  calibration, and learned-benefit results remain unvalidated. The 66-task source
  inventory has completed source-bound AI reviews; this does not supply model data.
- ECPA needs a separately frozen interleaved execution/replanning protocol;
  v13's pre-replay route selection is not itself the proposed RL environment.
- The runtime/transition appendix specifies stateless planner calls, accepted
  replacement requests, post-intervention completion witnesses, fixed approval
  semantics, bounded decisions, and actual intervention-dependent rollouts. The
  runtime implements the guards, pure public witness, exact acceptance, actual scoped
  grants, real replanning, explicit stop and probability-accounted collection.
  Private records retain actual permitted state/menu/history and outcomes; hashes
  are identifiers. Two development overlays are not a sufficient training corpus.
- The selectability-repair appendix defines a proposed explicit stop/continue
  interface and its validation requirements. It is not implemented by this edit.

## Implementation Alignment

The benchmark source revision recorded by the earlier implementation audit is
`d09969477826a8913905613a76199eeb0a37fee5`. At final manuscript review, the
checkout HEAD is `230a11174cef12b6046fc07a3193866d2bb022e2` and the paper
worktree is modified; neither identifies a new clean formal-evaluation
checkpoint. Existing user changes to `main.tex`, `references.bib`, and this
audit were preserved. No new formal experiment was started.

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
| Supervised outcomes / offline multi-step TD | Existing learning methods, not a new RL algorithm |

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

The paper makes no learned-defense efficacy claim. Small real-agent recovery and
scorer fitting checks are development feasibility evidence, not formal improvement
experiments. Result tables and machine-readable CSV inputs are present under
`paper/figures/`; the model CSV now contains all eleven full-v13 model rows,
and `formal_diagnostics.pdf` visualizes the model, route-length, and component
ablation results. The plotting source uses Python/matplotlib; vector, raster,
alignment, text-size, and collision checks pass.

## Experiments Revision (2026-11-20)

The experiment narrative now follows three questions: model route selection,
route properties associated with errors, and interface/presentation validity.
This is a writing revision; no model evaluation, frozen scenario, or historical
result was changed.

- The main table retains the archived paired Qwen3 results: 58.43% / 61.98%
  optimal/capable for 8B and 78.94% / 84.54% for 14B. These match
  `formal-v13-multifamily-paired-bootstrap-20261005.md` and its archived
  per-attempt sources.
- `formal-v13-current-analysis.md` describes a different pair of recovery
  summaries (58.56% / 61.34% and 78.92% / 83.89%). That report explicitly
  lacks the corresponding case-level records. Its aggregates must not be
  combined with the archived paired intervals. The separate October 8
  Qwen3-14B recovery report cited above yields 78.94% / 84.02% and remains a
  repeatability check, not another model row.
- The safe-certificate length table has 775 cases because the source report
  omits the single five-action case from its displayed rate groups. The
  manuscript now states the omission in the table and figure captions.
  Full-benchmark denominators remain 776 cases and 3,880 attempts.
- The flattened ablation changes all four public preference attributes and
  removes private edge costs. It is not an isolated authority-scope
  manipulation; exact credit is recomputed on each graph and can change.
  The narrative therefore emphasizes the observed forbidden outcomes and
  reports the paired compliance/capable intervals with subset limitations.
- The first-edge and ordering checks remain presentation diagnostics.
  Reachability counts (45 cases with no selectable safe completion/optimum,
  279 with no selectable forbidden route) remain explicit limits on model
  interpretation. No formal ECPA efficacy result is claimed.

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

A fresh-context independent verification on 2026-11-23 confirmed all 19 database
records against primary records and checked the related-work claims. The 18
active citations exactly match an official `acl_natbib.bst` regeneration of
the embedded bibliography. Sentence-BERT is not cited in the present paper.
ToolPrivBench's published record is
https://aclanthology.org/2026.findings-emnlp.2059/; CaMeL's verified refereed
record is SaTML 2026, pages 587--618, DOI `10.1109/SaTML68715.2026.00040`.
The table below retains the retrieval depth of the earlier targeted search.

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
refereed versions are not invented. The development encoder now uses a pinned
E5-small-v2 snapshot; no MiniLM inference claim remains. Model licensing and
anonymous redistribution must still be checked for the final release contents.

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

Checks completed for the 2026-11-23 defense-space revision:

- Section 8, Discussion and Conclusion, ends on PDF page 6. The complete PDF
  has 16 pages. All main floats are on pages 3 and 5, before the conclusion;
  counting only the conclusion page without the floats would be insufficient.
- Limitations starts after the conclusion on page 6. It and the subsequent
  ethics, AI-only acknowledgements, references, and appendices are excluded
  from the ACL content limit. No manual page break forces a new page.
- The current content uses six of the eight allowed pages, leaving two content
  pages for the ongoing defense experiment. There are no inserted blank pages.
  `defense-integration-plan.md` records the final allocation and result material.
- The ECPA method is now Section 6 of the main paper. Its threat model, guarded
  interventions, learner, information boundary, and matched-study design remain
  visible while the full protocol stays in Appendices D--F. The author reports
  ongoing experiments; no completed efficacy result is incorporated.
- The 147-word abstract is unchanged. The benchmark problem, construction/QC,
  public ordering, historical metrics, overall model table, key ablation, and
  interface-validity limitations remain in the main text. Four supporting tables
  move to the appendices without changing any values or captions.
- Anonymous AI disclosure covers writing/design assistance and AI-authored/reviewed
  recovery sources. The Responsible NLP form still needs the matching disclosure.
- The official ACL style, fonts, margins, and spacing are unchanged. Successful
  local and built-in compilation and rendering checks are recorded below.
- Historical denominators, 45 unavailable safe/optimal cases, 279 cases without a
  selectable forbidden route, and the conflicting Pareto-credit wording remain
  explicit. This writing revision neither repairs the protocol nor changes results.
- Starting sources/PDF are preserved in
  `/tmp/capgraphbench-reserve-20261123/before/`; previous audit backups remain
  in `/tmp/capgraphbench-acl-fix-20261123/`. Existing user edits are preserved.

### Revision blueprint and evidence boundary

| Main section | Purpose | Evidence | Boundary |
| --- | --- | --- | --- |
| 1 Introduction | Route-level evaluation gap and observed findings | Existing manuscript and archived aggregates listed above; author reports ongoing defense study | No new efficacy or priority claim |
| 2 Related Work | Benchmark and security positioning | Existing bibliography plus independent retrieval in this revision | No performance numbers attributed to prior work |
| 3 Problem | Replay eligibility, ordinal objective, public/private inputs | Existing formal definitions and historical contract audit | Graph-relative ordering; no calibrated-risk guarantee |
| 4 Construction | Manual authoring, materialization, QC and coverage | Frozen inventory, author account and replay audit | Tags are not independent workflow diversity |
| 5 Protocol | Reproduce historical v13 and its limitations | Archived protocol and manifests | No repaired-interface result |
| 6 ECPA | Compact companion method and matched-study design | Existing source/protocol materials; author reports experiment in progress | No completed efficacy result incorporated |
| 7 Experiments | Model comparison, structural ablation, validity controls | Existing frozen reports and tables | Historical interface; descriptive uncertainty; two pages reserved for defense |
| 8 Discussion/Conclusion | Interpret the measured benchmark and future questions | The same results and explicitly proposed appendices | No learned-defense benefit established |

The original manuscript/data and checked-in source-status reports are L1 evidence
for the above edits. They support the reported designs, counts, and historical
outcomes; they do not support deployment safety, general language competence,
a fresh protocol, or a completed recovery experiment. Official ARR/ACLPUB pages
support formatting and process requirements, not acceptance or author compliance.

### Final verification record: defense-space revision (2026-11-23)

- Final saved source compiled successfully with Tectonic and the desktop editor;
  the latter returned `kind: success`. The PDF has 16 A4 pages, with all main
  floats before the page-6 conclusion and no content beyond the six-page budget.
- All fonts are embedded; there are no Type 3 fonts or font-type mismatch warnings.
  References/citations resolve, labels are unique, and there are no overfull boxes,
  missing characters, or compiler errors. Existing `lineno.sty` UTF-8 comment and
  underfull-box notices remain. Rendered pages show no clipping or overlap.
- The embedded official ACL style is byte-identical to `acl.sty`. All 18 cited
  records still match the 18 embedded entries; the 19-record bibliography is
  byte-identical to the starting backup. Prior independent verification applies
  to the retained citation claims; this layout revision adds no references.
- All eight original main tables are byte-identical, including captions: four
  remain in the main text and four move to the supporting appendices. All twelve
  table blocks in the document are preserved. No CSV, benchmark source, scenario,
  historical result, or experiment process was changed by this writing revision.
- The diagnostic chart and ECPA diagram retain the earlier checked typography.
  The current PDF was rendered for visual review, including the new main-method
  and result-table placement. Final mechanical records and renders are under
  `/tmp/capgraphbench-reserve-20261123/`.
- PDF copies: `paper/main.pdf`, `output/pdf/CapGraphBench-ACL-review.pdf`, and
  `output/pdf/CapGraphBench-ACL-defense-space.pdf`. Generated outputs stay ignored.
- Final `main.tex` SHA-256: `920e8ea9ee799e37a2de5f1fbe98eb17936b1cf32975d585e369173454a7c24a`.
  Existing user changes remain uncommitted. Compilation/layout success does not
  establish experiment success, protocol repair, or full submission readiness.

## Remaining Submission Gates

1. Resolve interface eligibility under a newly frozen protocol before using
   model capability or attack-avoidance results to support claims.
2. Supply fresh repaired-protocol benchmark and matched diagnostic evidence when
   the historical v13 results are no longer sufficient. The current defense
   evidence remains absent; a specification cannot be presented as completed RL
   validation.
3. Integrate the ongoing defense study only from completed, source/model-bound
   results, retaining matched-information controls and the fixed success criteria.
   Composition diagnostics and acquisition comparisons remain separate proposed
   work. No effectiveness claim is supplied by the current method description.
4. Confirm benchmark split independence, authoring neutrality, and executable
   fixture semantics. Before any future recovery experiment, also confirm
   training support, calibration sampling assumptions, and compute.
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

## Current Completion Audit (2026-11-23)

The objective remains completion of the manuscript to submission requirements.
Existing benchmark aggregates are integrated; the defense experiment is ongoing,
and its completed results have not yet been incorporated. The historical interface
defects remain disclosed. The local PDF does not prove full submission readiness.

| Requirement | Current evidence | Status |
| --- | --- | --- |
| Complete non-experimental sections | Abstract through conclusion, limitations, ethics, bibliography, and seven appendices in `main.tex` | Written and locally checked |
| Keep CapGraphBench primary; include companion defense | Benchmark title/contributions; ECPA main method; proposed diagnostics in appendix | Verified in source |
| No invented experiments or improvements | Existing results cite frozen artifacts; RL/ECPA results remain explicitly absent | Verified in source |
| Match implemented benchmark semantics | Freeze metadata, replay/selection source, both structural audits | Verified with disclosed defects |
| Valid planner/scorer contract | Interior-terminal mismatch; conflicting credit field; proposed repair only | Not fully achieved |
| Distinct diagnostic and defense mechanisms | ECPA main method; full contracts and diagnostic design in appendices | Defense experiment ongoing per author; completed efficacy results not incorporated |
| Reproducible runtime assumptions | Stateless planner and receipt state, registered variants, approval epochs, actual rollout logging, stop/continue contract | Specified in appendices |
| ACL review formatting | Unchanged official style; six content pages; 147-word abstract; AI-only disclosure | Two content pages reserved for defense results |
| References and cross-references resolve | 19 verified database records; 18 cited and rendered entries; unique labels and resolved references | Mechanical and independent citation checks pass |
| PDF layout | Sixteen-page PDF with all main tables on pages 3/5 and conclusion on page 6 | Current verification recorded in the defense-space revision |
| Built-in compiler | Final defense-space source returned `kind: success`; local Tectonic build also passed | Verified after the final source edit |
| Model/data/code licensing and anonymous artifact access | Original code/tasks GPLv3; synthetic provenance and anonymous/public release approved; encoder snapshot and archive pending | Partly confirmed; third-party verification and archive preparation remain |
| Human verification and Responsible NLP attestation | Assistance disclosed; author verification not asserted complete | Requires author action |
| Novelty/effectiveness supported rather than promised | Benchmark design described; diagnostic/defense benefit still untested | Cannot establish by prose alone |
| Experiment evidence boundary | Earlier development checks retained; author reports ongoing defense experiment | No process modified and no new experiment launched in this writing revision |

Author confirmations now establish the original license, release intent, synthetic
provenance, single-reviewer sampling account, resources, and planned success margin.
They do not establish repaired runtime code, independent author verification,
third-party permissions, a published archive, completed profiles, authenticated human source review,
or empirical validation. Compiler waits and metadata requests do
not establish those facts either. The global goal must not be marked achieved on
the basis of the local PDF or this checklist.

## Historical Defense Source Alignment (2026-10-22)

The inventory counts in this dated entry describe the October 22 stage. The
66-task completion update at the top supersedes those counts.

The active compact-defense plan supersedes historical tool-return and CQL-only
entries: the attacker controls an external model-response relay; the primary
learner is Qwen3-1.7B LoRA with outcome-derived candidate-choice supervision and
frozen Qwen3-14B as task agent. A completed timing pilot does not freeze or
validate the formal recipe. Its tie with the path rule remains reported.

The manuscript now distinguishes text-operator holdout from structured proposal
forgery. Three registered text transformations have executable source behavior;
structured mode collapses them to the same proposal and cannot support a new
mechanism claim. Spoofed roles/facts remain untrusted data. Train/tune/calibration
and initial test sources total 23 tasks/22 candidate labels, all independently
unaccepted. One overlapping publication-pointer candidate was removed during
source checks before model outcomes. Forty primary-test families remain a target,
not an achieved count. Source and tokenizer audits are not formal efficacy data.

No historical result table, threshold, citation or bibliography entry changes.
The family-cluster and noninferiority evidence requirements remain unchanged;
inadequate precision must be reported as inconclusive. See the current
independent-defense-study-plan.md and defense-relay-mechanisms.md for provenance.
