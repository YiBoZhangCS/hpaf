# Independent Phase-6 Dataset Audit

Evidence basis: official release annotation files, the released Pythonic prompt library, released final-state files, and the frozen manifest. No number from `DATASET_AUDIT.md` is used as an input.

## Release inventory

| Split/artifact | Rows | Unique task texts | Role |
|---|---:|---:|---|
| `train` | 35 | 34 | Scene-0 example/train library; not an LLM fine-tuning corpus in this code release |
| `test_seen` | 10 | 10 | Derived seen-task evaluation slice; every text already occurs in train |
| `test_unseen` | 10 | 10 | Scene-0 task-unseen evaluation |
| `test_unseen_ambiguous_goals` | 5 | 5 | Scene-0 ambiguous/open-goal evaluation |
| `env1` | 10 | 10 | Held-out scene 1 |
| `env2` | 10 | 10 | Held-out scene 2 |
| `all_plans_env0` | 50 | n/a | Source inventory of 50 scene-0 plan texts, not an extra split |

The primary inventory is **70 task-scene instances**: 35 train + 10 test_unseen + 5 ambiguous + 10 env1 + 10 env2. It is not 80 because the 10 `test_seen` rows are a derived slice of train task instances/texts rather than ten new primary instances. The 50 scene-0 primary rows are also exactly the 50 entries represented in `all_plans_env0`.

## Train and seen relationships

`train` exists to provide annotated plans and the in-context example library. The released runner loads examples from `train_complete_plan_set.json` into the prompt; it does not fine-tune model weights. Train has 35 rows but 34 unique texts because `read book under table lamp` is duplicated. The Pythonic library has 34 keys.

The three Phase-6/default few-shot examples are:

- `put the wine glass in the kitchen cabinet`
- `throw away the lime`
- `wash mug`

All ten exact `test_seen` task texts occur in train. `test_seen` therefore tests seen task language in scene 0; it is excluded before held-out candidacy.

Complete `test_seen` task-text list:

- `listen to radio`
- `bring pillow to the sofa`
- `open window`
- `cut apple`
- `wash mug`
- `wash the rug in washing machine`
- `put all the cutlery in the sink`
- `throw away the lime`
- `put the wine glass in the kitchen cabinet`
- `put the candle on the living room shelf`

Exact env task texts also present in train:

- env1 (2): `bring my book to the sofa`, `put the soap in the bathroomcabinet`
- env2 (3): `bring my book to the sofa`, `open the curtains`, `put the soap in the bathroomcabinet`

`held-out` must therefore be qualified. A held-out task-scene instance is absent from the prompt-example/evaluation instance set. `task-unseen` means its exact text is absent from train. `environment-held-out` means the scene is env1/env2; its task text may still be train-seen. Phase 6 contains both task-unseen scene-0 instances and environment-held-out instances, so it should not call all 20 task-unseen.

## Candidate and final selection

The 35 held-out candidates are the direct union of test_unseen (10), ambiguous (5), env1 (10), and env2 (10). Fifteen were conservatively excluded because the current persistent final-graph protocol cannot represent the requested outcome reliably, leaving **20 task-scene instances and 18 unique task texts**.

## Final 20 tasks

