# Prompt Structure Audit

All structures below are verified against `llm_call_records[].prompt` and `.instructions` in the immutable formal raw logs, not inferred only from templates.

| Prompt | Input information | Explicitly absent | Output format | When called | Affects control flow |
|---|---|---|---|---|---|
| ProgPrompt generation | task, complete object-class inventory, 3 released train examples, shared action API | No symbolic state; no errors/trace; no semantic/GT data | DSL body: comments, actions, assertions, else recovery | Once per task | Yes: supplies entire program |
| ProgPrompt assertion | assertion text, assertion-object-filtered current local symbolic state, fixed 7-example state-check prompt | No task text, full graph, errors, semantic/GT data | Intended True/False text | At every generated assertion | Yes: skips or executes adjacent else branches |
| Flat ProgramAgent | whole task, initial symbolic observation, objects, shared action API, generic execution rules | No few-shot examples, trace/errors, semantic/GT data | Strict JSON with plan_brief/program | Once per task | Yes: supplies whole program |
| Flat verifier | whole task, post-execution symbolic observation, relevant objects, program, trace, typed errors | No few-shot examples or semantic/GT data | Strict done/reason/failure_stage/regeneration_hint JSON | Once after execution | No: recorded only; Flat has no retry |
| Full TaskAgent | whole task, object inventory, shared action names | No symbolic state, examples, trace/errors, semantic/GT data | Strict 1-6 atomic_tasks JSON | Once per task | Yes: defines ordered atomics |
| Full atomic ProgramAgent | whole task, current atomic, refreshed symbolic state, objects, shared action API | No few-shot or future atomic payload; no semantic/GT data | Strict JSON with plan_brief/program | Once per attempted atomic | Yes: supplies current program |
| Full atomic verifier | current atomic, post-state, relevant objects, whole-task context, program, trace, errors | No future atomic payload or semantic/GT data | Strict verifier JSON | After initial atomic execution | Yes: done=false invokes Retry-1 |
| Full repair ProgramAgent | current atomic, post-state, prior program, trace/errors, first verifier feedback, objects/API | No future atomic payload or semantic/GT data | Strict JSON with repair_brief/program | Only after done=false; 4 formal calls | Yes: supplies one local repair |
| Full post-repair verifier | current atomic, post-repair state, repair program/trace/errors, previous verifier | No future atomic payload or semantic/GT data | Strict verifier JSON | After each repair; 4 formal calls | Yes: failure stops future atomics |

## Backend request facts

All 292 formal calls used ARK `doubao-seed-2-1-pro-260628`, Responses API, temperature 0, thinking disabled, and `max_output_tokens=600`. ProgPrompt generation records `stop=['def']` and `frequency_penalty=0.15`, but the adapter does not send either to Responses: stop is applied locally after generation and frequency penalty is metadata only. ProgPrompt assertions similarly apply newline stop locally.

Additional baseline-fidelity differences are outside the request metadata. The frozen shared interface has 17 actions and omits four navigation variants advertised by the released ProgPrompt import (`turnright`, `turnleft`, `walkforward`, `walktowards`). Phase 6 also fixes same-class object grounding with executor `seed=0`; the released executor uses module-level `random.choice` without explicitly freezing an execution seed on the default-example path.

Most importantly, the released ProgPrompt assertion call uses `max_tokens=2`, while Phase 6 uses 600. The exact samples in this directory preserve the actual formal request and output.
