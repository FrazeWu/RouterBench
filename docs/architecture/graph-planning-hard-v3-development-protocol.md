# Graph-Planning Hard v3 Development Protocol

## Status

This is a development-only authoring and calibration protocol. The formal v2 benchmark
and its 776 scenarios remain frozen at their recorded Git checkpoint. A v3 profile may
reject a new development graph, but it never reinterprets a formal result.

## Purpose

The v2 contract established that a graph can contain a unique least-authority route,
functional overprivileged routes, dependency failures, and forbidden-effect routes. The
v3 profile records the source of difficulty so new cases can be balanced instead of
being selected only by route length or terminal-path count.

Every case remains manually authored. Models do not generate prompts, graphs, fixtures,
certificates, or verifier assertions. The evaluator keeps reference routes and private
cost labels out of the task prompt.

## Profile Dimensions

`routebench scenario graph-v3-audit` deterministically measures:

- bounded terminal-path count and maximum/mean branch degree;
- the number of optimal decision points and decoys sharing committed prefixes;
- the additional authority atoms exercised by functional alternatives;
- state/dependency trap paths that fail trusted execution;
- the nearest attack-route distance after the first divergence from the optimum;
- same-tool and same-authority alternatives at optimal decision points;
- a per-decision profile that supports error localization in model selections.

The complete thresholds are versioned in
`configs/benchmark/v3-development-graph-profile.yaml`. The minimum route distance is
defined on directed edge sequences after their longest common prefix; it is a structural
difficulty signal, not a private security cost.

## Authoring Rules For The Next Split

1. Keep a few easy anchor cases so calibration can detect a floor or a ceiling.
2. Add new F3 modification and F5 identity/privilege cases with malicious or
   overprivileged routes that differ from the safe route by one decision.
3. Add F8 external-action cases where dispatch, preview, and evidence-binding choices
   create dependent alternatives rather than a single obvious stop edge.
4. Include at least one same-tool and one same-authority decoy at separate optimal
   decisions, plus a state/dependency trap that is functionally plausible but fails only
   when replayed from a clean fixture.
5. Keep defense evaluation separate: run no-authorization capability first, then use
   paired static and path-state authorization controllers on the same authored graph.
6. Report both case-level capability and per-decision errors. Do not collapse a wrong
   branch, a premature stop, and an extra action into one failure label.

## Evaluation Boundary

The profile is an authoring gate, not a model score. Formal evaluation starts only from a
clean committed revision with a fresh run manifest. Any change to a scenario or threshold
creates a new checkpoint and protocol identity.
