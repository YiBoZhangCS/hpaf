"""Shared HPAF ProgramAgent constraints without evaluator-answer leakage."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


PROGRAM_AGENT_RULES = """Generic VirtualHome execution rules:
- Use only the listed lowercase primitive calls and available object class names.
- Ground and approach a target with find('target') or walk('target') before interaction.
- If the character is SITTING/LYING, call standup() before navigating elsewhere.
- grab requires the object to be close, accessible (not inside a closed container),
  and a free hand. Open a containing object only when needed and not already OPEN.
- open requires proximity, CLOSED state, and a free hand. close requires proximity
  and OPEN state. Do not repeat open/close or switch actions whose effect is true.
- putin/putback require the source object already held and the destination close;
  an openable putin destination must be OPEN. Put down held objects before a third grab.
- switchon/switchoff and sit require proximity.
- The simulator observation persistently marks food HEATED after it is inside an ON
  microwave. It marks an object WASHED after it is inside a sink while a faucet is ON.
  Establish those causal conditions with the shared primitives when the instruction
  requests heating or washing.
- There is no direct heat(), wash(), eat(), use(), wait(), or other unlisted primitive.
- Use current-state evidence to omit redundant actions. Never invent an action.
- Comments may organize the program. Do not emit assertions, functions, loops,
  instance IDs, frozen goal predicates, or an LLM-authored success claim.
"""


def action_signatures(actions_payload: Dict[str, Any]) -> List[str]:
    return [
        f"{name}({', '.join(['object'] * int(actions_payload['arity'][name]))})"
        for name in actions_payload["actions"]
    ]


def parse_json_object(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    if start < 0:
        return None, "no JSON object found"
    try:
        value, _ = json.JSONDecoder().raw_decode(stripped[start:])
    except json.JSONDecodeError as exc:
        return None, f"JSON parse failure: {exc}"
    if not isinstance(value, dict):
        return None, "top-level output is not an object"
    return value, None


def parse_program_json(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    value, error = parse_json_object(text)
    if error or value is None:
        return value, error
    if not isinstance(value.get("program"), str) or not value["program"].strip():
        return value, "missing non-empty program"
    return value, None

