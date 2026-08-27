# Phase-6 Official Dataset Audit

This audit is offline and was completed before any Phase-6 planning or verification call.

| Split | Number of tasks | Has GT program | Has final state | Used as prompt/train | Candidate for held-out eval |
|---|---:|---|---|---|---|
| train | 35 | Yes | 34/35 rows | Yes: train library | No |
| test_seen | 10 | Yes | Yes (10) | All task texts occur in train; 3 are default prompt examples | No |
| test_unseen | 10 | Yes | Yes (10) | No | Yes |
| test_unseen_ambiguous_goals | 5 | Yes | Yes (5) | No | Yes, subject to semantic-goal screening |
| env1 | 10 | Yes | Yes (10); task-specific official initial graphs | Some task texts seen; scene 1 is held out | Yes: environment-held-out |
| env2 | 10 | Yes | Yes (10); task-specific official initial graphs | Some task texts seen; scene 2 is held out | Yes: environment-held-out |
| all_plans_env0 | 50 | Natural-language plan outputs, not annotated executable GT | No dedicated positional file | Source inventory | No |

## What the release actually contains

- The primary annotation inventory contains 70 task-scene instances: 50 in scene 0 (35 train rows, 10 test_unseen rows, 5 ambiguous-goal rows) plus 10 env1 and 10 env2 rows.
- The 10-row test_seen directory is a derived seen-task evaluation slice: every task text is already in train, so adding it to the 70 would double-count those instances.
- Train has 35 annotation rows but 34 unique task strings because `read book under table lamp` appears in two source files. The Pythonic train-plan library and train final-state file each contain 34 entries.
- `final_states.json` has 39 rows and is the aggregate 34 unique train states plus 5 ambiguous-goal states; split-specific final-state files are used for evaluation.

## Prompt leakage

The released default three-example prompt uses: `put the wine glass in the kitchen cabinet`, `throw away the lime`, `wash mug`. All three are in test_seen/train, and none is in the final Phase-6 held-out set.

## Shared-action and semantic screening

All annotated primitive lines in the 35 held-out candidates use names contained in the frozen 17-action intersection. Filtering is nevertheless required when the natural-language completion itself has no reliable persistent state under that interface. Empty annotation steps do not count as an executable implementation of eating, brushing, elapsed-time toasting, open-ended cooking, dishwasher washing, or coffee production.

The held-out candidate pool is 35 task-scene instances: test_unseen (10), test_unseen_ambiguous_goals (5), env1 (10), and env2 (10). Decisions are made before method execution and stored for every task in `data/task_manifest.json`.

## Selection counts

- `excluded_not_held_out`: 10
- `excluded_unrepresentable`: 15
- `included`: 20

## Excluded held-out candidates

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

## Integrity checks

- Train annotation rows: 35; unique task strings: 34.
- Pythonic train examples: 34.
- Audited evaluation rows represented in the manifest: 45.
- No task is filtered using any Phase-6 method output or score.
