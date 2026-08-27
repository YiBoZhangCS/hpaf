# Independently Recomputed Phase-6 Metrics

Source: immutable `results/raw_runs.jsonl`, SHA-256 `4197aa59a2851be3f96fbcce0a9016567b27952987f5a7754e4bcd75baefe75e`. Aggregates below do not read `summary_main.csv`. All 60 stored grounded traces were replayed from frozen initial graphs; replayed Semantic SR, Official SR, and task Exec matched every raw record.

## Main recomputation

| Method | Successes/N | Semantic SR | Macro Exec | Micro Exec | Successful/attempted actions | Calls | Prompt tokens | Completion tokens | Total tokens | Avg calls/task | Avg tokens/task |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ProgPrompt | 16/20 | 0.800 | 0.918328 | 0.905882 | 231/255 | 172 | 83943 | 18367 | 102310 | 8.60 | 5115.5 |
| HPAF-Flat | 15/20 | 0.750 | 0.935000 | 0.939130 | 108/115 | 40 | 44243 | 3403 | 47646 | 2.00 | 2382.3 |
| HPAF-Full | 19/20 | 0.950 | 0.959583 | 0.948718 | 111/117 | 80 | 83103 | 4985 | 88088 | 4.00 | 4404.4 |

The reported Exec is **macro Exec**: the arithmetic mean of each task's successful-actions/attempted-actions ratio. Micro Exec is supplied only as an offline supplement and does not replace the frozen result.

## Per-role cost ledger

| Method | Role | Calls | Prompt tokens | Completion tokens | Total tokens |
|---|---|---:|---:|---:|---:|
| ProgPrompt | `assertion_verification` | 152 | 45841 | 12218 | 58059 |
| ProgPrompt | `whole_program_generation` | 20 | 38102 | 6149 | 44251 |
| HPAF-Flat | `flat_program_agent` | 20 | 26522 | 2161 | 28683 |
| HPAF-Flat | `flat_verifier` | 20 | 17721 | 1242 | 18963 |
| HPAF-Full | `atomic_program_agent` | 26 | 34975 | 2239 | 37214 |
| HPAF-Full | `atomic_verifier` | 26 | 20328 | 1309 | 21637 |
| HPAF-Full | `post_repair_verifier` | 4 | 2841 | 212 | 3053 |
| HPAF-Full | `repair_program_agent` | 4 | 7378 | 270 | 7648 |
| HPAF-Full | `task_agent` | 20 | 17581 | 955 | 18536 |

Full accounting is exactly TaskAgent 20 + atomic ProgramAgent 26 + atomic verifier 26 + repair ProgramAgent 4 + post-repair verifier 4 = 80 calls. Its 88,088 total tokens include every one of those roles, hence 4,404.4 tokens/task and 4.00 calls/task.

ProgPrompt accounting is exactly 20 whole-program generation + 152 assertion calls = 172 calls, hence 8.60 calls/task. Assertions are embedded precondition checks: a false gate executes the immediately adjacent `else:` recovery action(s); it is neither whole-task failure nor full replanning.

Concrete frozen trace (`test_unseen::turn_off_light`): one whole-program call generated `walk -> find -> assert close / else find -> assert switchon / else switchon -> switchoff`. After the successful walk/find, the first assertion prompt included `You see: lightswitch is ON.` and `assert('close' to 'lightswitch')`; its output was `False`, so only the adjacent recovery `find('lightswitch')` executed. The second assertion returned the non-binary first line `Let's analyze this step by step:`. Because it contained no `true`, runtime treated it as false and executed adjacent `switchon`, which failed because the light was already on; execution nevertheless continued to `switchoff`, which succeeded. The task therefore passed with Exec 4/5, proving an assertion false gate is local recovery rather than whole-task failure or replanning while also exposing the binary-contract bug.

Across generated ProgPrompt programs there are 178 `else:` branches: 84 were skipped after true gates and 94 were executed after false gates. There were 152 assertion calls; runtime parsing classified 76 true and 76 false by substring search.

## Assertion fidelity issue

Only 107/152 assertion outputs are strict `True`/`False`; 45 begin with explanatory text. Phase 6 uses max output 600 while the released executor uses max tokens 2. Because runtime truth is `'true' in output_text.lower()`, semantically affirmative verbose first lines can be treated as false. This is a baseline-fidelity/control-flow issue, not an arithmetic accounting error.

## Task-level win/loss matrix

