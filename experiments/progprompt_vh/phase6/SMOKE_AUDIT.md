# Phase-6 Smoke Audit

## Attempt 001

The complete Short/Medium/Long × three-method matrix produced nine records.
ProgPrompt made 24 real assertion LLM calls and exercised/skipped 14 recovery
branches. HPAF-Flat made one ProgramAgent and one whole-task verifier call per
task. HPAF-Full made and costed three TaskAgent calls, verified every attempted
atomic online, and exercised the entire Retry-1 path once. No HPAF online prompt
contained frozen semantic conditions, GT final state, or the official goal set.

One generic observation/verifier contract defect was found before formal
execution. After HPAF-Full successfully switched off one lightswitch instance,
the class-level symbolic observation listed `lightswitch is OFF` and
`lightswitch is ON` because a different instance retained ON. The LLM treated
that as a logical contradiction, returned `done=false`, and repeated the false
negative after repair, although the independent evaluator found the task
complete.

The generic verifier instruction is clarified: VirtualHome class names can
represent multiple instances; for singular/unspecified requests, one successfully
interacted matching instance is sufficient, while other instances need not share
the state unless the instruction explicitly says all/every/both. No task name,
semantic condition, method output, or evaluator score is inserted. Frozen task
set, semantic goals, action set, and horizon definition remain unchanged.

Attempt 001 is preserved under `results/smoke/attempt_001`. A complete attempt
002 is required before formal execution, and its implementation hash must become
the formal lock.

## Attempt 002

The complete Short/Medium/Long × three-method matrix again produced nine
unique records and passed the frozen protocol checks. ProgPrompt made 24 real
assertion-verification calls and recorded 14 recovery events. HPAF-Full made
exactly three TaskAgent calls and required no Retry-1 repair. All nine runs
completed without an LLM/API error, and the independent semantic evaluator
reported success for every smoke task-method pair.

The generic multi-instance clarification removed the Attempt-001 false negative:
HPAF-Full completed `turn off light` after its first atomic verifier call, with
no repair or early stop. Prompt inspection again found no frozen semantic goal,
GT final state, or official goal set in any method/verifier request.

Attempt 002 is preserved under `results/smoke/attempt_002` and is the sole
formal-run gate. `results/smoke/PASSED.json` freezes implementation SHA-256
`0daf61072d16151050ee62ad58010cc2e189f1c89f0b1ee83d31afe254891222`
together with all task, goal, action-set, dataset-source, and Phase-5 hashes.
