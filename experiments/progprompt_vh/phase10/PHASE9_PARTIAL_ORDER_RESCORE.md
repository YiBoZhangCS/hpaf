# Phase-9 Partial-Order Offline Rescore

No API/LLM call was made and no action was regenerated. The frozen Phase-9 traces are reinterpreted with semantic events, required dependency edges, terminal constraints, and final persistent goals. Reference program order is not task semantics.

## VH-40

| Method | Old VH40 SR | New offline SR |
|---|---:|---:|
| ProgPrompt-Compat | 18/40 (45.0%) | 18/40 (45.0%) |
| HPAF-Flat | 27/40 (67.5%) | 27/40 (67.5%) |
| HPAF-Full | 28/40 (70.0%) | 32/40 (80.0%) |

## Long-11

| Method | Old Success | New Offline Success |
|---|---:|---:|
| ProgPrompt-Compat | 0/11 | 0/11 |
| HPAF-Flat | 7/11 | 7/11 |
| HPAF-Full | 3/11 | 7/11 |

## Changed decisions

| Task | Method | Exec | Final conditions | Old | New | Reason |
|---|---|---:|---|---:|---:|---|
| `vh40_long_s0_03` | HPAF-Full | 1.000 | yes | 0 | 1 | All required semantic events and DAG edges occurred; terminal close occurred after delivery, which is legal. |
| `vh40_long_s0_04` | HPAF-Full | 1.000 | yes | 0 | 1 | All required semantic events and DAG edges occurred; terminal close occurred after delivery, which is legal. |
| `vh40_long_s1_07` | HPAF-Full | 0.857 | yes | 0 | 1 | All required semantic events and DAG edges occurred; terminal close occurred after delivery, which is legal. |
| `vh40_long_s1_08` | HPAF-Full | 1.000 | yes | 0 | 1 | All required semantic events and DAG edges occurred; terminal close occurred after delivery, which is legal. |

## Implementation rejections remain failures

The 4 TaskAgent parse/validation rejection records executed zero actions. They remain `FAIL` under offline rescoring and are labeled `implementation_rejection`; fixing the validator cannot counterfactually supply an execution trace.

## Interpretation

The score changes are evaluator corrections only. They do not claim that a new Phase-10 TaskAgent would have repaired any Phase-9 run. Unrelated legal operations may commute; required predecessor relationships still cannot be violated, and terminal/final conditions must still hold at task end.
