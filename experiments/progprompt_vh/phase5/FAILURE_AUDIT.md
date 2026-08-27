# Phase-4 Failure Audit

This is an offline, read-only, multi-label diagnosis of the 30 immutable Phase-4 records. Counts are affected-record counts per category, so columns are not mutually exclusive and do not sum to 30. Phase-4 metrics are not modified.

## Taxonomy

| Failure category | Count | Affected tasks | Affected methods | Example trace | Phase-5 response |
|---|---:|---|---|---|---|
| A_benchmark_goal_artifact | 11 | bring coffeepot and cupcake to the coffee table; eat chips on the sofa; make toast; microwave salmon; turn off light; watch tv | HPAF-Decomp-ClosedLoop; HPAF-Decomp-Static; ProgPrompt-Full | Official missing set contains only endpoint artifacts: character CLOSE tv / character CLOSE tvstand / tv CLOSE character / tvstand CLOSE character | Yes: Phase 5 retains official scores and adds a pre-frozen semantic evaluator. |
| B_decomposition_granularity_error | 14 | bring coffeepot and cupcake to the coffee table; eat chips on the sofa; microwave salmon; put salmon in the fridge; throw away apple; wash the plate; watch tv | HPAF-Decomp-ClosedLoop; HPAF-Decomp-Static | First-level prerequisite task(s): Locate the remote control used to operate the television / Position yourself in a suitable seating location (such as the sofa) to view the television | Yes: TaskAgent is restricted to verifiable semantic state transitions. |
| C_impossible_or_unrepresentable_goal | 9 | brush teeth; eat chips on the sofa; make toast; wash the plate; watch tv | HPAF-Decomp-ClosedLoop; HPAF-Decomp-Static | No stable graph-level completion for: Watch the television that is now powered on | Partly: illegal decompositions are rejected; unavoidable task-level ambiguities are frozen and disclosed. |
| D_unsupported_action | 5 | brush teeth; eat chips on the sofa; make toast; put salmon in the fridge; wash the plate | HPAF-Decomp-ClosedLoop; HPAF-Decomp-Static | puton('toothpaste', 'toothbrush'): hallucinated action: puton / use('toothbrush'): hallucinated action: use | Yes: all Phase-5 prompts and the executor share a source-audited action set. |
| E_action_precondition_failure | 17 | brush teeth; eat chips on the sofa; make toast; microwave salmon; put salmon in the fridge; throw away apple; wash the plate; watch tv | HPAF-Decomp-ClosedLoop; HPAF-Decomp-Static; ProgPrompt-Full | find('remotecontrol'): <character> (1) is not close to <remotecontrol> (452) when executing "[FIND] <remotecontrol> (452) [0]" / find('remotecontrol'): <character> (1) is not close to <remotecontrol> (452) when executing "[FIND] <remotecontrol> (452) [0]",<character> (1) is not close to <remotecontrol> (452) when executing "[FIND] <remotecontrol> (452) [0]" | Yes: generic precondition guidance, current state, verification, and Retry-1 address it; failures remain possible. |
| F_verification_false_negative | 0 | — | — | No matching Phase-4 record | Yes: Phase 5 uses a deterministic frozen-condition verifier. |
| G_verified_but_stopped | 2 | eat chips on the sofa; put salmon in the fridge | HPAF-Decomp-ClosedLoop | Eat the chips while on the sofa (boundary_executable=False, can_continue=False) | Yes: verified=True is the continuation gate; Exec is diagnostic only. |
| H_legitimate_planning_failure | 0 | — | — | No matching Phase-4 record | No special-case fix: it remains a planning failure in the controlled comparison. |
| I_stale_state_generation_error | 5 | microwave salmon; put salmon in the fridge; throw away apple; wash the plate; watch tv | HPAF-Decomp-Static | sit('sofa'): <character> (1) is sitting when executing "[SIT] <sofa> (368) [0]" / watch('tv'): <character> (1) is sitting when executing "[SIT] <sofa> (368) [0]",char room <livingroom> (335) is not node room <kitchen> (205) when executing "[WATCH] <tv> (264) [0]" | Yes: Static is removed; Hierarchical generation always receives current state. |
| J_recovery_parser_error | 8 | bring coffeepot and cupcake to the coffee table; brush teeth; make toast; microwave salmon; put salmon in the fridge; throw away apple; turn off light; wash the plate | ProgPrompt-Full | else: find('lightswitch'): hallucinated action: else / else: switchon('lightswitch'): hallucinated action: else | Yes: Phase-5 interpreter preserves and explicitly parses assertion/recovery branches. |

## Audit rules

- `benchmark_goal_artifact` is conservative: a failed official score is tagged only when every missing condition is CLOSE, character holding/location, or an object's demonstration-specific room containment; missing task-object states or relations prevent this label.
- `unsupported_action` excludes `else:`. That is a recovery-interpreter defect, reported separately as `recovery_parser_error`.
- `verification_false_negative` uses the saved verification and condition-detail records only; it does not reinterpret or change an old score.
- `legitimate_planning_failure` is deliberately residual: official SR=0 and none of the detected artifact/implementation/decomposition conditions applies.

## Integrity

Input: `experiments/progprompt_vh/results/raw_runs.jsonl` (30 records).
The audit script writes only Phase-5 artifacts and makes no API calls.
