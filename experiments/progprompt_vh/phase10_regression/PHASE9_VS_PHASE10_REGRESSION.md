# Phase-9 vs Phase-10 Unified Regression

Phase-9 values are the corrected partial-order offline rescore. Phase-10R values come from the new unified run with the frozen Phase-10 method.

| Method | Phase-9 corrected | Phase-10R unified rerun | Difference |
|---|---:|---:|---:|
| ProgPrompt-Compat | 18/40 | 22/40 | +4 |
| HPAF-Flat | 27/40 | 26/40 | -1 |
| HPAF-Full | 32/40 | 32/40 | +0 |

ARK does not expose a deterministic generation seed for these calls. Temperature is zero, but backend nondeterminism can remain; score differences must not be attributed wholly to code changes.

The existing Phase-10 12-task holdout remains separate independent validation evidence. It is not pooled with VH-40 into a 52-task score.
