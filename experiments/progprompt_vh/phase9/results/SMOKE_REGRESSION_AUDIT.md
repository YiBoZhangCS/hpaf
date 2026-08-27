# Regression-Only Smoke Audit

The required smoke slices are all from the 29-task official-source regression set. No confirmatory task was used and no smoke output was used to tune the frozen prompt.

| Slice | Task | ProgPrompt | Flat | Full | Checks |
|---|---|---:|---:|---:|---|
| short | `test_unseen::turn_off_light` | 1 | 1 | 1 | ProgPrompt assertions=PASS; Flat one generation+verifier=PASS; Full pipeline calls=PASS |
| medium | `test_unseen::put_salmon_in_the_fridge` | 1 | 1 | 1 | ProgPrompt assertions=PASS; Flat one generation+verifier=PASS; Full pipeline calls=PASS |
| long | `test_unseen::wash_the_plate` | 0 | 1 | 0 | ProgPrompt assertions=PASS; Flat one generation+verifier=PASS; Full pipeline calls=PASS |
| source_target_transfer | `env1::put_chicken_in_the_fridge` | 1 | 1 | 1 | ProgPrompt assertions=PASS; Flat one generation+verifier=PASS; Full pipeline calls=PASS |

The formal run records confirm strict binary assertions, shared Flat/Full ProgramAgent role contracts, Full TaskAgent/atomic verifier/Retry-1 roles where invoked, and no API crash. Smoke is pipeline validation only; method planning failures remain in the formal results.
