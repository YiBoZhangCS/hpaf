"""Single-shot whole-task HPAF ablation without explicit hierarchy."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient

from .common import PROGRAM_AGENT_RULES, parse_program_json


def generate_flat_program(
    client: ModernLLMClient,
    *,
    task: str,
    final_semantic_conditions: List[Dict[str, Any]],
    state: str,
    objects: List[str],
    actions_payload: Dict[str, Any],
    llm_config: Dict[str, Any],
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    goals = [
        {key: value for key, value in condition.items() if key not in {"condition", "rationale"}}
        for condition in final_semantic_conditions
    ]
    signatures = [
        f"{name}({', '.join(['object'] * actions_payload['arity'][name])})"
        for name in actions_payload["actions"]
    ]
    prompt = f"""You are the HPAF ProgramAgent for VirtualHome.

Generate one complete executable program for the WHOLE ORIGINAL TASK. This is
the flat ablation: there is no TaskAgent, frozen atomic decomposition, or
manually supplied intermediate subgoal. Plan naturally, but return one program.

Return strict JSON only:
{{"plan_brief":"...","program":"# concise comments\\nfind('object')\\n..."}}

ORIGINAL TASK:
{task}

FINAL SEMANTIC VERIFICATION TARGETS (conjunctive; do not add intermediate goals):
{json.dumps(goals, ensure_ascii=False)}

CURRENT INITIAL SYMBOLIC STATE:
{state}

AVAILABLE OBJECTS:
{json.dumps(objects)}

GRAPH_SUPPORTED_ACTIONS:
{json.dumps(signatures)}

{PROGRAM_AGENT_RULES}
"""
    call = client.generate(
        prompt,
        max_tokens=int(llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]),
        seed=llm_config.get("seed"),
        instructions="Return only the strict JSON object requested by the ProgramAgent protocol.",
    )
    parsed, error = parse_program_json(call.output_text)
    return parsed or {}, call, error