| Split | Task text | Scene | GT actions | Horizon | Frozen semantic goal | Include reason |
|---|---|---:|---:|---|---|---|
| `test_unseen` | turn off light | 0 | 3 | Short | `STATE(lightswitch, OFF)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `test_unseen` | throw away apple | 0 | 8 | Medium | `INSIDE(apple, garbagecan)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `test_unseen` | put salmon in the fridge | 0 | 8 | Medium | `INSIDE(salmon, fridge)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `test_unseen` | wash the plate | 0 | 18 | Long | `STATE(plate, WASHED)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `test_unseen` | bring coffeepot and cupcake to the coffee table | 0 | 8 | Medium | `ON(coffeepot, coffeetable); ON(cupcake, coffeetable)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `test_unseen` | microwave salmon | 0 | 11 | Long | `STATE(salmon, HEATED)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `test_unseen_ambiguous_goals` | collect 4 fruits such as apple, banana, etc in the dishbowl | 0 | 14 | Long | `COUNT_DISTINCT_INSTANCES(apple/bananas/lime/peach/plum INSIDE dishbowl) >= 4` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `env1` | turn off tablelamp | 1 | 2 | Short | `STATE(tablelamp, OFF)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `env1` | put the soap in the bathroomcabinet | 1 | 6 | Medium | `INSIDE(barsoap, bathroomcabinet)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `env1` | throw away plum | 1 | 6 | Medium | `INSIDE(plum, garbagecan)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `env1` | bring my book to the sofa | 1 | 4 | Short | `ON(book, sofa)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `env1` | put chicken in the fridge | 1 | 6 | Medium | `INSIDE(chicken, fridge)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `env1` | bring coffeepot and peach to the coffee table | 1 | 7 | Medium | `ON(coffeepot, coffeetable); ON(peach, coffeetable)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `env1` | microwave chicken | 1 | 13 | Long | `STATE(chicken, HEATED)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `env2` | open the curtains | 2 | 2 | Short | `STATE(curtains, OPEN)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `env2` | turn on tv | 2 | 2 | Short | `STATE(tv, ON)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `env2` | put the soap in the bathroomcabinet | 2 | 6 | Medium | `INSIDE(barsoap, bathroomcabinet)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `env2` | throw away bananas | 2 | 6 | Medium | `INSIDE(bananas, garbagecan)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `env2` | bring my book to the sofa | 2 | 4 | Short | `ON(book, sofa)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |
| `env2` | put milk in the fridge | 2 | 6 | Medium | `INSIDE(milk, fridge)` | Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API. |

## Horizon and HPAF complexity

Independent flattening of the released GT programs gives Short=6, Medium=10, Long=4. Long N=4 is a property of the selected 20 tasks, not a missing runner branch.

| Task | GT primitive actions | GT horizon | Full generated atomics | Unique manipulated objects |
|---|---:|---|---:|---|
| `test_unseen::turn_off_light` | 3 | Short | 1 | 1 (lightswitch) |
| `test_unseen::throw_away_apple` | 8 | Medium | 1 | 1 (apple) |
| `test_unseen::put_salmon_in_the_fridge` | 8 | Medium | 1 | 1 (salmon) |
| `test_unseen::wash_the_plate` | 18 | Long | 1 | 1 (plate) |
| `test_unseen::bring_coffeepot_and_cupcake_to_the_coffee_table` | 8 | Medium | 2 | 2 (coffeepot, cupcake) |
| `test_unseen::microwave_salmon` | 11 | Long | 2 | 2 (microwave, salmon) |
| `test_unseen_ambiguous_goals::collect_4_fruits_such_as_apple,_banana,_etc_in_the_dishbowl` | 14 | Long | 4 | 4 (apple, bananas, peach, plum) |
| `env1::turn_off_tablelamp` | 2 | Short | 1 | 1 (tablelamp) |
| `env1::put_the_soap_in_the_bathroomcabinet` | 6 | Medium | 1 | 1 (barsoap) |
| `env1::throw_away_plum` | 6 | Medium | 1 | 1 (plum) |
| `env1::bring_my_book_to_the_sofa` | 4 | Short | 1 | 1 (book) |
| `env1::put_chicken_in_the_fridge` | 6 | Medium | 1 | 1 (chicken) |
| `env1::bring_coffeepot_and_peach_to_the_coffee_table` | 7 | Medium | 2 | 2 (coffeepot, peach) |
| `env1::microwave_chicken` | 13 | Long | 2 | 2 (chicken, microwave) |
| `env2::open_the_curtains` | 2 | Short | 1 | 1 (curtains) |
| `env2::turn_on_tv` | 2 | Short | 1 | 1 (tv) |
| `env2::put_the_soap_in_the_bathroomcabinet` | 6 | Medium | 1 | 1 (barsoap) |
| `env2::throw_away_bananas` | 6 | Medium | 1 | 1 (bananas) |
| `env2::bring_my_book_to_the_sofa` | 4 | Short | 1 | 1 (book) |
| `env2::put_milk_in_the_fridge` | 6 | Medium | 1 | 1 (milk) |

