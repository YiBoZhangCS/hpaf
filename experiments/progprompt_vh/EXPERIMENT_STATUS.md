# Experiment status

Last updated: 2026-08-25 (Asia/Shanghai)

## Environment

- Python: 3.9.23 in independent conda env `hpaf-vh`
- ProgPrompt commit: `56e65510747dff809c1b0bac9318508da9d9a2d4`
- VirtualHome commit: `f84ee28a75b23318ee1bf652862b1c993269cd06`
- Unity: official VirtualHome 2.3.0 Linux executable, SHA-256
  `ac23adb21c4038de6068b4d3234a21ae13dc468330d4ee52dd292dab2c126d51`
- Backend: Phase 0 used Unity reset/render plus Evolving Graph state execution.
  Formal generated-program comparison uses Unity reset/inventory plus Evolving
  Graph-only action execution (documented deviation; same for all methods).
- Compatibility patch: official README fix applied to
  `JoinedExecutor.execute(..., *args)` at pinned source line 67. Patch remains
  visible through `git -C third_party/virtualhome diff`.
- Dependency compatibility: VirtualHome's declared `networkx==2.3` and old
  OpenCV wheel do not support this Python environment. The isolated benchmark
  uses NetworkX 2.8.8, NumPy 1.26.4, and headless OpenCV 4.11; PiPER/HPAF robot
  dependencies were not modified.

## Completed phases

### Phase 0 — passed

The ground-truth `watch tv` program executed 3/3 actions in both Unity and
Evolving Graph. The released evaluator formula produced:

| SR | GCR / raw PSR | Exec |
|---:|---:|---:|
| 1.0 | 1.0 | 1.0 |

Artifacts:

- `results/phase0_ground_truth_smoke.json`
- `results/phase0_ground_truth_final_state.json`
- `results/environment_initial_state.json`
- `results/task_metadata.csv`

### Phase 1 — passed

- provider: `codex`
- model: `gpt-5.6-sol`
- temperature: 0.0
- API interface: modern `responses.create`
- smoke output: `HPAF_VH_OK`
- measured usage: 4,396 prompt tokens, 10 completion tokens
- measured latency: 17.463 s

The unexpectedly high input-token count for the tiny request is the value
reported by the configured backend and is retained rather than estimated away.
No ARK fallback was used.

Subsequent integration smoke exposed a backend-stability blocker: two real
ProgPrompt requests to the primary Codex endpoint held an open connection for
more than 12 minutes without completing. A repeated tiny Codex health call did
pass in 42.572 s, while the configured ARK fallback returned the same exact
health string in 2.469 s (256-token budget). Therefore Phase 2 onward uses ARK
exclusively for every method/task pair; no formal comparison mixes providers.

Compatibility deviation from legacy ProgPrompt generation: Responses has no
server-side `stop` or `frequency_penalty`; generated baseline text will be
client-truncated at `def`, and the unavailable frequency penalty will be
recorded in run metadata.

The shared modern client also enforces a 240 s total wall-clock deadline per
call (in addition to its 180 s socket timeout). This was added after a smoke
state-check request kept its connection open without returning for more than
12 minutes. Timeout attempts are retained as metered call records; the same
deadline applies to all three methods.

ARK thinking is explicitly disabled for all methods with
`thinking: {type: disabled}`. Without that option, both 600 and 4,096 output
budgets were consumed by reasoning and the exact ProgPrompt completion prompt
returned no message. Disabling thinking restores the non-reasoning semantics
of the legacy Completion baseline; all methods share the released 600-token
output budget. Legacy two-token state checks receive 16 visible output tokens
to expose the requested Boolean answer. The actual usage and request option are
stored in every call record.

Closed-loop verification uses planner-authored graph conditions only. For a
`CLOSE` condition on a carried object, the verifier accepts the symbolic
two-edge proof `character HOLDS object` plus `character CLOSE target`, because
Evolving Graph does not materialize an object-to-target CLOSE edge while the
object is held. The derivation is written into the per-atomic verification
trace and does not consult task ground truth.

During the first Phase-4 process, two wrapper defects were found after 27
complete records: evaluator-only `HEATED` augmentation was applied before
rebuilding the native executor (unlike the released ordering), and planner
condition `HOLDS` was compared literally against graph relations
`HOLDS_RH/HOLDS_LH`. The former raised on the last task; the latter invalidated
the ClosedLoop records through false verification failures. All affected rows
are preserved in `results/diagnostics/phase4_pre_verifier_fix_invalid_runs.jsonl`.
Valid ProgPrompt/Static rows were retained, all invalid ClosedLoop rows were
quarantined, and only those pairs are rerun after the method-wide fix. This is
an implementation repair, not a repeat or favorable-run selection.

