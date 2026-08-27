# Phase-10 Failure Audit

Each failed task-method record receives one primary offline category from TaskAgent diagnostics, typed execution errors, missing semantic-DAG elements, terminal constraints, and final goals. No category assignment changed a score.

## Counts

| Category | Count |
|---|---:|
| TaskAgent semantic decomposition error | 0 |
| TaskAgent validator rejection | 0 |
| dependency violation | 0 |
| terminal constraint miss | 5 |
| process lifecycle incomplete | 5 |
| alignment failure | 2 |
| interaction/precondition failure | 5 |
| object grounding | 0 |
| verification false decision | 0 |
| repair failure | 0 |
| goal omission | 3 |

## Failed records

| Task | Method | Category | Exec | Primary diagnostic |
|---|---|---|---:|---|
| `p10_s0_container_1` | ProgPrompt-Compat | terminal constraint miss | 1.000 | missing semantic/final condition |
| `p10_s0_process_1` | ProgPrompt-Compat | terminal constraint miss | 0.810 | <washingmachine> (72) not lookable when executing "[WATCH] <washingmachine> (72) [0]" |
| `p10_s0_coupled_1` | ProgPrompt-Compat | interaction/precondition failure | 0.500 | <character> (1) does not have a free hand when executing "[OPEN] <fridge> (305) [0]" |
| `p10_s0_coupled_1` | HPAF-Flat | interaction/precondition failure | 0.583 | verifier failure fields violate schema |
| `p10_s0_crossloc_1` | ProgPrompt-Compat | interaction/precondition failure | 0.789 | <toothpaste> (62) is inside other closed thing when executing "[GRAB] <toothpaste> (62) [0]" |
| `p10_s1_container_2` | ProgPrompt-Compat | goal omission | 1.000 | missing semantic/final condition |
| `p10_s1_process_2` | ProgPrompt-Compat | process lifecycle incomplete | 0.938 | <dishwasher> (228) not lookable when executing "[WATCH] <dishwasher> (228) [0]" |
| `p10_s1_process_2` | HPAF-Flat | terminal constraint miss | 0.750 | verifier failure fields violate schema |
| `p10_s1_process_2` | HPAF-Full | process lifecycle incomplete | 0.917 | Atomic A1 remained done=false after Retry-1 |
| `p10_s1_coupled_2` | ProgPrompt-Compat | goal omission | 1.000 | missing semantic/final condition |
| `p10_s1_crossloc_2` | ProgPrompt-Compat | terminal constraint miss | 1.000 | missing semantic/final condition |
| `p10_s1_crossloc_2` | HPAF-Flat | alignment failure | 0.688 | verifier failure fields violate schema |
| `p10_s2_container_3` | ProgPrompt-Compat | terminal constraint miss | 1.000 | missing semantic/final condition |
| `p10_s2_process_3` | ProgPrompt-Compat | process lifecycle incomplete | 0.938 | <microwave> (171) not lookable when executing "[WATCH] <microwave> (171) [0]" |
| `p10_s2_process_3` | HPAF-Flat | process lifecycle incomplete | 0.923 | <microwave> (171) is not on when executing "[SWITCHOFF] <microwave> (171) [0]" |
| `p10_s2_process_3` | HPAF-Full | process lifecycle incomplete | 1.000 | missing semantic/final condition |
| `p10_s2_coupled_3` | ProgPrompt-Compat | interaction/precondition failure | 0.556 | <character> (1) does not have a free hand when executing "[OPEN] <closet> (395) [0]" |
| `p10_s2_coupled_3` | HPAF-Flat | interaction/precondition failure | 0.583 | verifier failure fields violate schema |
| `p10_s2_crossloc_3` | ProgPrompt-Compat | goal omission | 1.000 | missing semantic/final condition |
| `p10_s2_crossloc_3` | HPAF-Flat | alignment failure | 0.688 | verifier failure fields violate schema |
