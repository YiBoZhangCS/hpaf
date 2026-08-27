# ProgPrompt-Compat Final Binary Interface

ARK Responses structured output was capability-tested before implementation. The endpoint accepted a strict JSON-schema string enum with values `True` and `False`.

The released state-check prompt is unchanged. Phase 8 constrains only the modern API transport, uses a three-token cap sufficient for the JSON string, decodes that transport, and then accepts only exact normalized `True` or `False`. There is no reasoning instruction, semantic fallback, second call, or substring inference.

- Development assertions: **152/152 (100.0%) strict binary**.
- Normalized output counts: `{'True': 131, 'False': 21}`.
- Method label: **ProgPrompt-Compat**.
- Interpretation: ProgPrompt adapted to the modern Responses backend with a binary-constrained assertion interface matching the original method's intended True/False state-check contract.

Gate (`>=95%`): **PASS**.
