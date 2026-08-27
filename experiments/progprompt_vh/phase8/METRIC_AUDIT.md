# Phase-8 Metric Audit

- Raw formal records: **90**.
- Unique task-method pairs: **90**.
- Per method: 30 records, with 10 each at 2, 3, and 4 goals.
- Per-record token and call totals were independently checked against saved calls.
- Final raw SHA-256: `e231870000e2843f5aa50004060523e0a3d36164dc08cdc2632a95ff7fe8c268`.
- Frozen manifest SHA-256: `9eb12933135939eb6465e81090247155293cd641d5772face2adde30e1f3f36e`.
- ProgPrompt strict binary assertions: 353/353.
- Records containing online-verifier parse failures: 14;
  these recorded control-flow outcomes are not used as final scores.

| Method | Success/N | SR | Mean GCR | Macro Exec | Micro Exec | Tokens/task | Calls/task |
|---|---:|---:|---:|---:|---:|---:|---:|
| ProgPrompt-Compat | 6/30 | 20.0% | 48.9% | 0.911 | 0.891 | 7569.9 | 12.77 |
| HPAF-Flat | 23/30 | 76.7% | 89.7% | 0.952 | 0.958 | 3021.3 | 2.00 |
| HPAF-Full | 30/30 | 100.0% | 100.0% | 0.973 | 0.970 | 8180.6 | 7.47 |

Verdict: **PASS**.
