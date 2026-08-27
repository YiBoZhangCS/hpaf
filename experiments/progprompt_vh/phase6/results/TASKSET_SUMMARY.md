# Phase-6 Task-Set Summary

Official dataset source: ProgPrompt / VirtualHome pinned release.

Final held-out tasks: 20 task-scene instances.

Split composition: test_unseen=6, test_unseen_ambiguous_goals=1, env1=7, env2=6.

GT action length: min 2 / mean 7.00 / median 6.0 / max 18.

Short count: 6

Medium count: 10

Long count: 4

## Filtered held-out candidates

- `test_unseen::watch_tv`: WATCH is an event but the graph has no persistent WATCHED state; TV ON does not establish that watching occurred.
- `test_unseen::brush_teeth`: The shared API has no brush/use primitive and the graph has no BRUSHED_TEETH state.
- `test_unseen::make_toast`: The graph has no TOASTED state or elapsed-time transition; toaster placement/power is only an initiation proxy.
- `test_unseen::eat_chips_on_the_sofa`: EAT is outside the released ProgPrompt/shared API and consumption has no persistent state.
- `test_unseen_ambiguous_goals::make_dinner`: Open-ended meal content has no unique method-independent semantic endpoint.
- `test_unseen_ambiguous_goals::make_breakfast`: Open-ended meal content has no unique method-independent semantic endpoint.
- `test_unseen_ambiguous_goals::bring_some_breakfast_to_the_coffeetable`: The requested breakfast objects are unspecified and the ontology has no breakfast category predicate.
- `test_unseen_ambiguous_goals::cook_lunch`: Open-ended meal content and cooking completion have no unique persistent endpoint.
- `env1::watch_tv`: WATCH is an event but the graph has no persistent WATCHED state.
- `env1::make_toast`: The graph has no TOASTED state or elapsed-time transition.
- `env1::wash_the_dishbowl_in_dishwasher`: The pinned augmentation has no dishwasher-to-WASHED rule, so washing completion is not representable.
- `env2::make_toast`: The graph has no TOASTED state or elapsed-time transition.
- `env2::wash_the_cutlery_in_dishwasher`: The pinned augmentation has no dishwasher-to-WASHED rule, so washing completion is not representable.
- `env2::make_coffee_in_coffeemaker`: The graph has no COFFEE_MADE/USED state and the released program leaves only a held coffeepot endpoint.
- `env2::heat_salmon_on_the_stove`: Offline replay of the released GT path does not yield HEATED under the pinned augmentation, so final heat completion is not reliably scoreable.

## Seen-task exclusion

All 10 test_seen entries are excluded before held-out candidacy because their exact task texts occur in train; the three released default prompt examples are also in this slice.

## Resume/interview setting sentence

“Evaluated on 20 official held-out VirtualHome household task-scene instances from ProgPrompt, with ground-truth action horizons ranging from 2 to 18; all methods use the same LLM backbone and shared executable action interface.”
