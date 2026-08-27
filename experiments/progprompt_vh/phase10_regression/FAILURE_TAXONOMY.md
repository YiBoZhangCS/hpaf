# Phase-10R Failure Taxonomy

Every failed task-method record receives exactly one offline primary category. Classification does not alter any score.

| Category | Count |
|---|---:|
| semantic decomposition error | 0 |
| validator rejection | 0 |
| dependency violation | 7 |
| terminal constraint miss | 5 |
| goal omission | 7 |
| object grounding | 0 |
| alignment error | 1 |
| action precondition failure | 0 |
| process lifecycle incomplete | 20 |
| verifier false decision | 0 |
| repair failure | 0 |
| other | 0 |

## Flat fail / Full success

Count: 8

- `test_unseen_ambiguous_goals::collect_4_fruits_such_as_apple,_banana,_etc_in_the_dishbowl`
- `env1::microwave_chicken`
- `env2::turn_on_tv`
- `env2::put_the_soap_in_the_bathroomcabinet`
- `env2::put_milk_in_the_fridge`
- `test_unseen::watch_tv`
- `env1::watch_tv`
- `vh40_long_s1_07`

## Flat success / Full fail

Count: 2

- `vh40_long_s1_06`
- `vh40_long_s2_10`

## Failed records

| Task | Method | Category | Exec | Diagnostic |
|---|---|---|---:|---|
| `test_unseen::wash_the_plate` | ProgPrompt-Compat | process lifecycle incomplete | 0.864 | <plate> (314) is inside other closed thing when executing "[GRAB] <plate> (314) [0]" |
| `test_unseen::wash_the_plate` | HPAF-Flat | process lifecycle incomplete | 0.750 | verifier failure fields violate schema |
| `test_unseen::wash_the_plate` | HPAF-Full | process lifecycle incomplete | 0.818 | Atomic A1 remained done=false after Retry-1 |
| `test_unseen_ambiguous_goals::collect_4_fruits_such_as_apple,_banana,_etc_in_the_dishbowl` | ProgPrompt-Compat | goal omission | 1.000 | missing evaluator condition |
| `test_unseen_ambiguous_goals::collect_4_fruits_such_as_apple,_banana,_etc_in_the_dishbowl` | HPAF-Flat | goal omission | 1.000 | verifier failure fields violate schema |
| `env1::bring_coffeepot_and_peach_to_the_coffee_table` | ProgPrompt-Compat | process lifecycle incomplete | 1.000 | missing evaluator condition |
| `env1::microwave_chicken` | HPAF-Flat | process lifecycle incomplete | 0.909 | <character> (1) is not close to <fridge> (225) when executing "[CLOSE] <fridge> (225) [0]" |
| `env2::turn_on_tv` | HPAF-Flat | goal omission | 0.000 | verifier failure fields violate schema |
| `env2::put_the_soap_in_the_bathroomcabinet` | HPAF-Flat | goal omission | 0.000 | verifier failure fields violate schema |
| `env2::put_milk_in_the_fridge` | HPAF-Flat | goal omission | 0.000 | verifier failure fields violate schema |
| `test_unseen::watch_tv` | HPAF-Flat | goal omission | 0.000 | verifier failure fields violate schema |
| `test_unseen::make_toast` | HPAF-Flat | process lifecycle incomplete | 1.000 | missing evaluator condition |
| `test_unseen::make_toast` | HPAF-Full | process lifecycle incomplete | 0.857 | Atomic A1 remained done=false after Retry-1 |
| `env1::watch_tv` | ProgPrompt-Compat | alignment error | 0.889 | <character> (1) does not face <tv> (300) when executing "[WATCH] <tv> (300) [0]" |
| `env1::watch_tv` | HPAF-Flat | goal omission | 0.000 | verifier failure fields violate schema |
| `env1::wash_the_dishbowl_in_dishwasher` | ProgPrompt-Compat | process lifecycle incomplete | 1.000 | missing evaluator condition |
| `env1::wash_the_dishbowl_in_dishwasher` | HPAF-Flat | process lifecycle incomplete | 1.000 | missing evaluator condition |
| `env1::wash_the_dishbowl_in_dishwasher` | HPAF-Full | process lifecycle incomplete | 0.929 | Atomic A1 remained done=false after Retry-1 |
| `env2::make_toast` | HPAF-Flat | process lifecycle incomplete | 1.000 | missing evaluator condition |
| `env2::make_toast` | HPAF-Full | process lifecycle incomplete | 1.000 | Atomic A1 remained done=false after Retry-1 |
| `env2::wash_the_cutlery_in_dishwasher` | ProgPrompt-Compat | process lifecycle incomplete | 1.000 | missing evaluator condition |
| `env2::wash_the_cutlery_in_dishwasher` | HPAF-Flat | process lifecycle incomplete | 0.636 | verifier failure fields violate schema |
| `env2::wash_the_cutlery_in_dishwasher` | HPAF-Full | process lifecycle incomplete | 1.000 | missing evaluator condition |
| `env2::make_coffee_in_coffeemaker` | ProgPrompt-Compat | process lifecycle incomplete | 0.579 | <character> (1) is not close to <sink> (155) when executing "[PUTIN] <coffeepot> (170) <sink> (155) [0]" |
| `env2::make_coffee_in_coffeemaker` | HPAF-Flat | process lifecycle incomplete | 0.000 | verifier failure fields violate schema |
| `env2::make_coffee_in_coffeemaker` | HPAF-Full | process lifecycle incomplete | 0.857 | Atomic A1 remained done=false after Retry-1 |
| `vh40_long_s0_01` | ProgPrompt-Compat | dependency violation | 1.000 | missing evaluator condition |
| `vh40_long_s0_02` | ProgPrompt-Compat | terminal constraint miss | 0.778 | <washingmachine> (72) not lookable when executing "[WATCH] <washingmachine> (72) [0]" |
| `vh40_long_s0_03` | ProgPrompt-Compat | terminal constraint miss | 0.941 | bad action syntax |
| `vh40_long_s0_04` | ProgPrompt-Compat | dependency violation | 1.000 | missing evaluator condition |
| `vh40_long_s1_05` | ProgPrompt-Compat | terminal constraint miss | 0.947 | bad action syntax |
| `vh40_long_s1_06` | ProgPrompt-Compat | dependency violation | 1.000 | missing evaluator condition |
| `vh40_long_s1_06` | HPAF-Full | process lifecycle incomplete | 1.000 | missing evaluator condition |
| `vh40_long_s1_07` | ProgPrompt-Compat | dependency violation | 1.000 | missing evaluator condition |
| `vh40_long_s1_07` | HPAF-Flat | terminal constraint miss | 0.765 | verifier failure fields violate schema |
| `vh40_long_s1_08` | ProgPrompt-Compat | dependency violation | 1.000 | missing evaluator condition |
| `vh40_long_s2_09` | ProgPrompt-Compat | terminal constraint miss | 1.000 | missing evaluator condition |
| `vh40_long_s2_10` | ProgPrompt-Compat | dependency violation | 0.889 | <microwave> (171) not lookable when executing "[WATCH] <microwave> (171) [0]" |
| `vh40_long_s2_10` | HPAF-Full | process lifecycle incomplete | 1.000 | missing evaluator condition |
| `vh40_long_s2_11` | ProgPrompt-Compat | dependency violation | 1.000 | missing evaluator condition |
