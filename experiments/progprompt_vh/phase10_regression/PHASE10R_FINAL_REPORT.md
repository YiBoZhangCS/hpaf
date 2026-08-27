# Phase-10R VH-40 Unified Regression Report

VH-40 is a regression matrix, not an unseen test: 29 official-source regression instances plus 11 pre-frozen causal long-horizon extensions.

## Unified VH-40 regression

| Method | Success/N | Task SR | Macro Exec | Calls/task | Tokens/task |
|---|---:|---:|---:|---:|---:|
| ProgPrompt-Compat | 22/40 | 55.0% | 0.956 | 11.32 | 6812.9 |
| HPAF-Flat | 26/40 | 65.0% | 0.817 | 2.00 | 2716.2 |
| HPAF-Full | 32/40 | 80.0% | 0.951 | 4.45 | 5940.9 |

Supplementary: Micro Exec / GCR — ProgPrompt-Compat 0.942/0.722; HPAF-Flat 0.846/0.660; HPAF-Full 0.940/0.827.

## Official-source regression subset

| Method | Success/N | Task SR | Macro Exec | Calls/task | Tokens/task |
|---|---:|---:|---:|---:|---:|
| ProgPrompt-Compat | 22/29 | 75.9% | 0.954 | 9.21 | 5807.8 |
| HPAF-Flat | 16/29 | 55.2% | 0.758 | 2.00 | 2564.4 |
| HPAF-Full | 23/29 | 79.3% | 0.943 | 3.90 | 5168.7 |

## Long-15

| Method | Success/N | Task SR | Macro Exec | Calls/task | Tokens/task |
|---|---:|---:|---:|---:|---:|
| ProgPrompt-Compat | 2/15 | 13.3% | 0.952 | 16.60 | 9322.7 |
| HPAF-Flat | 11/15 | 73.3% | 0.955 | 2.00 | 3101.1 |
| HPAF-Full | 12/15 | 80.0% | 0.968 | 5.40 | 7671.3 |

## Long provenance

| Method | Official Long-4 | Causal Long-11 | Combined Long-15 |
|---|---:|---:|---:|
| ProgPrompt-Compat | 2/4 | 0/11 | 2/15 |
| HPAF-Flat | 1/4 | 10/11 | 11/15 |
| HPAF-Full | 3/4 | 9/11 | 12/15 |

## Semantic complexity

| Dimension | Bin | N | ProgPrompt SR | Flat SR | Full SR |
|---|---|---:|---:|---:|---:|
| atomic_count | 1 | 29 | 75.9% | 55.2% | 79.3% |
| atomic_count | 2 | 9 | 0.0% | 88.9% | 77.8% |
| atomic_count | 3 | 2 | 0.0% | 100.0% | 100.0% |
| atomic_count | >=4 | 0 | — | — | — |
| dependency_depth | D=1 | 29 | 75.9% | 55.2% | 79.3% |
| dependency_depth | D=2 | 9 | 0.0% | 88.9% | 77.8% |
| dependency_depth | D=3 | 2 | 0.0% | 100.0% | 100.0% |
| dependency_depth | D>=4 | 0 | — | — | — |

Complexity bins are frozen benchmark-semantic bins shared by all methods; they do not use dynamic method decompositions.

## Full internal diagnostics

- TaskAgent IR parse success: 100.0%.
- Validator rejection: 0.0%.
- Mean atomic count: 1.325.
- Mean dependency depth: 1.325.
- Mean terminal constraints: 0.350.
- Atomic verifier done=true: 83.0% (44/53).
- Retry-1 triggers: 16; recoveries: 7.
- Early stops: 9.
- TaskAgent failures: 0.
- ProgramAgent failure tasks: 0.
- Dependency execution mismatches: 0.

## Full vs Flat

Success difference: +6 tasks; Long-15 difference: +1; Macro Exec: 0.951 vs 0.817.
Flat fail / Full success: 8; Flat success / Full fail: 2. This is a whole frozen-system comparison, not a decomposition-only gain estimate.

## Full vs ProgPrompt

Success difference: +10 tasks. Calls/task: 4.45 vs 11.32 (60.7% fewer for Full). Tokens/task: 5940.9 vs 6812.9 (Full minus ProgPrompt -872.0).

## Phase-9 vs Phase-10R

| Method | Phase-9 corrected | Phase-10R unified rerun | Difference |
|---|---:|---:|---:|
| ProgPrompt-Compat | 18/40 | 22/40 | +4 |
| HPAF-Flat | 27/40 | 26/40 | -1 |
| HPAF-Full | 32/40 | 32/40 | +0 |

ARK does not expose a deterministic generation seed for these calls. Temperature is zero, but backend nondeterminism can remain; score differences must not be attributed wholly to code changes.

The existing Phase-10 12-task holdout remains separate independent validation evidence. It is not pooled with VH-40 into a 52-task score.

## Relation to the Phase-10 holdout

The existing 12-task Phase-10 holdout remains separate independent validation evidence (ProgPrompt 0/12, Flat 6/12, Full 10/12). No 52-task aggregate is reported.

## Integrity

- Manifest hash: PASS.
- Method hash: PASS.
- Evaluator hash: PASS.
- Formal records: 120/120.
- Unique pairs: 120.
- Duplicates: 0.
- Planning resamples: 0.
- Post-result task filtering: 0.
- Prompt changes after start: 0.
- Evaluator changes after start: 0.
- ProgPrompt strict binary: 413/413 (100.0%).
- Leakage: PASS.
- Backend identity: PASS.
- Flat TaskAgent calls: 0.
- Raw runs SHA-256: `82f15f6af74f99d2a084897c2fc4c7d7e8d8a3a382a99c184d93e5dfa36432b7`.
- Formal delivery records SHA-256: `90f726067189df45605e6100fa951581c966e71c754d9bf35ffafa93c8a73b5b`.
- Per-call total tokens: 711/711 (100.0%).

## PPT recommended table

| Method | VH-40 Task SR | Long-15 SR | Macro Exec | LLM Calls/task |
|---|---:|---:|---:|---:|
| ProgPrompt-Compat | 22/40 (55.0%) | 2/15 (13.3%) | 0.956 | 11.32 |
| HPAF-Flat | 26/40 (65.0%) | 11/15 (73.3%) | 0.817 | 2.00 |
| HPAF-Full | 32/40 (80.0%) | 12/15 (80.0%) | 0.951 | 4.45 |

*VH-40 is a unified regression suite: 29 official-source evaluable instances + 11 pre-frozen causal long-horizon extensions.*

## Final interpretation

In the unified VH-40 regression matrix, HPAF-Full completed 32/40, HPAF-Flat 26/40, and ProgPrompt-Compat 22/40. On Long-15 the corresponding counts were 12/15, 11/15, and 2/15. Because all VH-40 tasks were previously observed, these results support a frozen-version regression comparison, not an unseen-generalization claim.
