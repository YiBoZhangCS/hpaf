# ProgPrompt Baseline Fidelity Fix

## Pinned source

The released source was read from `third_party/progprompt-vh` at commit
`56e65510747dff809c1b0bac9318508da9d9a2d4`. The relevant implementation is
`scripts/utils_execute.py`.

## Official behavior

- Assertion prompts are built from the current symbolic state filtered to the
  objects mentioned by the assertion.
- The released Completion API requests `max_tokens=2` and `stop=["\\n"]`.
- The released parser checks the returned text for the literal `True` or `False`
  and uses only the adjacent `else` branch for recovery. A false assertion does
  not fail the whole task and does not trigger replanning.
- There is no second assertion repair call and no semantic truth fallback.
- The released planner generates one whole program after the three supplied
  few-shot examples.

## Phase-6 bug

Phase 6 called the assertion endpoint with a 600-token cap and used a substring
parser. Verbose outputs such as `Let's analyze...` could therefore be interpreted
as false and alter recovery control flow. This produced non-binary assertion
outputs in the saved audit.

## Phase-9 correction

Phase 9 keeps the released prompt, whole-program generation, three examples,
adjacent-else recovery, and no-replanning semantics. Assertions are transported
through an ARK Responses API strict string enum with only `True` and `False`, and
the executor normalizes surrounding whitespace before applying the released
boolean parser. No reasoning prompt, semantic fallback, second repair call, or
method-specific truth inference is added.

The Responses compatibility wrapper uses `max_output_tokens=3` at the wire level
because the structured enum response includes transport syntax; the accepted
decoded assertion payload remains a single `True`/`False` enum and is audited as
the released two-token binary contract. This transport distinction is recorded
explicitly rather than hidden.

Formal audit: `419/419` assertion outputs were strict binary (`100.0%`), with
normalized values only `True` and `False`. Adjacent `else` behavior is preserved
by `Phase7GraphProgramExecutor` and inherited by the Phase-8 compatibility
executor.

