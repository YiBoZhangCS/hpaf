# Phase-9 Final Report

## Baseline Fidelity Repair

Official behavior: ProgPrompt uses its released whole-program DSL, three few-shot examples, assertion checks, and adjacent `else` recovery. Phase 9 keeps that behavior and uses ARK Responses API strict enum transport with `True`/`False` only.

Old bug: Phase-6 assertions used a 600-token generation cap, unlike the released binary contract, allowing verbose outputs to change recovery control flow.

New behavior: assertion transport is binary-enum constrained and parsed as the released boolean contract; no semantic fallback, repair call, or truth inference was added.

Strict-binary assertion rate: 419/419 (100.0%).

## HPAF Generic Prompt

Changed rules: interaction locality, source-before-target transfer order, held-source/close-target placement preconditions, re-alignment after movement, and typed-error-first Retry-1 repair. The same frozen ProgramAgent rules are used by Flat and Full; no framework agent was added.

The wording is generic: it contains no task ID, object name from a formal task, evaluator condition, or correct test action sequence.

## Dataset

- Regression: 29 official-source held-out task-scene instances previously observed during development.
- Confirmatory: 11 pre-frozen synthetic causal long-horizon extensions on official VirtualHome scenes.
- Combined: 40 task-scene instances; 35 unique task texts.
- Horizon: 9 Short / 16 Medium / 15 Long.
- Evaluators: 20 persistent-state / 9 generic trace / 11 generic causal trace-state.
- Synthetic: 11; never labeled official.

## Confirmatory Main Result

| Method | Success/N | SR | Exec | Tokens/task | Calls/task |
|---|---:|---:|---:|---:|---:|
| ProgPrompt-Compat | 0/11 | 0.0% | 0.897 | 9594.4 | 17.18 |
| HPAF-Flat | 7/11 | 63.6% | 0.809 | 3357.0 | 2.00 |
| HPAF-Full | 3/11 | 27.3% | 0.623 | 6283.2 | 5.73 |

## Combined Result

| Method | Success/N | SR | Exec | Tokens/task | Calls/task |
|---|---:|---:|---:|---:|---:|
| ProgPrompt-Compat | 18/40 | 45.0% | 0.917 | 6882.7 | 11.47 |
| HPAF-Flat | 27/40 | 67.5% | 0.835 | 2726.9 | 2.00 |
| HPAF-Full | 28/40 | 70.0% | 0.841 | 5818.0 | 5.15 |

## Long Provenance Split

| Long subset | ProgPrompt | Flat | Full |
|---|---:|---:|---:|
| Existing official-source Long (N=4) | 25.0% | 50.0% | 75.0% |
| New frozen Long extension (N=11) | 0.0% | 63.6% | 27.3% |
| Combined Long (N=15) | 6.7% | 60.0% | 40.0% |

## HPAF-Full vs ProgPrompt

- Combined success: 28/40 vs 18/40 (+10).
- Combined SR: +25.0 pp; Macro Exec -7.6 pp.
- Tokens/task: 15.5% relative; Calls/task: 55.1% relative.
- New Long-11: Full is 3/11 while Flat is 7/11; decomposition does not automatically dominate the causal extension.

## Complexity

- Short/Medium/Long: 9/16/15.
- Full atomic bins: 1 atomic N=15, 2 atomics N=9, >=3 atomics N=12.
- Long-11 reference actions: min 13, mean 15.36, median 15, max 17; mean causal stages 5.27; 9/11 cross-room.

## Cost Breakdown

- HPAF-Flat / flat_program_agent: 40 calls, 57985 total tokens (1.00 calls/task).
- HPAF-Flat / flat_verifier: 40 calls, 51090 total tokens (1.00 calls/task).
- HPAF-Full / atomic_program_agent: 72 calls, 99992 total tokens (1.80 calls/task).
- HPAF-Full / atomic_verifier: 72 calls, 60573 total tokens (1.80 calls/task).
- HPAF-Full / post_repair_verifier: 11 calls, 11056 total tokens (0.28 calls/task).
- HPAF-Full / repair_program_agent: 11 calls, 19892 total tokens (0.28 calls/task).
- HPAF-Full / task_agent: 40 calls, 41208 total tokens (1.00 calls/task).
- ProgPrompt-Compat / assertion_verification: 419 calls, 182414 total tokens (10.47 calls/task).
- ProgPrompt-Compat / whole_program_generation: 40 calls, 92893 total tokens (1.00 calls/task).

## Key Failures

- ProgPrompt: long-horizon whole-program plans accumulate precondition and relation failures; 419 assertions remained strictly binary.
- Flat: stronger than Full on the new causal Long-11 (7/11 vs 3/11), but with lower micro execution and no local repair.
- Full: official-source regression 25/29, but Long-11 exposes TaskAgent parse failures and verifier/retry limitations; this is retained as a real negative result.

## Integrity

- Dataset: PASS (29 official-source + 11 synthetic; fixed quotas; no post-result filtering).
- Reference feasibility: PASS (11/11 executable and evaluator-successful).
- Prompt leakage: PASS.
- Baseline binary: PASS.
- Fairness: PASS (Flat/Full shared ProgramAgent rules; Full-only difference is decomposition, atomic verification, and Retry-1).
- Formal records: PASS (120/120, duplicate 0, resample 0).

## Resume-Ready Statement

VH-40 evaluates 29 official-source held-out VirtualHome task-scene instances plus 11 pre-frozen synthetic causal long-horizon extensions; in one frozen 40-task run, HPAF-Full achieves 28/40 overall and 6/15 on Long tasks, with 5.15 LLM calls/task.

## Remaining Issue

Full does not dominate the new causal Long-11 extension (3/11 vs Flat 7/11); this is a substantive limitation, not an artifact to be tuned away.
