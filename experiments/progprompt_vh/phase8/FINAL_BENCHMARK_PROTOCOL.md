# Final Benchmark Protocol

## Identity

- Name: VirtualHome Compositional Stress Benchmark.
- Classification: synthetic deterministic compositions based on official VirtualHome scene inventories; not an official ProgPrompt test set.
- Seed: `20260826`.
- Size: 30 task-scene instances: 10 each with 2, 3, and 4 semantic goals.
- Scene balance: 10 each in official VirtualHome scenes 0, 1, and 2.

## Frozen Generation Rule

The generator enumerates persistent `PUT_IN`, `PUT_ON`, `SWITCH_ON`,
`SWITCH_OFF`, `OPEN`, and `CLOSE` atomics on unique scene instances. It uses a
fixed RNG, rejects conflicting/shared object classes, requires at least one
transfer and two goal-template types, and accepts the first combinations whose
complete deterministic reference programs execute and satisfy every conjunctive
predicate. No LLM output or method result enters generation or selection.

Exact instruction overlap with ProgPrompt train, test_seen, and the 29 Phase-7
development instances is zero. Atomic goals may recur; novel composition is the
intended independent variable.

## Methods And Order

The frozen methods are `ProgPrompt-Compat`, `HPAF-Flat`, and `HPAF-Full`.
Execution order is task-major, then method order as listed. Each of the 90
task-method pairs receives exactly one run. No repeats, resampling, task removal,
prompt change, or evaluator change is allowed after this lock.

Flat and Full share process-aware ProgramAgent rules, alignment/precondition
guidance, and the frozen `uncompressed` context representation. The attempted
compression is used only if its bounded development gate passed. Full alone has
TaskAgent decomposition, current-state per-atomic generation, atomic verification,
and one local Retry-1. The online verifier never receives frozen goal predicates.

## Evaluator And Metrics

Final success is method-independent conjunction over the pre-frozen persistent
goal predicates. Goal completion ratio is the fraction satisfied. Primary results
report Task SR by 2/3/4 goals and overall. Macro Exec is primary; micro Exec,
tokens/task, calls/task, role costs, retention, and 2-to-4-goal SR drop are also
reported. Reference programs and final states validate dataset feasibility only
and never enter any method prompt.
