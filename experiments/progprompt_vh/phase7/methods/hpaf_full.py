"""Full HPAF prompts with the same generic constraints as Flat."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient
from experiments.progprompt_vh.phase6.methods import hpaf_full as phase6_full
from .common import PROGRAM_AGENT_RULES, action_signatures


def generate_atomic_tasks(*args, **kwargs):
    return phase6_full.generate_atomic_tasks(*args, **kwargs)


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

Compile only the CURRENT OBJECT-CENTRIC ATOMIC TASK into a short executable
program. Do not redo earlier atomics, plan future atomics, or emit assertions.

Return strict JSON only:
{{"plan_brief":"...","program":"# concise comments\\nfind('object')\\n..."}}

ORIGINAL TASK:
{original_task}

CURRENT ATOMIC TASK:
{json.dumps(atomic_task, ensure_ascii=False)}

CURRENT SYMBOLIC OBSERVATION:
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
        instructions="Return only the strict JSON object requested by the HPAF atomic ProgramAgent protocol.",
    )
    parsed, error = phase6_full.parse_program_json(call.output_text)
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
    typed_errors: List[Dict[str, Any]],
    verifier_result: Dict[str, Any],
    llm_config: Dict[str, Any],
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    prompt = f"""You are the HPAF ProgramAgent performing the single allowed
local repair for one VirtualHome atomic task.

Repair ONLY the current atomic from the CURRENT post-execution observation.
Do not replay successful actions blindly, replan future atomics, or emit
assertions/functions/loops/instance IDs.

Return strict JSON only:
{{"repair_brief":"...","program":"# local repair\\nfind('object')\\n..."}}

ORIGINAL TASK:
{original_task}

CURRENT ATOMIC TASK:
{json.dumps(atomic_task, ensure_ascii=False)}

CURRENT SYMBOLIC OBSERVATION:
{state}

PREVIOUS PROGRAM:
{previous_program or '<no valid program>'}

CURRENT-ATOMIC EXECUTION TRACE:
{json.dumps(execution_trace, ensure_ascii=False)}

TYPED ERRORS:
{json.dumps(typed_errors, ensure_ascii=False)}

ONLINE VERIFIER FEEDBACK:
{json.dumps(verifier_result, ensure_ascii=False)}

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
        instructions="Return only the strict JSON object requested by the HPAF local Retry-1 protocol.",
    )
    parsed, error = phase6_full.parse_program_json(call.output_text)
    return parsed or {}, call, error

