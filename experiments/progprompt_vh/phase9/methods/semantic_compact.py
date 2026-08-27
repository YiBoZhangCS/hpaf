"""Semantic-preserving boilerplate/schema compression for the Phase-8 methods."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient
from experiments.progprompt_vh.phase6.methods.common import (
    parse_json_object,
    parse_program_json,
)


PROCESS_RULE = (
    "Process contract: if the request denotes a completed process, emit its full "
    "executable lifecycle, including the terminal operation after activation when "
    "closure is required. A requested interaction needs a successful interaction "
    "event. Preserve object/device preconditions. Use no invented wait/time/actions."
)

PROGRAM_RULES = f"""Execution invariants:
1. Listed lowercase calls/classes only. Stand up before navigation if seated/lying.
2. Before interact(X), establish CLOSE(X) with find/walk immediately beforehand and
preserve it; never align an unrelated object between alignment and interaction.
3. grab(src): close + accessible + free hand; open its container only when needed.
4. Transfer: align src > grab src > align dst > satisfy dst state > put src. Never
align dst before acquisition. putin/putback require held(src)+close(dst); open an
openable putin target. Movement invalidates prior proximity.
5. Do not repeat satisfied open/close/switch states. Repair the typed failed
precondition before retrying the failed interaction.
6. No direct heat/wash/eat/use/wait primitives. Comments may organize output; no
assertions, functions, loops, instance IDs, evaluator predicates, or success claims.
{PROCESS_RULE}"""


def action_documentation(actions_payload: Dict[str, Any]) -> str:
    return ", ".join(
        f"{name}({','.join(['obj'] * int(actions_payload['arity'][name]))})"
        for name in actions_payload["actions"]
    )


def generate_flat_program(
    client: ModernLLMClient, *, task: str, state: str, objects: List[str],
    actions_payload: Dict[str, Any], llm_config: Dict[str, Any], compact: bool,
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    del compact
    prompt = f"""HPAF VirtualHome ProgramAgent. Compile the whole task into one
complete executable program; infer static-state versus completed-process intent.
Return strict JSON: {{"plan_brief":"...","program":"# comments\\nfind('object')\\n..."}}
TASK: {task}
STATE: {state}
OBJECT CLASSES: {json.dumps(objects)}
CALLS: {action_documentation(actions_payload)}
{PROGRAM_RULES}"""
    call = client.generate(
        prompt, max_tokens=int(llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]), seed=llm_config.get("seed"),
        instructions="Return only the requested strict ProgramAgent JSON object.",
    )
    parsed, error = parse_program_json(call.output_text)
    return parsed or {}, call, error


def generate_atomic_tasks(
    client: ModernLLMClient, *, task: str, objects: List[str],
    actions_payload: Dict[str, Any], llm_config: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], LLMCall, Optional[str]]:
    prompt = f"""HPAF VirtualHome TaskAgent. Decompose WHAT is required into the
fewest ordered object-centric semantic operations; ProgramAgent handles navigation
and preconditions.
Rules: (1) one operation per atomic, centered on one manipulated object and optional
target; (2) no locate/find/walk atomics, and prerequisite open/close is not an atomic;
(3) completion_mode=state for persistent state/relation, process for a completed
operation; keep one lifecycle in one process atomic; (4) process_intent is natural
language completion intent only, never calls/evaluator/GT/answers; null for state;
(5) no primitive calls, IDs, invented objects, or time; (6) 1-6 atomics using exact
available object classes.
JSON only: {{"atomic_tasks":[{{"id":1,"instruction":"...","manipulated_object":"class","target_object":null,"completion_mode":"state|process","process_intent":null}}]}}
TASK: {task}
OBJECT CLASSES: {json.dumps(objects)}
ACTION NAMES: {json.dumps(actions_payload['actions'])}"""
    call = client.generate(
        prompt, max_tokens=int(llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]), seed=llm_config.get("seed"),
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
        validated.append({
            "id": expected_id, "instruction": instruction.strip(),
            "manipulated_object": manipulated, "target_object": target,
            "completion_mode": mode,
            "process_intent": intent.strip() if isinstance(intent, str) else None,
        })
    return validated, call, None


def generate_atomic_program(
    client: ModernLLMClient, *, original_task: str, atomic_task: Dict[str, Any],
    state: str, objects: List[str], actions_payload: Dict[str, Any],
    llm_config: Dict[str, Any], compact: bool,
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    del compact
    prompt = f"""HPAF VirtualHome ProgramAgent. Compile only the current atomic into
a short executable program; do not redo earlier or plan future atomics.
JSON only: {{"plan_brief":"...","program":"# comments\\nfind('object')\\n..."}}
ORIGINAL TASK: {original_task}
ATOMIC: {json.dumps(atomic_task, ensure_ascii=False)}
STATE: {state}
OBJECT CLASSES: {json.dumps(objects)}
CALLS: {action_documentation(actions_payload)}
{PROGRAM_RULES}"""
    call = client.generate(
        prompt, max_tokens=int(llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]), seed=llm_config.get("seed"),
        instructions="Return only the requested strict atomic ProgramAgent JSON object.",
    )
    parsed, error = parse_program_json(call.output_text)
    return parsed or {}, call, error


def generate_repair_program(
    client: ModernLLMClient, *, original_task: str, atomic_task: Dict[str, Any],
    state: str, objects: List[str], actions_payload: Dict[str, Any],
    previous_program: str, failed_actions: List[Dict[str, Any]],
    typed_errors: List[Dict[str, Any]], verifier_result: Dict[str, Any],
    llm_config: Dict[str, Any], compact: bool,
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    del compact
    prompt = f"""HPAF VirtualHome ProgramAgent, single local Retry-1 for the current
atomic. Repair from current state; do not blindly replay successes or plan future atomics.
JSON only: {{"repair_brief":"...","program":"# repair\\nfind('object')\\n..."}}
ORIGINAL TASK: {original_task}
ATOMIC: {json.dumps(atomic_task, ensure_ascii=False)}
STATE: {state}
PREVIOUS PROGRAM: {previous_program or '<invalid>'}
CURRENT-ATOMIC TRACE: {json.dumps(failed_actions, ensure_ascii=False)}
TYPED ERRORS: {json.dumps(typed_errors, ensure_ascii=False)}
VERIFIER: {json.dumps(verifier_result, ensure_ascii=False)}
OBJECT CLASSES: {json.dumps(objects)}
CALLS: {action_documentation(actions_payload)}
{PROGRAM_RULES}"""
    call = client.generate(
        prompt, max_tokens=int(llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]), seed=llm_config.get("seed"),
        instructions="Return only the requested strict Retry-1 JSON object.",
    )
    parsed, error = parse_program_json(call.output_text)
    return parsed or {}, call, error

