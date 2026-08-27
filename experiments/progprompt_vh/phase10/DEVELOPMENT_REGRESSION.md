# Phase-10 Development Regression

VH-40 is development/regression only in Phase 10 because all prior results were observed. At most two complete HPAF-Full iterations were permitted.

| Iteration | Success/40 | SR | Macro Exec | IR parse | Validator reject | Mean atomics | Mean D | Mean terminals | Atomic verify | Retry/task | Early stop |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 30/40 | 75.0% | 0.910 | 100.0% | 5.0% | 1.48 | 1.32 | 0.33 | 88.1% | 0.25 | 22.5% |
| 2 | 31/40 | 77.5% | 0.909 | 100.0% | 0.0% | 1.32 | 1.32 | 0.33 | 68.6% | 0.53 | 40.0% |

Adopted iteration: **2**. Persistent-state regression: 17/20; generic trace/process regression: 5/9; Long-11 under partial-order semantics: 9/11.

For context, the Phase-9 Full baseline on the same groups was 19/20 persistent-state, 6/9 generic trace/process, and 7/11 Long-11 after the Phase-10 partial-order rescore. Thus iteration 2 removed validator rejection and improved Long-11 by 2 tasks, while the persistent and generic process groups were lower by 2 and 1 tasks respectively; the limited development protocol did not permit a third iteration.

The final holdout was generated only after the adopted method, prompt, and evaluator hashes were frozen.
