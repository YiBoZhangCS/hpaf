# Phase-10 Final Report

## Final HPAF definition

Atomic task: one dominant, independently verifiable semantic state/process commitment around a focal object.

Complex task: multiple semantic checkpoints or predecessor-dependent later checkpoints.

Dependency: explicit acyclic `depends_on` edges; stable topological ready-node execution.

Terminal constraint: final required state/relation, not an independent high-level atomic.

Execution: `P -> (A -> I)^k -> V`, followed by state refresh before the next ready atomic.

## Phase-9 offline rescore

| Method | Original | Partial-order rescore |
|---|---:|---:|
| ProgPrompt-Compat | 18/40 | 18/40 |
| HPAF-Flat | 27/40 | 27/40 |
| HPAF-Full | 28/40 | 32/40 |

Four Full traces changed because all required semantic events and final conditions were present while only terminal close/reference order differed.

## Validator audit

Old false rejection: 4/40. New rejection after legacy compatibility projection: 0/40. All four fixed cases were legal `Move object from A to B` transfers.

## Development regression

See `DEVELOPMENT_REGRESSION.md`; adopted frozen development iteration is recorded in `PHASE10_METHOD_FREEZE.json`. Relative to the Phase-9 Full baseline, iteration 2 improved partial-order Long-11 from 7/11 to 9/11, while persistent-state changed from 19/20 to 17/20 and generic trace/process from 6/9 to 5/9.

## Final holdout

N=12; categories 3/3/3/3; scenes 4/4/4; reference feasible/evaluator-valid 12/12.

## Final result

| Method | Success/12 | SR | Macro Exec | Calls/task | Tokens/task | GCR (supp.) |
|---|---:|---:|---:|---:|---:|---:|
| ProgPrompt-Compat | 0/12 | 0.0% | 0.877 | 16.92 | 9456.8 | 0.440 |
| HPAF-Flat | 6/12 | 50.0% | 0.851 | 2.00 | 3217.3 | 0.715 |
| HPAF-Full | 10/12 | 83.3% | 0.950 | 6.33 | 8789.1 | 0.932 |

## Complexity scaling

| Complexity | Method | N | Success | SR | Macro Exec |
|---|---|---:|---:|---:|---:|
| 2 atomic | ProgPrompt-Compat | 9 | 0 | 0.0% | 0.860 |
| 2 atomic | HPAF-Flat | 9 | 5 | 55.6% | 0.871 |
| 2 atomic | HPAF-Full | 9 | 7 | 77.8% | 0.940 |
| 3 atomic | ProgPrompt-Compat | 3 | 0 | 0.0% | 0.930 |
| 3 atomic | HPAF-Flat | 3 | 1 | 33.3% | 0.792 |
| 3 atomic | HPAF-Full | 3 | 3 | 100.0% | 0.982 |
| >=4 atomic | ProgPrompt-Compat | 0 | 0 | — | — |
| >=4 atomic | HPAF-Flat | 0 | 0 | — | — |
| >=4 atomic | HPAF-Full | 0 | 0 | — | — |
| D=2 | ProgPrompt-Compat | 9 | 0 | 0.0% | 0.860 |
| D=2 | HPAF-Flat | 9 | 5 | 55.6% | 0.871 |
| D=2 | HPAF-Full | 9 | 7 | 77.8% | 0.940 |
| D=3 | ProgPrompt-Compat | 3 | 0 | 0.0% | 0.930 |
| D=3 | HPAF-Flat | 3 | 1 | 33.3% | 0.792 |
| D=3 | HPAF-Full | 3 | 3 | 100.0% | 0.982 |
| D>=4 | ProgPrompt-Compat | 0 | 0 | — | — |
| D>=4 | HPAF-Flat | 0 | 0 | — | — |
| D>=4 | HPAF-Full | 0 | 0 | — | — |

## PPT example

Task: Heat salmon in the microwave, then place it on the coffeetable.

`A1 Heat salmon [PROCESS] -> A2 Place salmon on table [TRANSFER]`

Terminal: microwave OFF. A1 executes `Perceive -> Align salmon -> Grab -> Align microwave -> Load / Run cycle -> Verify`; then state refresh and A2.

## Main conclusion

In the single pre-frozen 12-task causal holdout, HPAF-Full completed 10/12, HPAF-Flat 6/12, and ProgPrompt-Compat 0/12. This supports only the observed one-run comparison under the frozen semantic-DAG evaluator.

## Remaining limitation

The largest limitation is that the final evidence is one deterministic 12-task synthetic holdout run, so it does not estimate stochastic variance or broader real-robot generalization.
