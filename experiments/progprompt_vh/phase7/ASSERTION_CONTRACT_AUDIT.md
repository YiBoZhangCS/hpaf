# Phase-7 Assertion Contract Audit

All 152 immutable Phase-6 assertion prompts were replayed before confirmatory execution using the released-compatible two-token cap, unchanged prompt, no extra reasoning instruction, and no fallback call.

- Strict binary: **108/152 (71.1%)**.
- Non-binary: **44/152**.
- Output counts: `{'False': 28, "Let's": 44, 'True': 80}`.
- Parser unit cases: whitespace/newline/case variants normalize; explanatory text remains invalid.
- These compatibility calls are audit overhead and are excluded from benchmark cost.
