# Phase-7 Dataset Expansion Audit

Task selection was frozen from the Phase-6 independent audit before any Phase-7 method execution. No task was selected using Phase-7 output.

## Restored official trace-evaluable candidates

| Source file | Official split/source | Task text | Scene | GT length | Evaluator | Inclusion reason |
|---|---|---|---:|---:|---|---|
| `third_party/progprompt-vh/data/test_unseen/file3_annotated.json` | `test_unseen` | watch tv | 0 | 3 | `generic_trace/SUCCESSFUL_EVENT` | Pre-frozen official held-out candidate classified SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR in Phase-6 audit; restored before any Phase-7 method run. |
| `third_party/progprompt-vh/data/test_unseen/file3_annotated.json` | `test_unseen` | make toast | 0 | 8 | `generic_trace/SUCCESSFUL_APPLIANCE_CYCLE` | Pre-frozen official held-out candidate classified SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR in Phase-6 audit; restored before any Phase-7 method run. |
| `third_party/progprompt-vh/data/new_env/env1_annotated.json` | `env1` | watch tv | 1 | 2 | `generic_trace/SUCCESSFUL_EVENT` | Pre-frozen official held-out candidate classified SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR in Phase-6 audit; restored before any Phase-7 method run. |
| `third_party/progprompt-vh/data/new_env/env1_annotated.json` | `env1` | make toast | 1 | 6 | `generic_trace/SUCCESSFUL_APPLIANCE_CYCLE` | Pre-frozen official held-out candidate classified SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR in Phase-6 audit; restored before any Phase-7 method run. |
| `third_party/progprompt-vh/data/new_env/env1_annotated.json` | `env1` | wash the dishbowl in dishwasher | 1 | 10 | `generic_trace/SUCCESSFUL_APPLIANCE_CYCLE` | Pre-frozen official held-out candidate classified SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR in Phase-6 audit; restored before any Phase-7 method run. |
| `third_party/progprompt-vh/data/new_env/env2_annotated.json` | `env2` | make toast | 2 | 6 | `generic_trace/SUCCESSFUL_APPLIANCE_CYCLE` | Pre-frozen official held-out candidate classified SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR in Phase-6 audit; restored before any Phase-7 method run. |
| `third_party/progprompt-vh/data/new_env/env2_annotated.json` | `env2` | wash the cutlery in dishwasher | 2 | 10 | `generic_trace/SUCCESSFUL_APPLIANCE_CYCLE` | Pre-frozen official held-out candidate classified SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR in Phase-6 audit; restored before any Phase-7 method run. |
| `third_party/progprompt-vh/data/new_env/env2_annotated.json` | `env2` | make coffee in coffeemaker | 2 | 4 | `generic_trace/SUCCESSFUL_APPLIANCE_CYCLE` | Pre-frozen official held-out candidate classified SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR in Phase-6 audit; restored before any Phase-7 method run. |
| `third_party/progprompt-vh/data/new_env/env2_annotated.json` | `env2` | heat salmon on the stove | 2 | 7 | `generic_trace/SUCCESSFUL_APPLIANCE_CYCLE` | Pre-frozen official held-out candidate classified SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR in Phase-6 audit; restored before any Phase-7 method run. |

## Rejected official candidates

The other six Phase-6 excluded candidates remain out of the confirmatory set: `brush teeth`, `eat chips on the sofa`, `make dinner`, `make breakfast`, `bring some breakfast to the coffeetable`, and `cook lunch`. They lack a unique method-independent persistent or generic trace endpoint under the pinned action/state ontology. No synthetic tasks were added.

## Set accounting

- Regression: 20 task-scene instances.
- Confirmatory: 9 task-scene instances.
- Combined: 29 task-scene instances / 24 unique task texts.
- Persistent-state evaluated: 20; generic trace evaluated: 9; synthetic: 0.
