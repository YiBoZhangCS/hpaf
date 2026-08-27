# Structured Semantic Atomic Task IR

## Two-layer method

Layer 1 maps a natural-language instruction to a structured semantic task DAG. Layer 2 executes one ready atomic from fresh local state as:

`Perception -> (Alignment -> Interaction)^k -> Verification`

An atomic is one dominant semantic commitment: an independently meaningful and verifiable state transition or completed process around a focal object. Primitive count does not define atomicity.

## Schema

```json
{
  "atomic_tasks": [
    {
      "id": "A1",
      "type": "TRANSFER",
      "focal_object": "apple",
      "source": "table",
      "target": "fridge",
      "completion_mode": "state",
      "semantic_goal": "Store the apple inside the fridge.",
      "depends_on": []
    }
  ],
  "terminal_constraints": [
    {
      "predicate": "STATE",
      "object": "fridge",
      "value": "CLOSED",
      "semantic_goal": "Leave the fridge closed at task end."
    }
  ]
}
```

Allowed atomic types are exactly `TRANSFER`, `STATE_CHANGE`, `PROCESS`, `MULTI_OBJECT_COUPLED`, and `INTERACTION`. `depends_on` references atomic IDs and must form a DAG. Terminal constraints are final required states or relations, not separate high-level tasks.

`focal_object` is always one exact scene-inventory class. For a `MULTI_OBJECT_COUPLED` atomic it identifies the principal participant; every jointly required participant is named in `semantic_goal`. Multiple class names must never be concatenated into this singular field. A requested appliance process owns its loading/activation/completion lifecycle; loading is not a separate `TRANSFER` unless the instruction also asks for a distinct semantic checkpoint.

## Validator

The semantic validator checks JSON/object shape, the allowed type set, focal/source/target scene-inventory grounding, non-empty semantic goals, type/completion compatibility, valid dependency references, and acyclicity. Navigation-only output is rejected structurally: `NAVIGATION` is not an allowed type and each allowed type requires a state/process commitment.

No lexical prefix decides semantic validity. In particular, “Move the apple from the table to the sofa” is a valid `TRANSFER`.

## Complexity

A task is complex when it contains multiple semantic checkpoints or a later checkpoint depends on predecessor-produced state. Primary HPAF measures are semantic atomic count (`N_A`), dependency depth (`D`), process atomic count (`N_P`), cross-object transitions, and cross-location transitions. Reference primitive length is a supplementary simulator horizon.

## Evaluator separation

The final evaluator independently reads frozen gold semantic events, required dependency edges, terminal constraints, and final persistent goals. Gold semantics, reference programs, and final-state predicates never enter TaskAgent, ProgramAgent, Verifier, or Repair Agent prompts.

`REFERENCE_PROGRAM != TASK_SEMANTICS`: the reference validates feasibility and records a horizon; it is not the only correct total order.
