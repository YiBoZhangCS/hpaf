"""Frozen-semantic-decomposition ProgramAgent and Retry-1 prompts."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient

from .common import PROGRAM_AGENT_RULES, parse_program_json


def action_signatures(actions_payload: Dict[str, Any]) -> List[str]:
    return [
        f"{name}({', '.join(['object'] * actions_payload['arity'][name])})"
        for name in actions_payload["actions"]
    ]


def generate_atomic_program(
    client: ModernLLMClient,
    *,
    original_task: str,
    atomic_task: Dict[str, Any],
    state: str,
    objects: List[str],
    actions_payload: Dict[str, Any],
    llm_config: Dict[str, Any],
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    prompt = f"""You are the HPAF ProgramAgent for VirtualHome.

Compile only the CURRENT FROZEN SEMANTIC ATOMIC TASK into a short executable
program. Do not redo earlier atomics, plan future atomics, modify the frozen
goal, or emit assertions/functions/loops/instance IDs.

Return strict JSON only:
{{"plan_brief":"...","program":"# concise comments\\nfind('object')\\n..."}}

ORIGINAL TASK:
{original_task}

CURRENT ATOMIC INSTRUCTION:
{atomic_task['instruction']}

PRIMARY SEMANTIC GOAL (verified independently after execution):
{json.dumps(atomic_task['primary_goal_condition'], ensure_ascii=False)}

SUPPORTING CONDITIONS:
{json.dumps(atomic_task.get('supporting_conditions', []), ensure_ascii=False)}

CURRENT SYMBOLIC STATE:
{state}

AVAILABLE OBJECTS:
{json.dumps(objects)}

GRAPH_SUPPORTED_ACTIONS:
{json.dumps(action_signatures(actions_payload))}

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


def generate_repair_program(
    client: ModernLLMClient,
    *,
    original_task: str,
    atomic_task: Dict[str, Any],
    state: str,
    objects: List[str],
    actions_payload: Dict[str, Any],
    previous_program: str,
    execution_trace: List[Dict[str, Any]],
    failed_actions: List[Dict[str, Any]],
    typed_errors: List[Dict[str, Any]],
    llm_config: Dict[str, Any],
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    prompt = f"""You are the HPAF ProgramAgent performing the single allowed
local repair for one VirtualHome atomic task.

Repair ONLY the current atomic task from the CURRENT post-failure graph. Do not
replay successful actions blindly, replan the remaining full task, alter the
frozen decomposition/goal, or emit assertions/functions/loops/instance IDs.

Return strict JSON only:
{{"repair_brief":"...","program":"# local repair\\nfind('object')\\n..."}}

ORIGINAL TASK:
{original_task}

CURRENT ATOMIC INSTRUCTION:
{atomic_task['instruction']}

PRIMARY SEMANTIC GOAL:
{json.dumps(atomic_task['primary_goal_condition'], ensure_ascii=False)}

CURRENT SYMBOLIC STATE:
{state}

PREVIOUS GENERATED PROGRAM:
{previous_program or '<generation failed before a valid program>'}

CURRENT-ATOMIC EXECUTION TRACE:
{json.dumps(execution_trace, ensure_ascii=False)}

FAILED ACTIONS:
{json.dumps(failed_actions, ensure_ascii=False)}

TYPED ERRORS:
{json.dumps(typed_errors, ensure_ascii=False)}

AVAILABLE OBJECTS:
{json.dumps(objects)}

GRAPH_SUPPORTED_ACTIONS:
{json.dumps(action_signatures(actions_payload))}

{PROGRAM_AGENT_RULES}
"""
    call = client.generate(
        prompt,
        max_tokens=int(llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]),
        seed=llm_config.get("seed"),
        instructions="Return only the strict JSON object requested by the Retry-1 ProgramAgent protocol.",
    )
    parsed, error = parse_program_json(call.output_text)
    return parsed or {}, call, error

