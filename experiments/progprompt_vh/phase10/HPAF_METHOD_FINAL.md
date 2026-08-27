# Final HPAF Method Definition

## 1. Complex task

An instruction is HPAF-complex if it contains multiple semantic checkpoints or if a later checkpoint depends on state produced by an earlier checkpoint. Complexity is measured primarily by semantic atomic count, dependency depth, process atomic count, cross-object transitions, and cross-location transitions. Ground-truth/reference primitive length is retained only as supplementary simulator horizon.

## 2. Atomic task

One Atomic Task is one dominant semantic commitment: around one principal focal object, with optional source, target, appliance, or related object, it completes an independently meaningful and independently verifiable semantic state transition or process.

Atomic tasks are not primitive actions. Loading an item, running an appliance cycle, and completing that cycle can belong to one `PROCESS` atomic. Required navigation and object manipulation remain within the current atomic.

## 3. Atomic types

- `TRANSFER`: move a focal object into/on a semantic target.
- `STATE_CHANGE`: establish a requested persistent state.
- `PROCESS`: complete a requested lifecycle, not merely start it.
- `MULTI_OBJECT_COUPLED`: establish one inseparable semantic condition jointly involving multiple objects.
- `INTERACTION`: complete a meaningful non-persistent interaction such as watching TV.

No other type is permitted in version 1.

`focal_object` stores exactly one scene class. For `MULTI_OBJECT_COUPLED`, it is the principal participant and the semantic goal names all jointly constrained objects; class names are never concatenated in the field. A `PROCESS` atomic owns required loading, activation, and completion. A separate successor `TRANSFER` is used only for a distinct post-process delivery checkpoint requested by the instruction.

## 4. Dependency DAG

Every atomic carries `depends_on`. Edges mean genuine semantic precedence, not list order or reference-planner preference. The validator checks references and acyclicity; the executor selects ready nodes in stable topological order. An atomic is marked complete only after online verification.

## 5. Terminal constraints

A terminal constraint is a state/relation that must hold when the whole task ends but is not an independently meaningful high-level stage. “Transfer the object and leave both containers closed” yields transfer atomic(s) plus closed-container terminal constraints, not close-container atomics.

Terminal constraints are activated in the final ready atomic’s execution/verification contract. They are inferred by TaskAgent from the instruction, never supplied from evaluator gold.

## 6. Atomic execution

For the current ready atomic:

`Perception -> (Alignment -> Interaction)^k -> Verification`

Perception obtains fresh local state. Alignment establishes the geometric/spatial precondition for the next interaction; in VirtualHome this is mainly `find`, `walk`, and `CLOSE`. Interaction changes task state (`grab`, `putin`, `putback`, `open`, `close`, `switchon`, `switchoff`, etc.). The alignment–interaction pair may repeat any number of times inside one atomic.

## 7. State refresh

After an atomic verifies, HPAF refreshes symbolic state before generating the next ready atomic program. The next stage therefore does not rely on stale pre-execution proximity, held-object, container, appliance, or relation assumptions.

## 8. Verification and Retry-1

The online verifier evaluates only the current TaskAgent-derived atomic contract from current observation and the current attempt trace. If it returns `done=false`, HPAF permits one localized repair generated from typed failures and current state, followed by one post-repair verification. A second failure stops execution. Online verification never determines the method-independent final benchmark score.

## 9. Difference from HPAF-Flat

Flat has no TaskAgent and receives no structured atomic IR. Flat and Full share the same ProgramAgent action documentation, alignment rules, process rules, and primitive semantics. Full-only behavior is structured decomposition, dependency-aware ready selection, per-atomic state refresh/verification, terminal handling derived from TaskAgent IR, and Retry-1.

## 10. Difference from ProgPrompt

ProgPrompt maps the instruction to one whole program and uses assertions with local recovery. Its comments can express logical subtasks; HPAF does not claim ProgPrompt lacks task structure. HPAF instead makes execution boundaries explicit, refreshes state between semantic atomics, checks atomic postconditions, localizes one retry, and schedules work using explicit dependencies.

## Evaluator contract

Final success requires all semantic events, all required DAG edges, all terminal constraints at task end, and all final persistent semantic goals. Legal unrelated operations may commute. Reference programs are used only for feasibility, horizon, and debugging.

`REFERENCE_PROGRAM != TASK_SEMANTICS`.
