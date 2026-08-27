# Phase-6 Independent Audit Report

## 1. Dataset correctness

**PASS.** Official primary inventory is 70 task-scene instances, the 35-candidate construction is correct, the final set is 20 instances / 18 unique texts, and direct GT flattening confirms Short/Medium/Long = 6/10/4. `held-out` must not be presented as synonymous with `task-unseen`; five selected env instances use three task texts seen in train.

## 2. Task filtering correctness

**PASS (conservative).** No included task lacks a stable frozen endpoint, and no filtering decision depends on formal method output. Independent replay confirms all 128/128 non-empty released GT primitives across the 15 excluded held-out tasks execute through the shared interface; exclusion is about missing persistent/evaluable natural-language semantics, not primitive executability. Nine appliance/event tasks could be reconsidered only under a new pre-frozen generic trace evaluator; six remain unreliable. The formal set was not modified.

## 3. Metric recomputation

**PASS.** Offline replay confirms ProgPrompt 16/20, Flat 15/20, Full 19/20. Reported Exec is macro average; supplemental micro Exec is 0.905882, 0.939130, 0.948718 respectively.

## 4. Cost accounting

**PASS (arithmetic).** All per-call prompt/completion tokens are present and sum exactly. Calls are 172/40/80 and tokens are 102310/47646/88088. Full includes all TaskAgent and verifier costs.

## 5. Prompt leakage

**PASS.** All 292 actual formal prompts were searched. No frozen semantic payload, unexplained GT action, GT final/evaluator field, future TaskAgent atomic answer, or score was found.

## 6. Baseline fidelity

**ISSUE.** The adapter preserves the official three examples, DSL, assertions, adjacent else recovery, and per-subgoal cap, but it is not a strict official replication. It narrows the released 21-name import to the shared 17-action graph interface by removing `turnright`, `turnleft`, `walkforward`, and `walktowards`; fixes same-class object grounding with `seed=0` where the released default path uses unseeded module-level `random.choice`; and uses Responses API rather than the released Completion API. Server-side frequency penalty is not applied, stop is post-processed locally, and most importantly assertion max output is 600 rather than the released 2. Forty-five of 152 assertions are non-binary first lines, and substring parsing can turn intended affirmative answers into false recovery gates. The reported result is real for this adapter, not a strict official ProgPrompt replication.

## 7. HPAF fidelity

**PASS within the declared abstraction.** Raw logs show 20 real TaskAgent calls, current-state atomic ProgramAgent calls, 30 real Full verifier calls including post-repair, four Retry-1 calls, state refresh, and early stop. This benchmark uses symbolic perception surrogate and does not validate real RGB-D/VLM perception.

## 8. Fairness

**PARTIAL.** Methods share environment graphs, Evolving Graph backend, the same narrowed 17-action interface, deterministic grounding seed, final evaluator, model, temperature, max-output setting, and thinking setting. They intentionally do not receive identical observations/prompts: ProgPrompt generation has examples but no state; assertions see filtered local state; HPAF sees richer current symbolic observations and typed trace/errors. These are method-design differences, but the ProgPrompt assertion-contract deviation creates an avoidable fidelity/cost disadvantage.

## 9. Main result confidence

Current supported statement:

On one frozen run of 20 selected official held-out task-scene instances (18 unique texts), this exact adapted implementation achieved HPAF-Full **19/20 (95%)** vs ProgPrompt **16/20 (80%)**, with macro Exec 0.9596 vs 0.9183, 4.00 vs 8.60 calls/task, and 4404.4 vs 5115.5 tokens/task. The raw arithmetic is +15 percentage points, 53.5% fewer calls, and 13.9% fewer measured tokens. Full fixes four ProgPrompt failures and introduces one failure, net +3 tasks.

Unsupported overclaims:

- `Task decomposition caused a 20-point gain over Flat.` Only one of four Flat-to-Full conversions is explicitly multi-atomic; two are directly Retry-1, and one is single-atomic prompt behavior.
- `The 13.9% token reduction is a clean method comparison.` ProgPrompt assertion output cap/fidelity inflates and perturbs its assertion completions.
- `Results are statistically stable or broadly generalize.` There is one run, temperature 0 has no provider seed, N=20, and Long N=4.
- `HPAF improves real visual perception.` VirtualHome provides symbolic observations.
- `All held-out tasks are task-unseen.` Env holdout and task-text holdout are different.

## 10. Minimum next experiment

Fix and freeze only the ProgPrompt assertion contract to reproduce the released binary check (`max_output_tokens` equivalent to 2 and exact `True`/`False` parsing, while preserving the same prompt and adjacent recovery semantics), then rerun one complete 20-task x 3-method matrix. Do not add tasks or tune prompts from outcomes. This single corrected matrix is more valuable than repetitions of the currently fidelity-compromised baseline; repetition can be considered only after it passes the same offline audit.
