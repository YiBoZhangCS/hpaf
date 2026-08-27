# Phase-7 Final Results

## Regression result

| Method | N | Success | SR | Macro Exec | Micro Exec | Tokens/task | Calls/task |
|---|---:|---:|---:|---:|---:|---:|---:|
| ProgPrompt | 20 | 17 | 0.8500 | 0.8116 | 0.7769 | 4523.6 | 8.65 |
| HPAF-Flat | 20 | 18 | 0.9000 | 0.9875 | 0.9833 | 2509.8 | 2.00 |
| HPAF-Full | 20 | 20 | 1.0000 | 0.9917 | 0.9913 | 4320.9 | 3.80 |

## Official confirmatory result

| Method | N | Success | SR | Macro Exec | Micro Exec | Tokens/task | Calls/task |
|---|---:|---:|---:|---:|---:|---:|---:|
| ProgPrompt | 9 | 4 | 0.4444 | 0.7202 | 0.7101 | 5015.9 | 10.11 |
| HPAF-Flat | 9 | 1 | 0.1111 | 0.8750 | 0.8696 | 2772.6 | 2.00 |
| HPAF-Full | 9 | 1 | 0.1111 | 0.8333 | 0.8615 | 6458.2 | 5.44 |

## Combined engineering result

| Method | N | Success | SR | Macro Exec | Micro Exec | Tokens/task | Calls/task |
|---|---:|---:|---:|---:|---:|---:|---:|
| ProgPrompt | 29 | 21 | 0.7241 | 0.7833 | 0.7532 | 4676.4 | 9.10 |
| HPAF-Flat | 29 | 19 | 0.6552 | 0.9526 | 0.9418 | 2591.3 | 2.00 |
| HPAF-Full | 29 | 21 | 0.7241 | 0.9425 | 0.9444 | 4984.2 | 4.31 |

## HPAF-Full comparisons

| Set | Compared with | Success difference | SR pp | Macro Exec pp | Micro Exec pp | Token reduction | Call reduction |
|---|---|---:|---:|---:|---:|---:|---:|
| Confirmatory | ProgPrompt | -3 | -33.33 | 11.31 | 15.14 | -28.76% | 46.15% |
| Confirmatory | HPAF-Flat | 0 | 0.00 | -4.17 | -0.80 | -132.93% | -172.22% |
| Combined | ProgPrompt | 0 | 0.00 | 15.93 | 19.12 | -6.58% | 52.65% |
| Combined | HPAF-Flat | 2 | 6.90 | -1.01 | 0.26 | -92.34% | -115.52% |

## Complexity

Horizon and atomic-count breakdowns are in `results/summary_by_horizon.csv` and `results/summary_by_atomic_count.csv`; Long confirmatory N=0, so no long-horizon confirmatory claim is made.

## Fidelity and audits

- Assertion strict-binary: 175/235 (74.5%); outputs `{'True': 127, "Let's": 60, 'False': 48}`. Malformed output is retained as unparsed; no semantic fallback or repair call was used. Baseline fidelity verdict: **ISSUE** for this Responses backend.
- Dataset integrity: **PASS**; regression=20, confirmatory=9, combined=29; persistent=20, trace=9, synthetic=0.
- Prompt leakage: **PASS** across 447 formal calls.
- Flat/Full ProgramAgent fairness: **PASS**; exact shared generic rule block, action documentation, and verifier settings.
- Automatically selected case task IDs: ['test_unseen::bring_coffeepot_and_cupcake_to_the_coffee_table', 'test_unseen::wash_the_plate', 'test_unseen::make_toast', 'test_unseen_ambiguous_goals::collect_4_fruits_such_as_apple,_banana,_etc_in_the_dishbowl'].

## Resume-ready statement

We evaluate ProgPrompt, HPAF-Flat, and HPAF-Full on 29 official ProgPrompt/VirtualHome task-scene instances: a disclosed 20-instance regression set and a separate 9-instance confirmatory set restored with pre-frozen method-independent event/appliance trace predicates; no synthetic tasks are mixed into the official result.
