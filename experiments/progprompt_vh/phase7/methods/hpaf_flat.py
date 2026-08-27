"""Flat ProgramAgent using the Phase-7 frozen generic constraints."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient
from experiments.progprompt_vh.phase6.methods import hpaf_flat as phase6_flat
from .common import PROGRAM_AGENT_RULES, action_signatures


def generate_flat_program(
    client: ModernLLMClient,
    *,
    task: str,
    state: str,
    objects: List[str],
    actions_payload: Dict[str, Any],
    llm_config: Dict[str, Any],
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    prompt = f"""You are the HPAF ProgramAgent for VirtualHome.

Generate one complete executable program for the WHOLE ORIGINAL TASK. This is
the flat ablation: there is no TaskAgent, atomic decomposition, or manually
supplied intermediate goal. Plan naturally and return one program.

Return strict JSON only:
{{"plan_brief":"...","program":"# concise comments\\nfind('object')\\n..."}}

ORIGINAL TASK:
{task}

CURRENT INITIAL SYMBOLIC OBSERVATION:
{state}

AVAILABLE OBJECTS:
{json.dumps(objects)}

SHARED PRIMITIVE ACTIONS:
{json.dumps(action_signatures(actions_payload))}

{PROGRAM_AGENT_RULES}
"""
    call = client.generate(
        prompt,
        max_tokens=int(llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]),
        seed=llm_config.get("seed"),
        instructions="Return only the strict JSON object requested by the HPAF ProgramAgent protocol.",
    )
    parsed, error = phase6_flat.parse_program_json(call.output_text)
    return parsed or {}, call, error

