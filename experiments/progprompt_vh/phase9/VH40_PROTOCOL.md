# VH-40 Formal Protocol

## Dataset

VH-40 is the VirtualHome 40-Task Evaluation Suite, not an official 40-task
benchmark. It contains 29 official-source held-out task-scene instances retained
because they admit method-independent scoring, plus 11 synthetic causal
long-horizon extensions built on official VirtualHome scenes. The 29 instances
are a regression subset because they were previously observed during development;
the pre-frozen Long-11 is the only new holdout in Phase 9.

Long-11 was generated with seed `20260826`, deterministic natural-language and
causal templates, fixed 4/4/3 scene and 3/3/3/2 category allocations, first-valid
reference selection, and no method output. Every reference has 11-25 actions,
at least three causal stages, a majority of predecessor-dependent stages, complete
reference execution, and evaluator success. Exact instruction overlap against
train, test_seen, the existing 29, and Phase-8 synthetic 30 is zero.

## Methods

The fixed order is `ProgPrompt-Compat`, `HPAF-Flat`, `HPAF-Full`. ProgPrompt uses
the released three few-shots, whole-program generation, assertions with the frozen
ARK strict binary enum compatibility transport, and adjacent-else recovery. Flat
and Full use identical Phase-8 uncompressed process/alignment/precondition rules.
Full alone has TaskAgent decomposition, current-state atomic generation, online
atomic verification, and one local Retry-1. The Phase-9 compression gate rejected
both bounded candidates; no Long-11 task was exposed during tuning.

## Execution

Run exactly 40 x 3 x 1 = 120 unique task-method pairs, task-major then method-minor,
with ARK `doubao-seed-2-1-pro-260628`, Responses API, temperature 0, and thinking
disabled. SDK transport retries are infrastructure retries; HPAF Retry-1 is the
only planning retry. Completed records are never rerun. After formal start there
is no task removal, resampling, prompt/evaluator/config change, or failed-pair rerun.

## Evaluation

Persistent-state, frozen generic trace, and frozen generic ordered-event-plus-state
evaluators are selected by manifest metadata and shared by all methods. Online
verifiers do not determine final success. Primary metrics are Task SR, Macro Exec,
calls/task, and tokens/task. Report overall 40, official-source regression 29,
new Long-11, existing official Long-4, and combined Long-15 separately.
