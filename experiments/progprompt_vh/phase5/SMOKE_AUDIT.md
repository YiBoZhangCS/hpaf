# Phase-5 Smoke Audit

## Attempt 001

The locked 2 tasks × 3 methods pipeline completed without an API, Unity,
serialization, evaluator, repair-loop, or controller crash. All six records had
the frozen hashes and ARK/model/settings; `verified_but_stopped_count` was zero.

The Long task exposed two generic implementation gaps before formal execution:

1. The shared ProgramAgent action documentation listed the frozen API but did
   not explain the benchmark's causal augmentation rules. Flat hallucinated
   unsupported `wash('plate')`; Hierarchical's Retry-1 did the same because it
   had no documented graph-compatible route to WASHED.
2. The shared current-state renderer showed nearby objects but omitted an
   object's one-hop INSIDE/ON relation to a nearby container. After the initial
   program placed a plate in the sink, the repair state displayed the sink but
   not `plate INSIDE sink`, encouraging redundant retrieval of a different
   class-equivalent plate.

The fix is method-generic and task-independent: document the WASHED/HEATED
augmentation mechanics and append one-hop INSIDE/ON relations connected to
nearby objects to the same Flat/Hierarchical symbolic state representation.
The action set, semantic goals, decomposition, evaluator, examples, retry cap,
and all frozen hashes are unchanged. Attempt 001 remains preserved.

## Attempt 002

The complete six-pair rerun passed pipeline validation. The generic action
documentation eliminated all unsupported-action outputs, and the current-state
trace included one-hop relations. `verified_but_stopped_count` remained zero.

The executable Long programs then exposed a separate shared grounding defect:
after placing a plate in kitchen sink 247, class-only `find('faucet')` randomly
bound bathroom faucet 50. Every Flat primitive succeeded, but WASHED could not
be augmented because the ON faucet and sink contents were in different visible
rooms. This is not a planning or method-specific failure; the interpreter had
ignored its current room while resolving duplicate class instances.

The shared resolver is corrected generically for every method: retain a valid
prior binding, otherwise prefer a character-CLOSE instance, then an instance
INSIDE the current room, then use the seeded fallback. No task name, target
class, frozen artifact, prompt, or evaluator is changed. A complete attempt 003
is required before formal execution. Attempt 002 remains preserved.

An offline replay with the corrected faucet binding then identified a second
shared adapter defect before attempt 003: the pinned augmentation function
produces WASHED from the complete final graph, but the released-style adapter
passes only the agent-visible partial graph after each action. Even the exact
ground-truth wash sequence therefore never receives WASHED. Phase 5 now invokes
the same pinned augmentation rules on a full evaluator-only snapshot after each
successful action. Resulting HEATED/WASHED replacements remain separate from
native Evolving Graph state and are shared by all methods and both evaluators;
no score formula or frozen condition is changed.

## Attempt 003

The final complete smoke passed all six pairs under the locked hashes and shared
ARK settings. Both HPAF methods reached Semantic SR=1 on the Medium and Long
tasks. On the Long task their legal programs achieved WASHED with Exec=1.0;
there were no unsupported actions, serialization/runtime failures, early stops,
or verified-but-stopped events. ProgPrompt also reached the Long semantic goal,
while its official score retained demonstration-endpoint penalties.

Retry-1 was exercised end-to-end in attempt 001 (one generation, one repair,
second verification, correct early stop) and was not needed in attempt 003.
The `results/smoke/PASSED.json` marker points to attempt 003 and matches all
frozen hashes. The implementation is now frozen for the single formal run; no
prompt, executor, grounding, augmentation, goal, decomposition, or evaluator
change is permitted after this point.
