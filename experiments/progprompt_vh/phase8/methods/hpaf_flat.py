"""Process-aware Flat ProgramAgent with selectable context representation."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient
from experiments.progprompt_vh.phase6.methods.common import parse_program_json
from experiments.progprompt_vh.phase8.methods.common import (
    action_documentation,
    program_rules,
)


def generate_flat_program(
    client: ModernLLMClient,
    *,
    task: str,
    state: str,
    objects: List[str],
    actions_payload: Dict[str, Any],
    llm_config: Dict[str, Any],
    compact: bool,
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    prompt = f"""You are the HPAF ProgramAgent for VirtualHome.
Generate one complete executable program for the whole task. Infer whether each
requested outcome is a static state or a completed process. Return strict JSON:
{{"plan_brief":"...","program":"# comments\\nfind('object')\\n..."}}

TASK: {task}
CURRENT STATE: {state}
AVAILABLE OBJECT CLASSES: {json.dumps(objects)}
PRIMITIVE CALLS: {action_documentation(actions_payload, compact=compact)}

{program_rules(compact=compact)}"""
    call = client.generate(
        prompt,
        max_tokens=int(llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]),
        seed=llm_config.get("seed"),
        instructions="Return only the requested strict ProgramAgent JSON object.",
    )
    parsed, error = parse_program_json(call.output_text)
    return parsed or {}, call, error

