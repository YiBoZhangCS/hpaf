"""Frozen generic constraints shared by Flat and Full ProgramAgents."""

from __future__ import annotations

PROGRAM_AGENT_RULES = """Generic VirtualHome execution rules:
- Use only the listed lowercase primitive calls and available object class names.
- Ground and approach a target with find('target') or walk('target') before interaction.
- If the character is SITTING/LYING, call standup() before navigating elsewhere.
- grab requires the object to be close, accessible (not inside a closed container),
  and a free hand. Open a containing object only when needed and not already OPEN.
- open requires proximity, CLOSED state, and a free hand. close requires proximity
  and OPEN state. Do not repeat open/close or switch actions whose effect is true.
- Interaction locality: before interacting with object X, establish and preserve
  the required alignment/proximity to X until that interaction completes. Do not
  align to an unrelated object between alignment(X) and interaction(X).
- For a source-target transfer, use this conceptual order: locate/align the source,
  acquire the source, locate/align the target, satisfy target prerequisites, then
  place/interact the source with the target. Never switch to the target before the
  source is successfully acquired.
- putin/putback require the source object already held and the destination close;
  an openable putin destination must be OPEN. Put down held objects before a third grab.
- After movement or alignment to another object, do not assume an earlier CLOSE
  relation still holds. Regenerate the next interaction from the current state.
- switchon/switchoff and sit require proximity.
- A repair must restore failed preconditions explicitly: reacquire a missing source,
  realign to a distant target, and satisfy target state before repeating placement.
- Some simulator augmentations persist an outcome only after the relevant object is
  placed in the required appliance/container and its controller completes the
  requested state transition. Establish causal conditions with shared primitives
  when the instruction requests an appliance or washing outcome.
- There is no direct heat(), wash(), eat(), use(), wait(), or other unlisted primitive.
- Use current-state evidence to omit redundant actions. Never invent an action.
- Comments may organize the program. Do not emit assertions, functions, loops,
  instance IDs, frozen goal predicates, or an LLM-authored success claim.
"""


def action_signatures(actions_payload):
    return [
        f"{name}({', '.join(['object'] * int(actions_payload['arity'][name]))})"
        for name in actions_payload["actions"]
    ]
