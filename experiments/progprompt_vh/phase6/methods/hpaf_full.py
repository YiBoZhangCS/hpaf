"""Runtime TaskAgent, atomic ProgramAgent, and local Retry-1 prompts."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient

from .common import PROGRAM_AGENT_RULES, action_signatures, parse_json_object, parse_program_json


def generate_atomic_tasks(
    client: ModernLLMClient,
    *,
    task: str,
    objects: List[str],
    actions_payload: Dict[str, Any],
    llm_config: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], LLMCall, Optional[str]]:
    prompt = f"""You are the HPAF TaskAgent for a VirtualHome household task.

Decompose WHAT the task requires into the fewest ordered object-centric semantic
operations. A separate ProgramAgent handles HOW: finding, walking, proximity,
grasp preconditions, and prerequisite container open/close actions.

Rules:
1. Each atomic task describes one understandable operation centered on one
   manipulated object and, when needed, one reference/target object.
2. Never create Locate/Find/Walk/Navigate/Move/Position atomic tasks.
3. Never make OPEN/CLOSE a separate atomic when it is only a prerequisite. It
   may be atomic only when opening/closing is itself the user-requested goal.
4. Do not output primitive calls, instance IDs, graph predicates, verification
   answers, time-waiting steps, or invented objects.
5. Use 1-6 atomics, keep the original task meaning, and use exact class names
   from AVAILABLE OBJECTS for object fields.

Return strict JSON only:
{{"atomic_tasks":[{{"id":1,"instruction":"Put the apple into the fridge.","manipulated_object":"apple","target_object":"fridge"}}]}}
Use null for target_object when no reference object is needed.

ORIGINAL TASK:
{task}

AVAILABLE OBJECTS:
{json.dumps(objects)}

SHARED ACTION NAMES (ProgramAgent only; do not output calls):
{json.dumps(actions_payload['actions'])}
"""
    call = client.generate(
        prompt,
        max_tokens=int(llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]),
        seed=llm_config.get("seed"),
        instructions="Return only the strict JSON object requested by the HPAF TaskAgent protocol.",
    )
    parsed, error = parse_json_object(call.output_text)
    if error or parsed is None:
        return [], call, error
    atomics = parsed.get("atomic_tasks")
    if not isinstance(atomics, list) or not 1 <= len(atomics) <= 6:
        return [], call, "atomic_tasks must contain 1-6 items"
    available = set(objects)
    forbidden = re.compile(r"^\s*(locate|find|walk|navigate|move|position)\b", re.I)
    validated: List[Dict[str, Any]] = []
    for expected_id, item in enumerate(atomics, 1):
        if not isinstance(item, dict):
            return [], call, f"atomic {expected_id} is not an object"
        instruction = item.get("instruction")
        manipulated = item.get("manipulated_object")
        target = item.get("target_object")
        if item.get("id") != expected_id or not isinstance(instruction, str) or not instruction.strip():
            return [], call, f"atomic {expected_id} has invalid id/instruction"
        if forbidden.match(instruction):
            return [], call, f"atomic {expected_id} is a forbidden navigation/perception task"
        if manipulated not in available:
            return [], call, f"atomic {expected_id} manipulated_object is unavailable: {manipulated}"
        if target is not None and target not in available:
            return [], call, f"atomic {expected_id} target_object is unavailable: {target}"
        validated.append(
            {
                "id": expected_id,
                "instruction": instruction.strip(),
                "manipulated_object": manipulated,
                "target_object": target,
            }
        )
    return validated, call, None


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
    parsed, error = parse_program_json(call.output_text)
    return parsed or {}, call, error

