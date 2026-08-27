# ProgPrompt/VirtualHome baseline audit

This audit is based on the release source at
`third_party/progprompt-vh` (`56e65510747dff809c1b0bac9318508da9d9a2d4`),
the pinned VirtualHome source at
`f84ee28a75b23318ee1bf652862b1c993269cd06`, and the ICRA 2023 paper
PDF. It records code behavior rather than relying on the repository README.

## Evaluation task sets

The release contains two 10-task environment-0 splits.

`test_seen`:

1. wash the rug in washing machine
2. put all the cutlery in the sink
3. throw away the lime
4. put the wine glass in the kitchen cabinet
5. put the candle on the living room shelf
6. listen to radio
7. bring pillow to the sofa
8. open window
9. cut apple
10. wash mug

`test_unseen` (the paper Table II test-time tasks and the official runner's
default split):

1. watch tv (3 actions)
2. turn off light (3)
3. brush teeth (8)
4. throw away apple (8)
5. make toast (8)
6. eat chips on the sofa (5)
7. put salmon in the fridge (8)
8. wash the plate (18)
9. bring coffeepot and cupcake to the coffee table (8)
10. microwave salmon (11)

The first HPAF comparison therefore uses `test_unseen` only. The horizon
buckets reproduce Table II: Short 0--5, Medium 6--10, Long 11--18.

## Ground truth and positional pairing

- Ground-truth executable plans are the values in
  `data/test_unseen/*_annotated.json`; each JSONL row maps one task to ordered
  commented subgoals, and each subgoal contains explicit VirtualHome script
  lines with instance IDs.
- Ground-truth action length is the number of script lines after flattening all
  subgoal arrays. Empty annotated subgoals contribute zero actions. This
  reproduces every `|A|` value in Table II.
- Ground-truth final graphs are JSONL rows in
  `data/final_states/final_states_test_unseen.json`.
- The final-state rows contain no task identifier. `run_eval.py` gathers tasks
  with unsorted `os.listdir()` and then positionally zips task, generated final
  graph, and GT final graph. In the release checkout, the intended order is
  `file3_annotated.json` followed by `file1_annotated.json`, exactly the Table II
  order above. Sorting those filenames silently mis-pairs every target. The
  adapter fixes the intended paper order explicitly; it does not change any
  target graph.
- The initial environment-0 graph is not stored in ProgPrompt. The official
  runner obtains it from Unity after `reset(0)` and after adding Male2 in the
  kitchen. The benchmark caches that exact 444-node/957-edge graph for metadata
  and resets Unity for execution runs.

## Prompt construction

`run_eval.py::planner_executer` constructs one completion-style text prompt:

1. a Python import-like line listing the action functions;
2. `objects = [...]`, using unique class names from the Unity graph;
3. three default Pythonic examples from
   `data/pythonic_plans/train_complete_plan_set.json` (default
   `prompt_num_examples=3`):
   `put_the_wine_glass_in_the_kitchen_cabinet`, `throw_away_the_lime`, and
   `wash_mug`;
4. an incomplete `def <task_name>():` whose body is generated.

The official action import string includes `turnright`, `turnleft`,
`walkforward`, `walktowards`, `walk`, `run`, `grab`, `switchon`, `switchoff`,
`open`, `close`, `lookat`, `sit`, `standup`, `find`, `turnto`, `drink`,
`pointat`, `watch`, `putin`, and `putback`. The paper's shorter action-space
description is not the complete code-level import list.

The release queries legacy `openai.Completion.create` with 600 max tokens,
temperature 0, stop `def`, and frequency penalty 0.15. The benchmark preserves
the raw text prompt but uses a modern OpenAI-compatible Responses adapter. That
API lacks server-side stop/frequency-penalty fields: `def` is applied to the
returned text client-side and the missing frequency-penalty control is recorded
as a compatibility deviation. Full raw prompts and outputs are saved.

For deterministic cross-method scene input, the benchmark sorts the unique
object-class list instead of relying on Python set/hash order. All three methods
receive that same list.

## Comments, assertions, and recovery

- During execution, every line containing `#` starts a new subgoal dictionary
  entry; following non-comment lines are assigned to that comment. Comments do
  not execute and are the baseline's inline subgoal organization.
- An `assert(...)` line is not sent to VirtualHome. The runner extracts object
  words, filters the current agent-local symbolic state to those objects,
  appends the assertion to a fixed few-shot state-check prompt, and makes a
  second LLM request limited to two tokens.
- If that response contains `True`, the immediately represented `else:`
  recovery line is skipped. If it contains `False`, an `else:` prefix is
  stripped and its recovery action is executed. These state-check calls are
  part of ProgPrompt's LLM-call and token budget.
- The released interpreter stores one `last_assert` and has several brittle
  branches: it does not reset that variable after a recovery, uses `step+1`
  instead of assignment in several failures, and may read `found_id` before it
  is initialized. The adapter preserves the assertion/recovery semantics while
  turning these crash-only cases into typed trace errors shared by all methods.

## Execution backends

`utils_execute.run_execution` uses both backends, but not symmetrically:

- Unity supplies scene reset, character insertion, the initial graph, camera
  count/images, object inventory, and a `render_script` call for each action.
- Evolving Graph's `ScriptExecutor` determines whether the primitive succeeds
  and produces the graph used for the next step and for final metrics. A Unity
  render failure does not by itself determine `Exec` in the released code.
- `utils_aug_env.py` adds semantic `USED`, `HEATED`, and `WASHED` states for
  actions whose effects are not natively represented by the graph executor.

Phase 0 exercised both backends with the ground-truth `watch tv` plan. All
three Unity render calls and all three Evolving Graph calls succeeded; the
official metric formula returned SR=1, PSR/GCR=1, and Exec=1.

During the first generated-program smoke, however, the no-GPU Unity process
received `switchon <tv> (264)`, attempted to start a VideoPlayer without video
shaders under NullGfxDevice, and terminated with SIGSEGV. Evolving Graph had
already executed the same action successfully. Formal comparison runs
therefore use Unity for reset/inventory sanity and the cached Phase 0 initial
graph, but do not call Unity `render_script`; all three methods use the same
Evolving Graph action executor and released metric formulas. This is a
documented deviation from the full original dual-backend runtime, not a claim
of exact visual-simulator reproduction.

## Metric definitions in code

For each graph the evaluator collapses instance IDs to class names and forms
sets of `class relation class` and `class state` strings.

- Task-relevant goal conditions are GT-final conditions absent from the initial
  graph.
- `PSR = 1 - missing_task_goal_conditions / total_task_goal_conditions`.
- `SR = 1` exactly when `PSR == 1.0`; overall SR is the fraction of such tasks.
- `Precision` measures preservation of GT conditions that were already present
  initially.
- `Exec = successfully_executed_generated_primitives / attempted_generated_primitives`.

The paper defines GCR with the same missing-over-task-goal set difference used
by code field `PSR`. Consequently raw artifacts retain `PSR` and displays map
the identical value to `GCR`. The official evaluator has no guard for a
zero-goal or zero-attempt denominator; the audited 10 tasks all have nonzero
goal counts.

## Additional release issues relevant to reproducibility

- The non-environment-0 branch writes to `log_file` before opening it.
- `argparse type=bool` does not parse CLI false values reliably.
- The environment object list comes from `list(set(...))` and is not stable
  across Python hash seeds.
- Generated-plan execution randomly selects among duplicate class instances;
  the benchmark fixes random seed 0 and saves each compiled instance ID.
- Goal relations are class-collapsed, so two distinct instances with the same
  class may become indistinguishable in the metric sets.
