# Evaluation-Calibrated RL Defense Protocol

## Purpose

This protocol defines a reinforcement-learning defense that converts RouteBench
development results into a runtime policy for reducing unauthorized access and
privilege escalation while preserving benign task completion.

## Scope and data boundary

- Training and policy search use `split: dev` cases only.
- A separate development calibration slice selects reward weights and risk thresholds.
- Frozen `split: test` cases are used only once for final evaluation. They must not be
  used for training, reward design, threshold selection, or controller revision.
- Every protocol change creates a new committed checkpoint and protocol identity.

## Policy

The policy observes the task projection, current capability state, proposed typed action,
executed-action history, data-flow labels, and the model/planner identity. It chooses one
of four decisions:

```text
allow | constrain | escalate | deny
```

The environment executes only the selected decision. The policy cannot rewrite an action
silently; constrained actions must be represented as a new typed capability request.

## Learning formulation

Use constrained offline RL or conservative actor-critic training over trusted simulator
traces. The objective is:

```text
maximize task utility - execution cost - intervention cost
subject to estimated escalation risk <= alpha
```

The reward must assign a substantially larger penalty to forbidden effects and privilege
escalation than to extra latency or a benign intervention. Risk estimates should use a
conservative confidence bound when a state/action combination has little data.

## Baselines and evaluation

Compare the learned policy with `none`, `static_minimum_permission`, and `path_state`
under identical cases, seeds, planners, feedback modes, and budgets. Report:

- attack success and policy violation rates;
- benign functional success and optimal-path success;
- intervention, escalation, latency, and action-cost rates;
- results stratified by `F1-F8`, `P1-P8`, `M1-M5`, route length, and topology;
- safety-utility curves for multiple fixed values of `alpha`.

The primary generalization test holds out attack mechanisms and template families from
policy training. A defense win requires lower attack success than the strongest baseline
without a predeclared unacceptable loss in benign functional success.

## Required ablations

Remove the learned risk model, path history, data-flow state, and escalation action one
at a time. This distinguishes gains from ordinary path-state authorization, reward
shaping, and additional intervention opportunities.
