# Phase-5 Action-Space Audit

Phase 5 freezes one primitive API for all three methods. It is the exact intersection of the released ProgPrompt import, the pinned VirtualHome Evolving Graph `Action` enum, and `ScriptExecutor._action_executors`.

## Source comparison

- ProgPrompt official import (21): `turnright, turnleft, walkforward, walktowards, walk, run, grab, switchon, switchoff, open, close, lookat, sit, standup, find, turnto, drink, pointat, watch, putin, putback`
- Evolving Graph enum (45): `close, cut, drink, drop, eat, find, grab, greet, lie, lookat, lookat_long, lookat_medium, lookat_short, move, open, plugin, plugout, pointat, pour, pull, push, putback, putin, putobjback, putoff, puton, read, release, rinse, run, scrub, sit, sleep, squeeze, standup, switchoff, switchon, touch, turnto, type, wakeup, walk, wash, watch, wipe`
- Evolving Graph dispatch (42): `close, cut, drink, drop, eat, find, grab, greet, lie, lookat, move, open, plugin, plugout, pointat, pour, pull, push, putback, putin, putobjback, putoff, puton, read, release, rinse, run, scrub, sit, sleep, squeeze, standup, switchoff, switchon, touch, turnto, type, wakeup, walk, wash, watch, wipe`
- Frozen intersection (17): `close, drink, find, grab, lookat, open, pointat, putback, putin, run, sit, standup, switchoff, switchon, turnto, walk, watch`

Official-import actions rejected by the graph executor: `turnleft, turnright, walkforward, walktowards`. Graph-only actions withheld from HPAF for baseline fairness: `cut, drop, eat, greet, lie, move, plugin, plugout, pour, pull, push, putobjback, putoff, puton, read, release, rinse, scrub, sleep, squeeze, touch, type, wakeup, wash, wipe`.

## Phase-4 observed violations

| Action | Affected Phase-4 task/method records |
|---|---|
| `puton` | brush teeth / HPAF-Decomp-Static |
| `use` | brush teeth / HPAF-Decomp-Static |
| `walktowards` | brush teeth / HPAF-Decomp-Static; eat chips on the sofa / HPAF-Decomp-ClosedLoop; make toast / HPAF-Decomp-Static; put salmon in the fridge / HPAF-Decomp-ClosedLoop; wash the plate / HPAF-Decomp-Static |
| `wash` | wash the plate / HPAF-Decomp-Static |

The `else:` recovery parsing failures are not primitive-action violations and are reported separately in the failure audit.

## Representative parser/dispatch check

Static source inspection is decisive at this pinned commit: an action must both parse to an `Action` member and have a dispatch entry. The intersection therefore excludes `turnright`, `turnleft`, `walkforward`, and `walktowards`; Phase-4 traces independently confirm `WALKTOWARDS` reaches `UnknownExecutor`.
No planning API was called for this audit.

## Frozen artifact

- File: `experiments/progprompt_vh/phase5/data/graph_supported_actions.json`
- SHA-256: `e9d00393e42c1da2b945e3f300f84ba6bfb174c833925e706d802f1423f7c93c`
