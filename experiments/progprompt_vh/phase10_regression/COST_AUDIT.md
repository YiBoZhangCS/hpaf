# Phase-10R Cost Audit

| Method | Role | Calls | Prompt tokens | Completion tokens | Total tokens | Calls/task | Tokens/task |
|---|---|---:|---:|---:|---:|---:|---:|
| HPAF-Flat | flat_program_agent | 40 | 51615 | 6608 | 58223 | 1.00 | 1455.6 |
| HPAF-Flat | flat_verifier | 40 | 47389 | 3038 | 50427 | 1.00 | 1260.7 |
| HPAF-Full | atomic_program_agent | 53 | 74100 | 7001 | 81101 | 1.32 | 2027.5 |
| HPAF-Full | atomic_verifier | 53 | 52126 | 3181 | 55307 | 1.32 | 1382.7 |
| HPAF-Full | post_repair_verifier | 16 | 16055 | 1300 | 17355 | 0.40 | 433.9 |
| HPAF-Full | repair_program_agent | 16 | 27799 | 1902 | 29701 | 0.40 | 742.5 |
| HPAF-Full | task_agent | 40 | 50133 | 4037 | 54170 | 1.00 | 1354.2 |
| ProgPrompt-Compat | assertion_verification | 413 | 178695 | 1089 | 179784 | 10.32 | 4494.6 |
| ProgPrompt-Compat | whole_program_generation | 40 | 76474 | 16256 | 92730 | 1.00 | 2318.2 |
