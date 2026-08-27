# HPAF × ProgPrompt VirtualHome benchmark

This experiment evaluates only HPAF's high-level planning organization in the
audited ProgPrompt VirtualHome setting. It does **not** evaluate or make claims
about RGB-D perception, Florence-2/GroundingDINO, geometric alignment, grasp
pose estimation, PiPER motion, or other real-robot components.

## Methods

- `ProgPrompt-Full`: released action import, object list, default three
  few-shots, inline comments, assertions, recovery semantics, and evaluator;
  only the legacy Completion client is adapted to Responses.
- `HPAF-Decomp-Static`: TaskAgent produces ordered semantic atomic tasks;
  ProgramAgent generates every atomic program from the initial symbolic state;
  programs are concatenated and then executed.
- `HPAF-Decomp-ClosedLoop`: TaskAgent decomposes once; each atomic ProgramAgent
  call receives the current graph state after the preceding atomic program,
  and planner-authored symbolic completion conditions gate continuation.

All methods use the same scene 0 cached initial graph, stable object inventory,
primitive action interpreter, evaluator, provider/model, temperature, and
600-token output budget. Method-specific prompts and call counts are the
experimental treatment and are fully recorded.

## Audited task set and metrics

The benchmark uses the released `test_unseen` order corresponding to the ten
tasks in paper Table II. `results/task_metadata.csv` records the ground-truth
action length and horizon (`Short` 0–5, `Medium` 6–10, `Long` 11–18).

The evaluator in `adapters/evaluator.py` preserves the released set formulas.
Its raw `PSR` is Goal Conditions Recall, so results retain the `PSR` field and
display the same value as `GCR`. `SR` is one iff every task-relevant condition
is satisfied. `Exec` is successful generated graph actions divided by attempted
generated graph actions.

## Environment

- conda environment: `hpaf-vh`, Python 3.9.23
- ProgPrompt: `56e65510747dff809c1b0bac9318508da9d9a2d4`
- VirtualHome: `f84ee28a75b23318ee1bf652862b1c993269cd06`
- official Unity 2.3.0 Linux executable
- one official README compatibility fix, saved in
  `adapters/virtualhome_f84ee28_compat.patch`

Phase 0 exercised ground truth through both headless Unity render and Evolving
Graph. A generated program later reproduced a headless Unity VideoPlayer
SIGSEGV. Consequently the formal comparison uses Unity reset/inventory sanity
plus Evolving Graph-only per-action execution for **all** methods. This is a
documented deviation and is not a full reproduction of the visual dual-backend
pipeline.

## LLM compatibility

The primary Codex backend passed the minimal Phase-1 call but repeatedly held
real ProgPrompt requests open for over twelve minutes. The formal comparison
therefore uses the configured fallback exclusively:

- provider: `ark`
- model: `doubao-seed-2-1-pro-260628`
- API: `responses.create`
- temperature: 0.0
- `thinking: {type: disabled}`
- max output tokens: 600
- total wall-clock deadline: 240 s per call

Thinking is disabled uniformly to reproduce non-reasoning Completion behavior;
otherwise the prompt consumed the entire output budget without a visible
message. The request shape follows Fire Volcano Engine's published Responses
example using [`thinking={'type':'disabled'}`](https://developer.volcengine.com/articles/7628897447645904939).
Responses lacks server-side Completion `stop` and
`frequency_penalty`, so `def` stop is applied client-side and the unavailable
frequency penalty remains recorded as compatibility metadata.

## Commands

From the repository root, with the `hpaf-vh` environment and API variables
available:

```bash
PYTHONPATH=. conda run -n hpaf-vh python experiments/progprompt_vh/scripts/run_phase0.py
PYTHONPATH=. conda run -n hpaf-vh python experiments/progprompt_vh/scripts/run_phase1.py --provider fallback
PYTHONPATH=. conda run -n hpaf-vh python experiments/progprompt_vh/scripts/summarize.py
```

The canonical runner is `experiments/progprompt_vh/runner.py`; it requires an
explicit task and method list and skips existing task/method pairs. The first
formal 10×3 run has already completed, so do not delete or rerun
`results/raw_runs.jsonl` as part of normal result inspection.

## Results

The first one-sample-per-pair run is summarized in
`results/RESULTS_TABLES.md`. Raw prompts, raw outputs, programs, traces, usage,
and errors are in `results/raw_runs.jsonl` and the per-pair `results/runs/`
files. See `EXPERIMENT_STATUS.md` for findings and all compatibility caveats.

ProgPrompt and VirtualHome remain under their upstream licenses and attribution
in `third_party/`; no NVIDIA source is copied into the HPAF package.
