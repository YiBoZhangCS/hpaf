# Phase-7 Task Provenance

The benchmark uses task-scene instances released with the pinned ProgPrompt/VirtualHome repository. The primary ProgPrompt inventory has 70 instances: 35 train, 10 test-unseen, 5 ambiguous-goal, 10 environment-1, and 10 environment-2. The ten `test_seen` rows are a derived slice of train task texts, not new held-out instances.

Train is an annotated in-context example library, not LLM weight fine-tuning in this release. Train and test-seen are excluded from new confirmatory evaluation because their task texts are available to the baseline prompt library. Environment-held-out instances remain valid environment tests even when their text is train-seen, but must not be mislabeled task-unseen.

The regression set is the exact Phase-6 selected set: 20 official task-scene instances / 18 unique texts. Its outputs were inspected before the Phase-7 generic prompt change, so it is development/regression evidence rather than untouched confirmation.

The confirmatory set restores nine official held-out task-scene instances from the Phase-6 audit's pre-existing `SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR` category. They come from `test_unseen`, `new_env/env1_annotated.json`, and `new_env/env2_annotated.json`. They were previously excluded only because their requested event/appliance outcome lacks a persistent graph state. Their final score now uses a method-independent, result-blind trace predicate frozen before execution. The other six excluded tasks remain out because brushing/eating actions are unavailable or meal content has no unique semantic endpoint.

A local search of the pinned VirtualHome repository found no additional activity annotation inventory with the required task text, task-specific initial state, GT program, and stable final/trace semantics beyond the ProgPrompt release files. No synthetic tasks are used.

Current frozen accounting is generated in `data/dataset_stats.json`: 20 regression, 9 confirmatory, and 29 combined task-scene instances; 24 combined unique task texts; 20 persistent-state evaluated and 9 trace-evaluated; synthetic = 0.

Interview statement:

“We evaluate ProgPrompt, HPAF-Flat, and HPAF-Full on 29 official ProgPrompt/VirtualHome task-scene instances: a disclosed 20-instance regression set and a separate 9-instance confirmatory set restored with pre-frozen method-independent event/appliance trace predicates; no synthetic tasks are mixed into the official result.”

