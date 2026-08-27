# Task Provenance

## Dataset Identity

The **VirtualHome Compositional Stress Benchmark** is a synthetic composition
benchmark based on official VirtualHome scene inventories. It is not an official
ProgPrompt test set. The 29 official Phase-7 instances are development/regression
only and do not contribute to the final main result.

- Fixed seed: `20260826`.
- Final tasks: 30 task-scene instances / 30 unique task texts.
- Goal strata: 10 x 2-goal, 10 x 3-goal, 10 x 4-goal.
- Scenes: 10 each from official VirtualHome scenes 0, 1, and 2.
- Synthetic: YES, 30/30.
- Exact full-instruction overlap with train/test_seen/development: 0.
- Deterministic reference feasibility: 30/30.

Train and test_seen instructions are excluded from leakage claims because released
ProgPrompt training tasks can enter the in-context library and test_seen is not a
task-unseen source. The final generator instead composes persistent, shared-action
goals after method freeze. It accepts combinations by fixed-seed order only after
method-independent graph execution proves every reference action executable and
every frozen predicate satisfied. Reference data is never supplied to a method.

Interview statement: "We evaluate once on 30 pre-frozen synthetic compositional
tasks built deterministically from three official VirtualHome scenes (10 each at
2, 3, and 4 semantic goals), with zero exact instruction overlap and 30/30
reference-feasibility validation."
