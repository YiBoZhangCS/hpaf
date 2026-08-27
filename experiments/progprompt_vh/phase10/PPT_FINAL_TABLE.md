# Phase-10 PPT Final Table

| Method | Success/12 | SR | Macro Exec | Calls/task | Tokens/task | GCR (supp.) |
|---|---:|---:|---:|---:|---:|---:|
| ProgPrompt-Compat | 0/12 | 0.0% | 0.877 | 16.92 | 9456.8 | 0.440 |
| HPAF-Flat | 6/12 | 50.0% | 0.851 | 2.00 | 3217.3 | 0.715 |
| HPAF-Full | 10/12 | 83.3% | 0.950 | 6.33 | 8789.1 | 0.932 |

**Method:** Instruction -> semantic atomic IR + DAG -> current atomic `P -> (A -> I)^k -> V` -> refresh -> next ready atomic.

**Data-supported conclusion:** In the single pre-frozen 12-task causal holdout, HPAF-Full completed 10/12, HPAF-Flat 6/12, and ProgPrompt-Compat 0/12. This supports only the observed one-run comparison under the frozen semantic-DAG evaluator.

**Limitation:** The largest limitation is that the final evidence is one deterministic 12-task synthetic holdout run, so it does not estimate stochastic variance or broader real-robot generalization.
