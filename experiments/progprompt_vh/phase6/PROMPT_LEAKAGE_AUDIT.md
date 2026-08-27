# Formal Prompt Leakage Audit

Scanned 292 actual formal API call records across all 60 runs.

## Results

| Prohibited information | Check | Result |
|---|---|---|
| Frozen semantic goal conditions/rationales | Exact same-task payload search over every prompt | PASS: 0 hits |
| GT program / grounded GT actions | Exact released grounded-action search and structural field-name search | PASS: 0 unexplained hits (175 execution-trace overlaps) |
| GT final graph / official goal set | Structural marker search plus manual prompt-schema inspection | PASS: 0 hits |
| Future atomic answers | 22 exact future-instruction comparisons in current-atomic calls | PASS: 0 hits |
| Method scores/outcomes | Score/evaluator field-name search | PASS: 0 hits |

The grounded-action overlaps occur only in verifier/repair prompts where the allowed current execution trace contains a method-executed action that happens to equal a released GT action. Each overlap is also present in that method's own stored trace; none appears in generation/TaskAgent prompts. This is execution-derived evidence, not GT provenance.

The HPAF templates contain negative safeguards such as `frozen goal predicates` and `do not ... future atomics`; these are policy text, not leaked goal values. Original task text remains visible to Full atomic calls by design, but no future TaskAgent-produced atomic object is inserted.

ProgPrompt receives only its released-style action/object prefix, three train examples, and task header during generation. Assertion calls receive the fixed state-check examples plus assertion-object-filtered local symbolic state. No final evaluator input is present.

## Separation conclusion

The online controller prompts are clean with respect to frozen evaluator answers. Final semantic conditions are consumed only by the offline deterministic scoring/replay path. Prompt leakage status: **PASS**.
