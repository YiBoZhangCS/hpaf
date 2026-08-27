# Structured Hierarchical Execution for Long-Horizon Robot Tasks

```text
ORIGINAL INSTRUCTION          STRUCTURED ATOMIC IR + DAG          CURRENT ATOMIC

Heat salmon, then       ->    A1 PROCESS: heat salmon       ->    Perception
place it on table                    | depends_on                  -> (Align -> Interact)^k
                                     v                             -> Verification
                                A2 TRANSFER: place on table

                                Terminal: microwave OFF
```

**Layer 1:** What semantic stage should complete next?  
**Layer 2:** How should the robot execute that stage under fresh state?  
**Verification + refresh:** Confirm completion; never plan the next stage from stale state.

**ProgPrompt vs HPAF:** one whole program with assertion/local recovery vs explicit semantic execution boundaries with dependency-aware scheduling, per-atomic refresh/verification, and localized Retry-1.

