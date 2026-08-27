"""Shared process-aware ProgramAgent contract in verbose and compact forms."""

from __future__ import annotations

from typing import Any, Dict


PROCESS_RULE = """Some requested operations are completed processes, not merely static states.
For a process-oriented task, do not stop after initiation: generate the complete
executable lifecycle reasonably needed to finish it. Preserve object/device
preconditions throughout. When completion requires a closed lifecycle, include
the necessary terminal operation after activation. For a requested interaction
event, require the interaction itself to execute successfully. Use only simulator
capabilities; never invent waiting, time, or unsupported actions."""


PROGRAM_RULES_VERBOSE = f"""Generic VirtualHome execution rules:
- Use only listed lowercase calls and available object class names.
- Establish proximity with find or walk immediately before interaction. If the
  character is sitting/lying, stand up before navigating.
- grab needs a close accessible source and free hand. Open a containing object
  only when needed. Do not repeat an already-satisfied open/close/switch action.
- Preserve alignment to object X until interaction(X) completes.
- Transfer order is: align source, acquire source, align target, satisfy target
  prerequisites, place source. Never align target before acquiring source.
- putin/putback need the source held and target close; an openable putin target
  must be open. Movement invalidates earlier proximity assumptions.
- A repair restores failed preconditions before retrying the interaction.
- There are no direct heat, wash, eat, use, or wait primitives. Never invent calls.
- Comments may organize output. Do not emit assertions, functions, loops,
  instance IDs, evaluator predicates, or success claims.

{PROCESS_RULE}
"""


PROGRAM_RULES_COMPACT = f"""Rules: listed calls/classes only; standup before moving if seated/lying.
Before interact(X), find/walk(X) and do not align elsewhere first. Transfer:
align source > grab source > align target > meet target state > put source.
putin/putback require held source + close target; open an openable putin target.
Movement cancels prior proximity. Avoid redundant state actions. Repair failed
preconditions before retry. No invented calls, assertions, loops, IDs, evaluator
predicates, or success claims.

{PROCESS_RULE}
"""


def action_documentation(actions_payload: Dict[str, Any], *, compact: bool) -> str:
    signatures = [
        f"{name}({','.join(['obj'] * int(actions_payload['arity'][name]))})"
        for name in actions_payload["actions"]
    ]
    if compact:
        return ", ".join(signatures)
    return "\n".join(f"- {signature}" for signature in signatures)


def program_rules(*, compact: bool) -> str:
    return PROGRAM_RULES_COMPACT if compact else PROGRAM_RULES_VERBOSE

