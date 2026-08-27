# Offline Case Studies

The concise findings below are backed by lossless chronological renderings containing every prompt, raw output, action, state delta, verification decision, and cost entry. Those timelines were reconstructed without LLM or Unity calls and require replayed metrics to match the raw records.

## Case A: collect four fruits

- ProgPrompt: SR=0, Exec=0.739130, calls=12, tokens=7233.
- HPAF-Flat: SR=0, Exec=1.000000, calls=2, tokens=3250.
- HPAF-Full: SR=1, Exec=1.000000, calls=9, tokens=9960.

ProgPrompt suffered repeated precondition/object-binding failures and finished with zero counted fruits in a dishbowl. Flat emitted all four placements and every action reported executable, but target resolution switched between two dishbowl instances: the deterministic evaluator found only bananas, peach, and plum inside any qualifying bowl relation set (3/4). Full decomposed into four fruit atomics, regenerated from refreshed state each time, consistently accumulated apple, bananas, peach, and plum, and all four atomic verifiers returned done=true. This single case supports decomposition/state refresh, but it is not enough to attribute the aggregate 20-point Flat-to-Full gap entirely to decomposition.

Complete evidence: `audits/case1_collect_4_fruits_full_timeline.md`.

## Case B: bring my book to the sofa (env1)

- ProgPrompt: SR=0, Exec=1.000000, calls=5, tokens=3534.
- HPAF-Flat: SR=1, Exec=1.000000, calls=2, tokens=1977.
- HPAF-Full: SR=1, Exec=1.000000, calls=3, tokens=2930.

ProgPrompt generated and successfully executed `putin('book', 'sofa')`, but the frozen semantic goal is `ON(book, sofa)`. The action choice therefore produced the wrong relation despite Exec=1.0. Flat and Full used `putback`, producing ON and succeeding. The same ProgPrompt failure repeats in env2, so this is an action-semantics issue rather than an assertion failure.

Complete evidence for env1 and env2: `audits/case2_book_to_sofa_full_timeline.md`.

## Case C: env1 microwave chicken

- ProgPrompt: SR=1, Exec=0.875000, calls=19, tokens=10585.
- HPAF-Flat: SR=0, Exec=0.800000, calls=2, tokens=2474.
- HPAF-Full: SR=0, Exec=0.625000, calls=5, tokens=6068.

Full's TaskAgent produced two atomics: put chicken into microwave, then turn on microwave. Its first ProgramAgent called `find(chicken)`, then `find(microwave)`, which moved grounding/proximity to the microwave before `grab(chicken)`; grab failed and putin then lacked a held chicken. The verifier correctly returned done=false. Retry-1 walked to and grabbed the chicken but immediately attempted putin without returning close to the microwave, so repair failed. Post-repair verification correctly remained false; the controller stopped before atomic 2. The failure is a two-location alignment/repair-planning error, not evaluator leakage or a false verifier decision.

Complete evidence: `audits/case3_microwave_chicken_full_timeline.md`.
