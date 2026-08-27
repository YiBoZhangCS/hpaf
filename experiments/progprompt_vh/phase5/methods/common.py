"""Shared ProgramAgent schema and generic VirtualHome execution guidance."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple


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
- switchon/switchoff and sit require proximity. turnto can establish facing for lookat.
- Evaluator augmentation is causal and persistent: food INSIDE an ON microwave
  becomes HEATED; an object INSIDE a sink while a faucet is ON becomes WASHED.
  Establish those graph conditions with putin/switchon. There is no direct
  wash(), heat(), eat(), use(), wait(), or other unlisted primitive.
- Use current-state evidence to omit redundant actions. Never invent an action.
- Comments may organize the program, but verification happens after execution from
  the graph; never output an LLM-authored success claim or condition.
"""


def parse_program_json(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
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
    program = value.get("program")
    if not isinstance(program, str) or not program.strip():
        return value, "missing non-empty program"
    return value, None