| Task | ProgPrompt | Flat | Full | GT actions | Horizon | Atomic count |
|---|---:|---:|---:|---:|---|---:|
| `test_unseen::turn_off_light` | 1 | 1 | 1 | 3 | Short | 1 |
| `test_unseen::throw_away_apple` | 1 | 1 | 1 | 8 | Medium | 1 |
| `test_unseen::put_salmon_in_the_fridge` | 1 | 1 | 1 | 8 | Medium | 1 |
| `test_unseen::wash_the_plate` | 1 | 1 | 1 | 18 | Long | 1 |
| `test_unseen::bring_coffeepot_and_cupcake_to_the_coffee_table` | 1 | 1 | 1 | 8 | Medium | 2 |
| `test_unseen::microwave_salmon` | 1 | 1 | 1 | 11 | Long | 2 |
| `test_unseen_ambiguous_goals::collect_4_fruits_such_as_apple,_banana,_etc_in_the_dishbowl` | 0 | 0 | 1 | 14 | Long | 4 |
| `env1::turn_off_tablelamp` | 1 | 1 | 1 | 2 | Short | 1 |
| `env1::put_the_soap_in_the_bathroomcabinet` | 1 | 1 | 1 | 6 | Medium | 1 |
| `env1::throw_away_plum` | 1 | 0 | 1 | 6 | Medium | 1 |
| `env1::bring_my_book_to_the_sofa` | 0 | 1 | 1 | 4 | Short | 1 |
| `env1::put_chicken_in_the_fridge` | 1 | 0 | 1 | 6 | Medium | 1 |
| `env1::bring_coffeepot_and_peach_to_the_coffee_table` | 0 | 1 | 1 | 7 | Medium | 2 |
| `env1::microwave_chicken` | 1 | 0 | 0 | 13 | Long | 2 |
| `env2::open_the_curtains` | 1 | 1 | 1 | 2 | Short | 1 |
| `env2::turn_on_tv` | 1 | 1 | 1 | 2 | Short | 1 |
| `env2::put_the_soap_in_the_bathroomcabinet` | 1 | 1 | 1 | 6 | Medium | 1 |
| `env2::throw_away_bananas` | 1 | 0 | 1 | 6 | Medium | 1 |
| `env2::bring_my_book_to_the_sofa` | 0 | 1 | 1 | 4 | Short | 1 |
| `env2::put_milk_in_the_fridge` | 1 | 1 | 1 | 6 | Medium | 1 |

- All success (12): `test_unseen::turn_off_light`, `test_unseen::throw_away_apple`, `test_unseen::put_salmon_in_the_fridge`, `test_unseen::wash_the_plate`, `test_unseen::bring_coffeepot_and_cupcake_to_the_coffee_table`, `test_unseen::microwave_salmon`, `env1::turn_off_tablelamp`, `env1::put_the_soap_in_the_bathroomcabinet`, `env2::open_the_curtains`, `env2::turn_on_tv`, `env2::put_the_soap_in_the_bathroomcabinet`, `env2::put_milk_in_the_fridge`
- ProgPrompt-only success (1): `env1::microwave_chicken`
- Flat-only success (0): none
- Full-only success (1): `test_unseen_ambiguous_goals::collect_4_fruits_such_as_apple,_banana,_etc_in_the_dishbowl`
- ProgPrompt fail / Full success (4): `test_unseen_ambiguous_goals::collect_4_fruits_such_as_apple,_banana,_etc_in_the_dishbowl`, `env1::bring_my_book_to_the_sofa`, `env1::bring_coffeepot_and_peach_to_the_coffee_table`, `env2::bring_my_book_to_the_sofa`
- Full fail / ProgPrompt success (1): `env1::microwave_chicken`

Full's only failure is `env1::microwave_chicken`. Moving from 16/20 to 19/20 means Full fixes all four ProgPrompt failures but introduces one failure on a task ProgPrompt solved: +4 - 1 = net +3 tasks, or +15 percentage points.

## What Full > Flat supports

Flat fails five tasks; Full also fails microwave chicken and converts the other four. Two one-atomic conversions (`env1::throw_away_plum`, `env2::throw_away_bananas`) are directly attributable in-trace to verifier-triggered Retry-1 opening the closed garbage can. `env1::put_chicken_in_the_fridge` is one atomic with no retry, so its conversion cannot be decomposition; it reflects different TaskAgent rewriting/program prompts and possibly backend nondeterminism. The four-fruit task is the one direct multi-atomic example where decomposition plus current-state regeneration avoids Flat's multi-instance dishbowl binding failure.

The observed 95% vs 75% therefore supports the Full package (TaskAgent rewriting, current-state atomic generation, online verification, and Retry-1), not the claim that decomposition alone adds 20 points. One temperature-zero run without a provider seed cannot separate prompt/sampling nondeterminism.
