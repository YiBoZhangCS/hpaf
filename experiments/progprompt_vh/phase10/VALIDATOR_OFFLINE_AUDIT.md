# Phase-10 Validator Offline Audit

This audit uses only the 40 TaskAgent outputs saved in Phase 9; LLM/API calls: **0**. Because those outputs predate Structured Atomic Task IR, each successfully parsed legacy object is passed through a validator-only compatibility projection. The projection moves close-only items to terminal constraints but does not invent dependency edges and is never executed.

## Result

| Measure | Count |
|---|---:|
| Saved TaskAgent outputs | 40 |
| Old validator rejected | 4 |
| New validator rejected | 0 |
| Old false rejection fixed | 4 |
| JSON parse-invalid | 0 |
| Schema-invalid after projection | 0 |
| Semantic-invalid after projection | 0 |

## Fixed false rejections

The old validator rejected a lexical prefix. The new validator accepts the same dominant semantic commitment structurally as `TRANSFER`; it never applies `if "move" in text: reject` logic.

| Task | Phase-9 legal transfer text | Old | New |
|---|---|---|---|
| `vh40_long_s0_01` | Move the creamybuns from the fridge into the cabinet. | reject | accept |
| `vh40_long_s1_05` | Move the toothbrush from the cabinet into the closet. | reject | accept |
| `vh40_long_s2_09` | Move the salmon from the fridge into the cabinet. | reject | accept |
| `vh40_long_s2_11` | Move the slippers from the cabinet to the bathroomcounter, leaving the barsoap stored in the cabinet. | reject | accept |

All four are Long-11 transfer cases (`s0_01`, `s1_05`, `s2_09`, and Long-11 item `s2_11`). They were implementation rejections, not navigation-only tasks.

## Validator boundary

The Phase-10 validator checks JSON/schema shape, the five allowed atomic types, scene-inventory grounding, non-empty semantic goals, dependency references, and DAG acyclicity. Navigation is rejected structurally because `NAVIGATION` is not an allowed type and because each allowed type carries a state/process commitment. Surface words such as *move*, *walk*, or *position* are not semantic classifiers.
