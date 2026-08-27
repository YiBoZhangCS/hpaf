# Phase-6 Resume-Oriented Final Benchmark Protocol

## Frozen benchmark

| Item | Value |
|---|---|
| Provider/model | ARK / `doubao-seed-2-1-pro-260628` |
| API/settings | Responses API; temperature 0; thinking disabled; max output 600 |
| Methods | ProgPrompt, HPAF-Flat, HPAF-Full |
| Final task set | 20 valid official held-out task-scene instances |
| Horizons | Short <=5; Medium 6-10; Long >=11 GT actions |
| Horizon counts | Short 6; Medium 10; Long 4 |
| Shared actions | Frozen Phase-5 17-action graph-compatible intersection |
| Execution | Per-task official/cached initial graph; Unity scene reset and class-inventory sanity; pinned Evolving Graph per-action execution |
| Online control | Method-specific LLM verification; never sees deterministic evaluator conditions |
| Final primary score | Shared deterministic frozen semantic evaluator |
| Supplementary score | Unmodified released/Phase-5 Official SR/GCR and Exec |
| Repetitions | One formal run per task-method pair |

## Frozen hashes

| Artifact | SHA-256 |
|---|---|
| `data/task_manifest.json` | `b030e18ebc284885389c9f3ac23bac4ed15110dd08db1d0bc297ab18d154e5b1` |
| `data/semantic_goals.json` | `26f96ce7f68d5424beca17341be3d7f12c045628b42526d3890193fa2a2a3704` |
| `data/long_horizon_manifest.json` | `464b7e4056717e5237f5f1f3b033289b6b79fb70f4de63dedd414b20e9ba8d8a` |
| Phase-5 shared action set | `e9d00393e42c1da2b945e3f300f84ba6bfb174c833925e706d802f1423f7c93c` |
| Audited source-data bundle | `f21ddd7f1d40ff75ab01270e0a862a8763be1c08dda63634b0a867f809360238` |
| Immutable Phase-5 formal raw runs | `b6d91c5da04e666ccf0eada583d70ad224d667fc99966ed49ebc1a6ffa8217a4` |

The manifest, semantic goals, long threshold, prompt examples, and action set are frozen before any Phase-6 method execution. Formal execution is additionally locked to the implementation hash recorded by the passing smoke marker.

## Dataset selection

The official release contains 35 held-out candidates across test_unseen, the ambiguous-goal split, env1, and env2. Tasks are excluded only when a stable method-independent semantic endpoint cannot be expressed by the shared interface/ontology. test_seen is excluded before candidacy because all ten task texts occur in train. Full decisions and reasons are stored in `DATASET_AUDIT.md` and `data/task_manifest.json`.

## Verification separation

ProgPrompt retains released assertion-level LLM state checks and recovery. HPAF-Flat calls the shared LLM verifier once after its whole-task program and does not retry. HPAF-Full pays for a fresh TaskAgent call, generates and executes each object-centric atomic against current state, calls the shared LLM verifier on post-execution symbolic observation, and permits one local repair plus one post-repair verification when `done=false`.

The online verifier receives only the current instruction, post-execution symbolic observation, relevant/available objects, and execution trace/error context. It never receives GT final states, official goal sets, frozen semantic conditions, or future atomics. Final benchmark success is recomputed independently from the frozen semantic goal file.

## Abstraction statement

VirtualHome substitutes simulator symbolic observation for real RGB-D perception while preserving HPAF's perception/grounding, alignment/precondition, interaction, and LLM verification organization. This benchmark does not claim to evaluate real visual perception.