Atomic distribution: 1 atomic=15, 2 atomics=4, >=3 atomics=1. Full generated 27 atomics but attempted only 26 because `env1::microwave_chicken` stopped after atomic 1 failed Retry-1.

GT primitive horizon and HPAF semantic decomposition are not equivalent. GT length includes navigation and precondition primitives; 15/20 tasks are single-atomic under Full, and even the Long set contains the single-atomic `wash the plate` task.

## Audit of the 15 filtered candidates

Classification counts: existing protocol=0, generic trace evaluator=9, not reliably evaluable=6. This is an offline proposal only; no task is restored here.

Shared-interface executability was checked by replay, not inferred from action names. All **128/128 non-empty released GT primitives** for the 15 tasks executed successfully from their task-specific frozen initial graphs using the same 17-action Evolving Graph interface. This does not make every natural-language task evaluable: several annotations omit the requested brushing, eating, waiting, or open-ended recipe semantics entirely.

| Excluded task | Released non-empty GT primitives | Successful replay | Shared action verbs used |
|---|---:|---:|---|
| `test_unseen::watch_tv` | 3 | 3 | `find`, `switchon`, `walk` |
| `test_unseen::brush_teeth` | 8 | 8 | `find`, `grab`, `putback`, `putin`, `walk` |
| `test_unseen::make_toast` | 8 | 8 | `find`, `grab`, `putin`, `switchoff`, `switchon` |
| `test_unseen::eat_chips_on_the_sofa` | 5 | 5 | `find`, `grab`, `sit`, `walk` |
| `test_unseen_ambiguous_goals::make_dinner` | 22 | 22 | `find`, `grab`, `putback`, `putin`, `switchon`, `walk` |
| `test_unseen_ambiguous_goals::make_breakfast` | 17 | 17 | `find`, `grab`, `putback`, `putin`, `switchon`, `walk` |
| `test_unseen_ambiguous_goals::bring_some_breakfast_to_the_coffeetable` | 13 | 13 | `find`, `grab`, `putback`, `putin`, `walk` |
| `test_unseen_ambiguous_goals::cook_lunch` | 7 | 7 | `find`, `grab`, `putback`, `switchon`, `walk` |
| `env1::watch_tv` | 2 | 2 | `find`, `switchon` |
| `env1::make_toast` | 6 | 6 | `find`, `grab`, `putin`, `switchoff`, `switchon` |
| `env1::wash_the_dishbowl_in_dishwasher` | 10 | 10 | `close`, `find`, `grab`, `open`, `putin`, `switchoff`, `switchon` |
| `env2::make_toast` | 6 | 6 | `find`, `grab`, `putin`, `switchoff`, `switchon` |
| `env2::wash_the_cutlery_in_dishwasher` | 10 | 10 | `close`, `find`, `grab`, `open`, `putin`, `switchoff`, `switchon` |
| `env2::make_coffee_in_coffeemaker` | 4 | 4 | `find`, `grab`, `switchoff`, `switchon` |
| `env2::heat_salmon_on_the_stove` | 7 | 7 | `find`, `grab`, `putin`, `switchoff`, `switchon` |