### Generated-program Unity deviation

The first adapted Short smoke generated a valid program and reached SR=1/GCR=1
in Evolving Graph. Its recovery branch selected duplicate `tv (264)`. The
headless Unity NullGfxDevice attempted to activate that TV's VideoPlayer and
terminated with SIGSEGV because video shaders were unavailable. The crash and
stack trace are retained in local `port_8091.txt`; it occurred after Evolving
Graph successfully applied the action. To avoid counting a graphics/runtime
crash as planning failure, all formal methods disable per-action Unity render
and use the same Evolving Graph executor. Unity is still started and reset for
environment sanity/inventory on every run. This means the comparison does not
fully reproduce the original visual dual-backend runtime.

### Phase 2/3 — passed

The final integration smoke (`results/smoke_v8`) completed one Short and one
Long task through all three methods. Every pair produced generation, execution,
evaluation, raw prompts/outputs, trace, token usage, latency, and typed errors.
Task success was not required for a pipeline pass.

### Phase 4 — complete

The audited ten-task `test_unseen` set completed with exactly 30 unique valid
task/method records: ten per method and three per task. All use provider `ark`,
model `doubao-seed-2-1-pro-260628`, scene 0, temperature 0.0, and initial graph
SHA-256 `6ebd404fdbb03bd2dcaaf5ad6566606ceeacae3bf5f6829d02a6716cbcd2afd8`.

| Method | SR | GCR | Exec | Avg LLM Calls | Avg Tokens |
|---|---:|---:|---:|---:|---:|
| ProgPrompt-Full | 0.500 | 0.726 | 0.711 | 10.20 | 5,199.9 |
| HPAF-Decomp-Static | 0.300 | 0.616 | 0.865 | 5.50 | 7,256.2 |
| HPAF-Decomp-ClosedLoop | 0.100 | 0.305 | 0.831 | 3.60 | 4,406.0 |

Horizon SR:

| Horizon | ProgPrompt-Full | HPAF-Decomp-Static | HPAF-Decomp-ClosedLoop |
|---|---:|---:|---:|
| Short (3 tasks) | 0.333 | 0.000 | 0.333 |
| Medium (5 tasks) | 0.600 | 0.600 | 0.000 |
| Long (2 tasks) | 0.500 | 0.000 | 0.000 |

## Findings

1. This first run does not support RQ1 or RQ2. ProgPrompt has the highest
   overall SR/GCR and is the only method with Long successes.
2. Static decomposition reaches virtually the same Medium SR/GCR as ProgPrompt
   (`0.600/0.853` versus `0.600/0.852`) and has higher overall Exec (`0.865`
   versus `0.711`), but those executable actions do not translate into higher
   overall goal completion. Static also costs more tokens on average.
3. ClosedLoop has high action executability but often stops at a failed atomic
   boundary, yielding only 3.6 calls and 4,406 tokens on average. Its low cost is
   therefore partly early termination, not an efficiency win. Planner-authored
   decomposition/conditions and accumulated grounding/precondition errors are
   the immediate issues to study before expanding the benchmark.

## Anomalies and potential unfairness

1. Formal action execution is graph-only after Unity reset/inventory sanity due
   the reproducible headless Unity VideoPlayer SIGSEGV. This is shared across
   methods but deviates from the original visual dual-backend runtime.
2. The primary Codex endpoint was unstable on real prompts, so the formal run
   uses ARK fallback exclusively. Thinking is disabled, and a minimal
   completion-style instruction bridges the legacy code prompt to Responses.
3. There is only one sample per pair; Long contains only two tasks. Temperature
   0 did not make the hosted backend perfectly deterministic across smoke runs,
   so no statistical significance or repeatability claim is made.
4. ClosedLoop completion conditions are planner-authored rather than GT-derived.
   They avoid future-answer leakage but are imperfect: unsupported condition
   shapes fall back to executable-boundary evidence and false conditions stop
   the remaining atomic sequence.

## Primary artifacts

- `BASELINE_AUDIT.md`
- `README.md`
- `results/raw_runs.jsonl`
- `results/task_results.csv`
- `results/summary_overall.csv`
- `results/summary_by_horizon.csv`
- `results/RESULTS_TABLES.md`
- `plots/sr_vs_task_horizon.{png,pdf}`
- `plots/gcr_vs_task_horizon.{png,pdf}`
- `plots/exec_vs_task_horizon.{png,pdf}`
- `plots/token_cost_vs_task_horizon.{png,pdf}`

## Stop condition

All requested first-stage artifacts are complete. No repeats, larger task set,
second benchmark, or real-robot experiment has been started.
