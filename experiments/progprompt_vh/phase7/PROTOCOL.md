# Phase-7 Final Benchmark Protocol

## Purpose and set separation

Phase 7 restores the released ProgPrompt assertion contract, freezes one generic HPAF source-target sequencing constraint, and evaluates three methods once. The original Phase-6 20 task-scene instances are the `regression` set because their outputs informed prompt motivation. Nine additional official held-out instances, selected only from the Phase-6 preclassified trace-evaluable exclusions, are the untouched `confirmatory` set. `combined` is descriptive only and is never called untouched test.

## Frozen methods

- ProgPrompt: released three examples, whole-program generation, assertions, adjacent `else:` recovery, shared 17-action graph adapter, and restored two-token assertion cap.
- HPAF-Flat: one whole-task ProgramAgent and one whole-task online verifier; no TaskAgent or retry.
- HPAF-Full: TaskAgent, per-atomic current-state ProgramAgent, per-atomic online verifier, at most one local Retry-1, and early stop after failed repair.

Flat and Full receive the exact same `PROGRAM_AGENT_RULES`. Full differs only by decomposition, per-atomic refreshed generation, atomic verification, and Retry-1.

## Frozen scoring

Primary success is method-independent and ignores online verifier declarations. Regression tasks use their Phase-6 persistent semantic conditions. Confirmatory tasks use one of two pre-frozen generic trace templates:

- `SUCCESSFUL_EVENT(action-set, object)` requires a matching successful grounded event.
- `SUCCESSFUL_APPLIANCE_CYCLE(item, appliance, controller, output?)` requires source loading when configured, a successful controller ON transition followed by OFF, and an optional post-cycle output interaction.

The trace templates are parameterized in the confirmatory manifest; there is no task-ID branch in the evaluator. Exec is successful grounded action attempts divided by all grounded attempts. Main Exec is the macro mean across tasks; micro Exec is supplementary.

## Frozen backend and order

ARK `doubao-seed-2-1-pro-260628`, Responses API, temperature 0, thinking disabled. HPAF and ProgPrompt whole-program max output remain 600. ProgPrompt assertion max output is 2. Every prompt, raw output, parsed output, token count, role, latency, and error is recorded.

Smoke uses four regression tasks only: one Short, one Medium, one Long, and one source-target transfer. It may fix API/parser/pipeline bugs but may not tune planning behavior. Formal execution order is the complete 20 x 3 regression matrix, then the complete 9 x 3 confirmatory matrix. Runs are resumable only after crashes; no failed pair is resampled. Prompt, manifests, evaluator, action set, config, and implementation hashes are verified before execution.

## Stop rule

After one regression run and one confirmatory run per task-method pair, only offline recomputation, leakage/cost audit, provenance, tables, and case timelines are allowed. No repeats, new ablations, prompt changes, evaluator changes, or task expansion are permitted.

