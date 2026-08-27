# HPAF ProgramAgent Prompt Freeze

## Before

The Phase-8 frozen ProgramAgent contract required listed actions/classes,
precondition-aware navigation, process completion, and one local repair, but did
not state the source-target interaction invariant with enough precision for
generic transfer chains.

## After

The frozen rules used by both HPAF-Flat and HPAF-Full explicitly require:

1. Establish and preserve locality to object X until `interact(X)` completes.
2. For a transfer, align source, acquire source, align target, satisfy target
   state, then place source; do not align target before acquisition.
3. `putin/putback` require a held source and close target, with open target state
   when required.
4. Movement or re-alignment invalidates earlier proximity assumptions.
5. Retry-1 restores the typed failed precondition before retrying.

These are generic constraints in the frozen Phase-8 `program_rules` bundle. No
formal task name, object name, task ID, evaluator predicate, or correct test
sequence occurs in the prompt. Flat and Full receive the same rules; Full alone
adds TaskAgent decomposition, per-atomic verification, and one Retry-1.

Prompt freeze is represented by `data/VH40_PROTOCOL_LOCK.json` and its method
bundle SHA-256. The rejected compression experiments did not modify this bundle.

