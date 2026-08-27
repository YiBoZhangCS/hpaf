# Phase-8 Final Results

## Method freeze

ProgPrompt compatibility: binary-constrained ARK Responses enum; unchanged
semantic assertion prompt; exact parser; no fallback or second call. Development
assertions were 152/152 binary; formal assertions were
353/353 binary.

Process-goal changes: generic `completion_mode=state|process`, generic complete
lifecycle ProgramAgent rule, and process-aware online verification. Process
development success improved from 1/9 to
7/9 in one iteration.

Token compression: REJECTED by the predeclared gate. Success changed from
27/29 to
24/29, Macro Exec from
0.950 to
0.872, and tokens/task
from 5617.3 to
7551.9. The formal
method uses the frozen uncompressed fallback.

HPAF framework changed: **NO**. It remains TaskAgent -> atomics -> ProgramAgent ->
execute -> verifier -> at most one Retry-1.

## Development regression

| Method | N | Success | SR | Macro Exec | Tokens/task | Calls/task |
|---|---:|---:|---:|---:|---:|---:|
| ProgPrompt-Compat | 29 | 21 | 72.4% | 0.947 | 5766.4 | 9.10 |
| HPAF-Flat | 29 | 18 | 62.1% | 0.827 | 2521.6 | 2.00 |
| HPAF-Full | 29 | 27 | 93.1% | 0.950 | 5617.3 | 4.86 |


This table is official **development/regression only**, not an untouched test.

Process tasks: 1/9 -> 7/9.

HPAF compression A/B: 5617.3
-> 7551.9 tokens/task;
the attempted compression was not adopted.

## Final benchmark provenance

- Name: VirtualHome Compositional Stress Benchmark.
- Source: official VirtualHome scene inventories + synthetic deterministic compositions.
- Synthetic: YES.
- Seed: 20260826.
- Tasks: 30; 2-goal: 10; 3-goal: 10; 4-goal: 10.
- Exact overlap with train/dev: 0.
- Reference feasibility: 30/30.
- Formal execution: 90/90 unique pairs, one run each, no repeats.

## Final main result

| Method | 2-goal SR | 3-goal SR | 4-goal SR | Overall SR | Macro Exec | Tokens/task | Calls/task |
|---|---:|---:|---:|---:|---:|---:|---:|
| ProgPrompt-Compat | 50.0% | 0.0% | 10.0% | 20.0% | 0.911 | 7569.9 | 12.77 |
| HPAF-Flat | 90.0% | 50.0% | 90.0% | 76.7% | 0.952 | 3021.3 | 2.00 |
| HPAF-Full | 100.0% | 100.0% | 100.0% | 100.0% | 0.973 | 8180.6 | 7.47 |


Supplementary mean goal completion ratios: ProgPrompt-Compat
48.9%, Flat 89.7%,
Full 100.0%. Micro Exec values are
0.891, 0.958, and 0.970.

## Complexity scaling

- ProgPrompt-Compat: 50.0% -> 0.0% -> 10.0%; retention 0.20, 2-to-4 drop 40 pp.
- HPAF-Flat: 90.0% -> 50.0% -> 90.0%; retention 1.00, 2-to-4 drop 0 pp (non-monotonic middle stratum).
- HPAF-Full: 100.0% -> 100.0% -> 100.0%; retention 1.00, 2-to-4 drop 0 pp.

## Full vs ProgPrompt

- Overall success: 30/30 vs 6/30 (+24).
- Overall SR: +80.0 pp.
- 4-goal SR: +90.0 pp.
- Macro Exec: +6.23 pp.
- Tokens: -8.1% reduction (negative means Full used more; Full used 8.1% more).
- Calls: +41.5% reduction.

## Full vs Flat

- Overall success: 30/30 vs 23/30 (+7).
- Overall SR: +23.3 pp.
- Macro Exec: +2.06 pp.
- Tokens: Full used 170.8% more.
- Calls: Full used 273.3% more.

This comparison supports that the complete Full pipeline was more robust on this
benchmark. It does not isolate a decomposition-only causal effect because Full
also includes current-state atomic generation, verification, and local Retry-1.

## Cost breakdown

ProgPrompt-Compat: generation 30 calls; assertion 353 calls.
Flat: ProgramAgent 30 calls; verifier 30 calls.
Full: TaskAgent 30; atomic ProgramAgent 90; atomic verifier 90; repair 7;
post-repair verifier 7 calls. Detailed token totals are in `results/cost_by_role.csv`.

## Key failures

ProgPrompt failed 24 tasks; its missing goal conditions were dominated by ON
(28)
and INSIDE (21)
relations, including use of `putin` for surface placement and incomplete
multi-goal execution. Flat failed 7 tasks, mostly open-container preconditions
and one complete multi-goal miss. Full had no final semantic failures; it used
Retry-1 on 7 atomics. 14 records contained online verifier schema parse
errors, but these are control-time diagnostics and final scoring remained fully
offline and method-independent.

## Audit verdict

- Dataset integrity: **PASS**.
- Prompt leakage: **PASS**.
- Baseline compatibility: **PASS**.
- Formal matrix integrity: **PASS** (90 unique pairs, no repeats).
- Prompt/method fairness: **PASS** for shared Flat/Full ProgramAgent rules; the rejected compression is transparently excluded from both.
- Token compression objective: **NOT ACHIEVED; FROZEN FALLBACK USED**.

## Main conclusion

On this pre-frozen synthetic VirtualHome composition benchmark, HPAF-Full achieved
30/30 semantic success across all three goal-count strata, while Flat achieved
23/30 and ProgPrompt-Compat 6/30. Full preserved SR from 2 to 4 goals and used
41.5% fewer LLM calls than ProgPrompt-Compat, but consumed 8.1% more tokens. This
is one-run synthetic stress evidence, not an estimate on the official ProgPrompt
test distribution.

## Resume-ready sentence

Built and pre-froze a 30-task VirtualHome compositional stress benchmark (10 each
at 2/3/4 semantic goals; 30/30 reference-feasible), where HPAF-Full completed
30/30 tasks versus 23/30 for Flat and 6/30 for ProgPrompt-Compat, with 41.5% fewer
LLM calls but 8.1% more tokens than ProgPrompt-Compat.

## Remaining hard issue

The final evidence is a single-run synthetic benchmark; it does not establish
variance across stochastic runs or generalization to the official task distribution.
