# PPT Method Example — Development Illustration Only

This fixed example is a **method illustration** previously seen in development. It is excluded from the Phase-10 final holdout.

## Task

> Heat the salmon in the microwave, complete the cycle, then place the salmon on the coffeetable.

## Layer 1 — semantic decomposition

```text
Instruction
    |
    v
+------------------------+
| TaskAgent              |
+------------------------+
    |
    v
A1 PROCESS
Heat salmon
    |
    | depends_on
    v
A2 TRANSFER
Place salmon on coffeetable

Terminal: Microwave OFF
```

```text
A1
type             = PROCESS
focal_object     = salmon
target           = microwave
completion_mode  = process
semantic_goal    = Complete the microwave heating process for the salmon.
depends_on       = []

A2
type             = TRANSFER
focal_object     = salmon
source           = microwave
target           = coffeetable
completion_mode  = state
semantic_goal    = Place the processed salmon on the coffeetable.
depends_on       = [A1]

Terminal constraint: microwave = OFF
```

It is not decomposed into load/on/off/retrieve/place atomics: those are primitive-level steps serving two semantic commitments.

## Layer 2 — execute A1

```text
Perceive salmon + microwave + held/appliance state
  -> Align salmon -> Grab
  -> Align microwave -> Open / Put in / Close
  -> Switch on / Switch off
  -> Verify heating process completed
```

After verification, refresh state. Then execute A2:

```text
Perceive current salmon/microwave/table state
  -> Align microwave -> Retrieve salmon
  -> Align coffeetable -> Put back salmon
  -> Verify salmon ON coffeetable
  -> Check terminal: microwave OFF
```

Each atomic follows `P -> (A -> I)^k -> V`.

## Why two layers

- Layer 1: “What semantic stage should be completed next?”
- Layer 2: “How should the robot execute the current semantic stage under the current state?”
- Verification: “Did the current semantic stage actually complete?”
- State refresh: “Do not plan the next stage using stale execution state.”

## Conceptual comparison

```text
ProgPrompt: Instruction -> one whole program -> assertion / local recovery

HPAF: Instruction -> semantic atomic IR + dependency
                  -> current atomic program -> execute -> verify
                  -> state refresh -> next ready atomic
```

ProgPrompt comments can express logical subtasks. HPAF’s distinction is explicit execution boundaries, per-atomic state refresh, postcondition verification, localized Retry-1, and dependency-aware execution.

## Very concise slide copy

```text
Task: Heat salmon in the microwave, then place it on the coffeetable.

Layer 1:
A1 Heat salmon [PROCESS]
        ↓
A2 Place salmon on table [TRANSFER]

Terminal: Microwave OFF

Layer 2 for A1:
Perceive -> Align salmon -> Grab -> Align microwave
         -> Load / Run cycle -> Verify

Then state refresh and A2.
```

