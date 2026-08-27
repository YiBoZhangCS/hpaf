# Phase-5 Controlled Experiment Protocol

## Research comparison

The primary ablation is `HPAF-Flat` versus `HPAF-Hierarchical`: the same
ProgramAgent instruction style, symbolic state, object inventory, primitive
action set, executor, model, and evaluators, with explicit frozen semantic
decomposition as the intended difference. `ProgPrompt-GraphCompatible` is the
literature baseline under the same graph-executable primitive API.

## Frozen protocol

| Item | Value |
|---|---|
| Provider / model | ARK / `doubao-seed-2-1-pro-260628` |
| API | Responses API (`responses.create`) |
| Sampling | temperature `0.0`; thinking disabled; max output tokens `600`; no seed |
| Scene | VirtualHome scene `0` |
| Executor | Unity reset/inventory sanity + pinned Evolving Graph per-action execution |
| Official evaluator | Unmodified Phase-4/released ProgPrompt set-difference formulas: SR, GCR/PSR, Exec |
| Semantic evaluator | Class-collapsed deterministic evaluation of the pre-frozen task conditions |
| Formal methods | `ProgPrompt-GraphCompatible`, `HPAF-Flat`, `HPAF-Hierarchical` |
| Formal repetitions | Exactly one run for each of 10 tasks × 3 methods |
| Hierarchical repair | At most one local ProgramAgent repair after failed primary-goal verification |

### Artifact hashes

| Frozen artifact | Frozen time (UTC) | SHA-256 |
|---|---|---|
| `data/graph_supported_actions.json` | before semantic/decomposition generation | `e9d00393e42c1da2b945e3f300f84ba6bfb174c833925e706d802f1423f7c93c` |
| `data/semantic_goals_test_unseen.json` | `2026-08-25T15:35:03.836213+00:00` | `67adf22f4df9f1432a824c5e04b0d88a4515d5a38866bafc7e5a8e1fe7734cdd` |
| `data/frozen_decompositions.json` | `2026-08-25T15:49:26.896442+00:00` | `d29a0d3dcea6b7f01edd444138058399316c8e26ddfae49dcff3d6b2a9adcc4e` |

The semantic-goal freeze occurred before any Phase-5 method execution. The
formal runner checks all hashes in `data/protocol_lock.json` before connecting
to Unity or calling an LLM. A mismatch is a hard stop.

The first whole-set TaskAgent attempt made 10 calls but was rejected before a
freeze because two outputs violated the generic condition-field schema. Its raw
calls and validation errors remain in `results/decomposition_freeze_attempt1_*`.
After the generic schema wording was clarified (no task-specific examples), the
entire 10-task set was regenerated, validated, and frozen. No individual task
was edited or selectively resampled.

## Shared action space

`GRAPH_SUPPORTED_ACTIONS` has 17 actions:

`close, drink, find, grab, lookat, open, pointat, putback, putin, run, sit,
standup, switchoff, switchon, turnto, walk, watch`

This is the source-audited intersection of the official ProgPrompt import, the
pinned Evolving Graph `Action` enum, and `ScriptExecutor` dispatch. Graph-only
actions such as EAT/WASH are withheld from HPAF for baseline fairness. See
`ACTION_SPACE_AUDIT.md`.

## HPAF execution contract

Flat receives the full task once and emits one whole-task program; it never
loads or calls TaskAgent. Hierarchical loads the frozen atomic tasks and, for
each atomic, generates against the current graph, executes, then verifies only
the frozen primary semantic goal. `verified=True` continues irrespective of
primitive failures. `verified=False` permits exactly one current-atomic repair
using current state, prior program, trace, failed actions, and typed errors.
Failure after repair stops that full task.

Exec remains a diagnostic action-success ratio and is never a continuation
gate. `verified_but_stopped_count` must be zero before formal summaries are
accepted.

## Execution order and integrity

1. Phase 5.0 offline Phase-4 failure audit (no API).
2. Phase 5.1 source action-space audit (no planning API).
3. Phase 5.2 semantic goals and one TaskAgent decomposition set frozen.
4. Phase 5.3 one Medium (`brush teeth`) and one Long (`wash the plate`) task ×
   three methods smoke.
5. Phase 5.4 exactly one ordered 10-task × three-method formal run.
6. Summaries, Markdown results, and six PNG+PDF plots, then stop.

Smoke attempt 001 completed all six pairs and exposed two generic pipeline
documentation/state-representation defects: ProgramAgent had not been told the
causal augmentation rules for WASHED/HEATED, and the post-action state omitted
one-hop INSIDE/ON relations attached to a nearby container. No frozen artifact
or task-specific content was changed. The generic ontology documentation and
shared Flat/Hierarchical state renderer were corrected, after which the full
six-pair smoke is rerun as a new attempt. Attempt 001 remains immutable under
`results/smoke/attempt_001`.

Smoke attempt 002 confirmed those fixes, then exposed a shared class-instance
resolver that could choose a duplicate object in a different room (for example,
a bathroom faucet while the character and sink were in the kitchen). The shared
interpreter was corrected to prefer the existing binding, then CLOSE instances,
then current-room instances, with the original seeded choice only as fallback.
This is method- and task-independent; prompts, evaluator, and frozen artifacts
remain unchanged. Attempt 002 is preserved and the complete smoke is rerun as
attempt 003 before formal execution.

Before attempt 003, offline replay also showed that the released partial-visible
augmentation path never emitted WASHED, including for the benchmark annotation,
although the pinned augmentation function emitted it from the identical full
graph. Phase 5 therefore refreshes the same HEATED/WASHED rules on a full,
evaluator-only snapshot after each successful primitive. These extra states are
never inserted into native Evolving Graph execution state; all methods share
the repair and the official/semantic formulas are unchanged.

Phase-4 raw runs are immutable and byte-hash locked as
`a4443744f87430b28b89360c9444a3d52d86f1f837745b76102f80d57cf72c59`.
Pinned repositories are ProgPrompt
`56e65510747dff809c1b0bac9318508da9d9a2d4` and VirtualHome
`f84ee28a75b23318ee1bf652862b1c993269cd06`.
