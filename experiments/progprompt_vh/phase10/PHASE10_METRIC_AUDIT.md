# Phase-10 Metric and Integrity Audit

- Formal records: 36/36; unique pairs: 36/36; repeat/resample: 0.
- Infrastructure recovery: one interrupted session after 29 records; resume skipped all 29 completed pairs and executed only the 7 missing pairs. Completed-pair repeats: 0.
- Reference replay feasible and evaluator-valid: 12/12.
- Frozen method, prompt, manifest, evaluator, and config hashes reverified: PASS.
- Manifest and raw-run completion hashes: PASS.
- Gold semantics/reference payload in method prompts: False.
- Flat TaskAgent calls: 0.
- Full Structured IR parse success: 100.0%; validator rejection: 0.0%.
- Full mean atomic count: 2.25; mean dependency depth: 2.25; mean terminal constraints: 1.00.
- Full atomic verifier success: 88.5%; retry/task: 0.50; early-stop/task: 25.0%.
- Primary metrics: Task SR, Macro Exec, calls/task, tokens/task. Goal Completion Ratio is supplementary.