| Task | A. NL success | B. Persistent final graph | C. Fair trace/event evaluator | D. Shared interface | E. Released official evaluator actually scores | F. Restoration requirement | Classification |
|---|---|---|---|---|---|---|---|
| test_unseen::watch_tv | Clear event: actually watch TV | No WATCHED state; TV ON is insufficient | Yes: successful WATCH(tv) event | WATCH is present | TV ON plus incidental proximity/room deltas | Add generic successful-event evaluator; no method privilege | SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR |
| test_unseen::brush_teeth | Clear event | No BRUSHED/CLEAN teeth endpoint | No brushing event exists | No brush/use primitive | Holding toothbrush and toothpaste placement/proximity | Needs new action/state ontology | NOT_RELIABLY_EVALUABLE |
| test_unseen::make_toast | Clear appliance task | No TOASTED/time state | Conditionally: bread-loaded toaster ON/OFF cycle | Existing primitives execute the cycle | Ends holding bread; not toasted | Add generic appliance-cycle trace predicate | SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR |
| test_unseen::eat_chips_on_the_sofa | Clear event plus location | No consumed/eaten state | No eating event exists | EAT is absent | Holding chips and character SITTING/ON sofa | Needs EAT/action-state ontology | NOT_RELIABLY_EVALUABLE |
| test_unseen_ambiguous_goals::make_dinner | No unique meal content | Only one arbitrary recipe endpoint | Trace would encode an arbitrary recipe | Primitives execute one annotation | Stove ON plus incidental proximity | Needs a predeclared meal/recipe ontology or task-specific goal | NOT_RELIABLY_EVALUABLE |
| test_unseen_ambiguous_goals::make_breakfast | No unique meal content | Only one arbitrary recipe endpoint | Trace would encode an arbitrary recipe | Primitives execute one annotation | Stove ON and arbitrary placement/proximity | Needs a predeclared meal/recipe ontology | NOT_RELIABLY_EVALUABLE |
| test_unseen_ambiguous_goals::bring_some_breakfast_to_the_coffeetable | Breakfast objects are unspecified | No breakfast category relation | Trace must choose arbitrary objects | Actions work for a chosen recipe | Plate/character proximity and held fork | Needs category/recipe semantics | NOT_RELIABLY_EVALUABLE |
| test_unseen_ambiguous_goals::cook_lunch | Lunch content is open-ended | One salmon recipe is not the task definition | Trace would privilege one recipe | Actions execute the annotation | Stove ON and salmon/pan proximity | Needs a predeclared recipe ontology | NOT_RELIABLY_EVALUABLE |
| env1::watch_tv | Clear event | No WATCHED state | Yes: successful WATCH(tv) event | WATCH is present | TV ON plus incidental proximity/room deltas | Add generic successful-event evaluator | SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR |
| env1::make_toast | Clear appliance task | No TOASTED state | Conditionally: loaded toaster ON/OFF cycle | Cycle executes | Only bread/toaster proximity changes | Add generic appliance-cycle trace predicate | SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR |
| env1::wash_the_dishbowl_in_dishwasher | Clear appliance task | No dishwasher WASHED rule | Yes: loaded dishwasher ON/OFF cycle | Cycle executes | Dishbowl INSIDE dishwasher plus proximity; not washed | Add generic appliance-cycle trace predicate | SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR |
| env2::make_toast | Clear appliance task | No TOASTED state | Conditionally: loaded toaster ON/OFF cycle | Cycle executes | Only bread/toaster proximity changes | Add generic appliance-cycle trace predicate | SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR |
| env2::wash_the_cutlery_in_dishwasher | Clear appliance task | No dishwasher WASHED rule | Yes: loaded dishwasher ON/OFF cycle | Cycle executes | Fork INSIDE dishwasher plus proximity; not washed | Add generic appliance-cycle trace predicate | SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR |
| env2::make_coffee_in_coffeemaker | Clear appliance task | No COFFEE_MADE/USED state | Yes: coffeepot-loaded maker ON/OFF cycle | Cycle executes | Ends holding coffeepot | Add generic appliance-cycle trace predicate | SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR |
| env2::heat_salmon_on_the_stove | Clear heating task | Released final graph has no HEATED state for this path | Yes: salmon-in-pan stove ON/OFF cycle | Cycle executes | Ends holding salmon plus proximity | Add generic appliance-cycle trace predicate; fix ON/INSIDE ontology mismatch only in evaluator | SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR |

A generic trace evaluator would need to be method-independent and frozen before execution. Its reusable predicates would be: `SUCCESSFUL_EVENT(action, object)` for non-persistent events such as WATCH, and `SUCCESSFUL_APPLIANCE_CYCLE(item, appliance)` requiring the item to be correctly loaded when a successful ON transition occurs, followed by the released cycle endpoint. This changes the evaluator, not the action space, and must be reported as a simulator event surrogate rather than a real elapsed-time process.

The current exclusion remains methodologically sound because Phase 6 chose a stricter persistent-state evaluator and did not optimize N after seeing method results. The nine trace-evaluable candidates are optional future protocol work, not evidence that the current 20 were cherry-picked.
