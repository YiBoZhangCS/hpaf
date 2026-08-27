# Phase-6 Verification Protocol

## Separation of roles

Online verification is part of a method's controller. It may decide whether to
take a recovery branch, continue to the next atomic, or invoke Retry-1. Final
benchmark evaluation is method-independent and never consumes the online
verifier's answer.

| Method | Online control-time verification | Effect |
|---|---|---|
| ProgPrompt | Released assertion text + current local symbolic state -> shared LLM True/False | Skip or execute the immediately associated `else:` recovery branch |
| HPAF-Flat | Whole task + post-execution symbolic observation + trace/errors -> shared JSON LLM verifier | Recorded once; no whole-task retry |
| HPAF-Full | Current atomic instruction + post-execution symbolic observation + trace/errors -> shared JSON LLM verifier | `done=true` continues; `done=false` invokes one local repair and one post-repair verification |

The HPAF verifier schema is:

```json
{
  "done": true,
  "reason": "short explanation",
  "failure_stage": "perception|alignment|interaction|verification|none",
  "regeneration_hint": "short repair suggestion"
}
```

Only `done` controls continuation or repair. Program executability and the
deterministic evaluator are not online gates.

## Allowed verifier evidence

- Current whole task or current atomic instruction.
- Current post-execution symbolic observation.
- Relevant object classes.
- Current program, action trace, and typed execution errors.
- For post-repair verification, the previous verifier result.

The verifier never receives the frozen semantic condition, GT program, GT final
graph, official goal set, future atomic tasks, or any method score. The frozen
semantic-goal file is loaded only after method execution when `run_one` computes
the final benchmark record.

## Observation abstraction

The observation describes character room/state/held objects, local graph object
states, and one-hop INSIDE/ON relations attached to nearby objects. Released
HEATED/WASHED augmentation states are included when causally produced. This is
a symbolic surrogate for HPAF's post-execution RGB/RGB-D observation, not a
measurement of real visual perception.

## Cost accounting

Every API call is tagged before aggregation:

- ProgPrompt: `whole_program_generation`, `assertion_verification`.
- HPAF-Flat: `flat_program_agent`, `flat_verifier`.
- HPAF-Full: `task_agent`, `atomic_program_agent`, `atomic_verifier`,
  `repair_program_agent`, `post_repair_verifier`.

Broad `generation`, `verification`, and `repair` counts/tokens are computed
from these tags, while the complete per-call records are retained in raw runs.

