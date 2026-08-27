# Phase-8 Cost Audit

All values are summed from actual formal per-call API usage.

| Method | Role | Calls | Prompt | Completion | Total |
|---|---|---:|---:|---:|---:|
| HPAF-Flat | `flat_program_agent` | 30 | 38706 | 6686 | 45392 |
| HPAF-Flat | `flat_verifier` | 30 | 42787 | 2461 | 45248 |
| HPAF-Full | `atomic_program_agent` | 90 | 112685 | 9222 | 121907 |
| HPAF-Full | `atomic_verifier` | 90 | 69650 | 4644 | 74294 |
| HPAF-Full | `post_repair_verifier` | 7 | 4769 | 313 | 5082 |
| HPAF-Full | `repair_program_agent` | 7 | 11404 | 473 | 11877 |
| HPAF-Full | `task_agent` | 30 | 27766 | 4493 | 32259 |
| ProgPrompt-Compat | `assertion_verification` | 353 | 152741 | 969 | 153710 |
| ProgPrompt-Compat | `whole_program_generation` | 30 | 57885 | 15502 | 73387 |

ProgPrompt formal assertions: 353/353 strict binary; 969 total completion tokens (2.75/call).

The attempted HPAF compression was rejected: average development tokens rose from 5617.3 to 7551.9 per task. The formal run therefore uses the frozen uncompressed fallback.
