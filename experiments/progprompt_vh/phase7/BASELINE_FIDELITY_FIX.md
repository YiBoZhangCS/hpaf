# Phase-7 Baseline Fidelity Fix

## Official behavior

The pinned ProgPrompt release (`56e65510747dff809c1b0bac9318508da9d9a2d4`) builds the state-check prompt from the fixed state-check examples, filters the current local state to assertion-mentioned objects, and calls the legacy Completion API with `max_tokens=2` and `stop=["\n"]`. It strips the returned text. The execution loop then checks the returned text for `True` or `False`; a `True` result skips only the immediately adjacent `else:` recovery line, while a `False` result executes that recovery line. The assertion is a local precondition check, not whole-task failure or full replanning.

## Old Phase-6 behavior

Phase 6 used the same assertion prompt and adjacent recovery structure but sent the Responses API request with `max_output_tokens=600`. It parsed with the substring test `'true' in output_text.lower()`, so 45 of 152 saved outputs began with explanatory text and could alter recovery control flow. The adapter also applied the newline stop locally because Responses did not receive the legacy Completion parameters.

## Phase-7 correction

Phase 7 uses an isolated `Phase7GraphProgramExecutor` with the same prompt construction, no extra reasoning instruction, no fallback call, and a two-token output cap (`max_tokens=2`, mapped to Responses `max_output_tokens=2`). It normalizes only surrounding whitespace and case, making `True`, `True\n`, `False`, and `False\n` equivalent to the released parser's intended values. Non-binary output is not assigned a truth value and never triggers an inferred semantic fallback. The adjacent `else:` branch remains the only recovery scope.

The correction changes the baseline contract only. It does not change the released few-shot examples, action prompt, assertion text, evaluator, task set, or HPAF prompts.

