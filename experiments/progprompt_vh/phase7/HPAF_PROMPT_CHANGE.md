# Phase-7 HPAF Prompt Change

## Before prompt

The Phase-6 ProgramAgent rules required target approach, basic action preconditions, and held-source/destination checks, but did not explicitly require source acquisition before target alignment or re-alignment after movement. A source-target sequence could therefore align to the target before acquiring the source, losing source proximity; a repair could repeat placement without restoring target proximity.

## After prompt

Phase 7 adds these generic constraints to the ProgramAgent rule block shared by Flat and Full:

- Interaction locality: preserve alignment/proximity to object X until its interaction completes.
- Source-target transfer order: align source, acquire source, align target, satisfy target prerequisites, then place/interact the source.
- Never align to the target before the source is successfully acquired.
- After movement or alignment to another object, do not assume the prior CLOSE relation remains valid; regenerate from current state.
- Placement requires held source, target proximity, and required target state.
- Retry repair must restore the failed precondition before repeating the failed interaction.

The full Phase-7 rule block is frozen in `methods/common.py` and injected identically into Flat and Full ProgramAgent prompts.

## Generic rationale

These are action-precondition and sequencing invariants over abstract source, target, and interaction variables. They contain no object names, task IDs, evaluator conditions, ground-truth actions, or method-specific success claims. The same rule block is used for Flat whole-task generation and Full per-atomic generation/repair.

## Known failure motivating it

The Phase-6 `env1::microwave_chicken` trace exposed a generic source-target locality failure: aligning to the target before acquiring the source invalidated the source interaction, and the repair acquired the source without re-aligning to the target. This failure was used once to design the generic rule block; the Phase-7 prompt is frozen before formal execution.

