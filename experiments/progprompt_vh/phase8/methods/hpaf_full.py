"""Process-aware TaskAgent, atomic ProgramAgent, and Retry-1 prompts."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient
from experiments.progprompt_vh.phase6.methods.common import (
    parse_json_object,
    parse_program_json,
)
from experiments.progprompt_vh.phase8.methods.common import (
    action_documentation,
    program_rules,
)


def generate_atomic_tasks(
    client: ModernLLMClient,
    *,
    task: str,
    objects: List[str],
    actions_payload: Dict[str, Any],
    llm_config: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], LLMCall, Optional[str]]:
    prompt = f"""You are the HPAF TaskAgent for a VirtualHome household task.
Decompose WHAT is required into the fewest ordered object-centric semantic
operations. A separate ProgramAgent handles navigation and action preconditions.

Rules:
1. Each atomic is one understandable operation centered on one manipulated
   object and optional target/reference object.
2. Never create locate/find/walk/navigation atomics. Opening/closing is an
   atomic only when it is the requested outcome, not merely a prerequisite.
3. Classify `completion_mode` as `state` for a persistent requested state or
   relation, and `process` when the requested operation must be completed rather
   than merely initiated. Keep one lifecycle as one process atomic rather than
   splitting its start and completion into disconnected static atomics.
4. For process mode, `process_intent` states only the natural-language completion
   intent. It must not contain primitive sequences, evaluator predicates, GT, or
   verification answers. Use null for state mode.
5. Do not output primitive calls, instance IDs, invented objects, or time steps.
6. Use 1-6 atomics and exact AVAILABLE OBJECT CLASSES in object fields.

Return strict JSON only:
{{"atomic_tasks":[{{"id":1,"instruction":"...","manipulated_object":"object_class","target_object":null,"completion_mode":"state|process","process_intent":null}}]}}

ORIGINAL TASK: {task}
AVAILABLE OBJECT CLASSES: {json.dumps(objects)}
PROGRAMAGENT ACTION NAMES: {json.dumps(actions_payload['actions'])}
"""
    call = client.generate(
        prompt,
        max_tokens=int(llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]),
        seed=llm_config.get("seed"),
        instructions="Return only the requested strict TaskAgent JSON object.",
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
        mode = item.get("completion_mode")
        intent = item.get("process_intent")
        if item.get("id") != expected_id or not isinstance(instruction, str) or not instruction.strip():
            return [], call, f"atomic {expected_id} has invalid id/instruction"
        if forbidden.match(instruction):
            return [], call, f"atomic {expected_id} is a forbidden navigation task"
        if manipulated not in available:
            return [], call, f"atomic {expected_id} manipulated object unavailable: {manipulated}"
        if target is not None and target not in available:
            return [], call, f"atomic {expected_id} target unavailable: {target}"
        if mode not in {"state", "process"}:
            return [], call, f"atomic {expected_id} has invalid completion_mode"
        if mode == "process" and (not isinstance(intent, str) or not intent.strip()):
            return [], call, f"atomic {expected_id} process_intent is required"
        if mode == "state" and intent is not None:
            return [], call, f"atomic {expected_id} state process_intent must be null"
        validated.append(
            {
                "id": expected_id,
                "instruction": instruction.strip(),
                "manipulated_object": manipulated,
                "target_object": target,
                "completion_mode": mode,
                "process_intent": intent.strip() if isinstance(intent, str) else None,
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
    compact: bool,
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    prompt = f"""You are the HPAF ProgramAgent for VirtualHome.
Compile only the current object-centric atomic into a short executable program.
Do not redo earlier atomics or plan future atomics. Return strict JSON only:
{{"plan_brief":"...","program":"# comments\\nfind('object')\\n..."}}

ORIGINAL TASK: {original_task}
CURRENT ATOMIC: {json.dumps(atomic_task, ensure_ascii=False)}
CURRENT STATE: {state}
AVAILABLE OBJECT CLASSES: {json.dumps(objects)}
PRIMITIVE CALLS: {action_documentation(actions_payload, compact=compact)}

{program_rules(compact=compact)}"""
    call = client.generate(
        prompt,
        max_tokens=int(llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]),
        seed=llm_config.get("seed"),
        instructions="Return only the requested strict atomic ProgramAgent JSON object.",
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
    failed_actions: List[Dict[str, Any]],
    typed_errors: List[Dict[str, Any]],
    verifier_result: Dict[str, Any],
    llm_config: Dict[str, Any],
    compact: bool,
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    context_label = "FAILED ACTIONS" if compact else "CURRENT-ATOMIC EXECUTION TRACE"
    prompt = f"""You are the HPAF ProgramAgent performing the single allowed
local repair for one current atomic. Repair from current state. Do not replay
successful work blindly or plan future atomics. Return strict JSON only:
{{"repair_brief":"...","program":"# repair\\nfind('object')\\n..."}}

ORIGINAL TASK: {original_task}
CURRENT ATOMIC: {json.dumps(atomic_task, ensure_ascii=False)}
CURRENT STATE: {state}
PREVIOUS ATTEMPTED PROGRAM: {previous_program or '<invalid>'}
{context_label}: {json.dumps(failed_actions, ensure_ascii=False)}
TYPED ERRORS: {json.dumps(typed_errors, ensure_ascii=False)}
PREVIOUS VERIFIER: {json.dumps(verifier_result, ensure_ascii=False)}
AVAILABLE OBJECT CLASSES: {json.dumps(objects)}
PRIMITIVE CALLS: {action_documentation(actions_payload, compact=compact)}

{program_rules(compact=compact)}"""
    call = client.generate(
        prompt,
        max_tokens=int(llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]),
        seed=llm_config.get("seed"),
        instructions="Return only the requested strict Retry-1 JSON object.",
    )
    parsed, error = parse_program_json(call.output_text)
    return parsed or {}, call, error

