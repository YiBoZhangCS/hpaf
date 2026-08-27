"""Phase-10 Structured IR TaskAgent and atomic ProgramAgent prompts."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient
from experiments.progprompt_vh.phase6.methods.common import parse_program_json
from experiments.progprompt_vh.phase8.methods.common import (
    action_documentation,
    program_rules,
)
from experiments.progprompt_vh.phase10.ir import parse_ir_json, validate_ir


TASK_AGENT_METHOD = """You are the HPAF TaskAgent for VirtualHome. Convert the natural-language instruction into the fewest Structured Semantic Atomic Tasks.

Layer-1 definition:
- ONE ATOMIC = ONE DOMINANT SEMANTIC COMMITMENT: one independently meaningful and verifiable state transition or completed process around a focal object.
- An atomic is not one primitive action. Navigation, find, walk, alignment, open/close prerequisites, loading, activation, and retrieval belong inside an atomic when they serve the same semantic commitment.
- Use 1-6 atomics. Use exact scene object class names. Do not output primitive calls, instance IDs, evaluator predicates, a reference program, or hidden final-state facts.

Allowed types only:
- TRANSFER: focal object reaches target; state completion; source may be null.
- STATE_CHANGE: requested persistent state of focal object; state completion.
- PROCESS: a requested lifecycle is completed for focal object; process completion. The appliance/tool is normally target, not the focal object.
- MULTI_OBJECT_COUPLED: only when multiple objects jointly form one condition that cannot naturally be separated.
- INTERACTION: meaningful non-persistent interaction such as watch TV; process completion.

Focal-object and grouping rules:
- `focal_object` is exactly one class copied verbatim from SCENE OBJECT CLASSES. Never concatenate classes and never put a comma-separated list in this field.
- For MULTI_OBJECT_COUPLED, choose one principal participant as `focal_object` and name every coupled participant in `semantic_goal`.
- Use MULTI_OBJECT_COUPLED when collecting, gathering, or staging multiple requested objects together at one target is itself a joint semantic checkpoint. Do not use it merely because unrelated objects appear in the instruction.
- A PROCESS owns its loading/activation/completion lifecycle. Do not emit a separate TRANSFER merely to load the process object. Emit a later TRANSFER only when the instruction requests a distinct post-process delivery checkpoint.

Dependency and terminal rules:
- `depends_on` expresses only required semantic predecessors and forms a DAG. Never use list position as a substitute for dependency.
- A clause such as "then" normally creates a dependency when the later checkpoint requires predecessor state.
- A final requested device/container state is a terminal constraint, not a separate atomic. Do not create close/switchoff atomics merely to restore final state.
- A process atomic includes its complete lifecycle as one commitment; do not split load/start/stop/retrieve into primitive-like atomics.

Return strict JSON only with this exact shape:
{"atomic_tasks":[{"id":"A1","type":"TRANSFER|STATE_CHANGE|PROCESS|MULTI_OBJECT_COUPLED|INTERACTION","focal_object":"exactly-one-scene-class","source":null,"target":"class-or-null","completion_mode":"state|process","semantic_goal":"independently verifiable semantic commitment","depends_on":[]}],"terminal_constraints":[{"predicate":"STATE","object":"class","value":"OFF|ON|OPEN|CLOSED","semantic_goal":"final required state"}]}

For a relational terminal constraint use predicate=RELATION with subject, relation, object, and semantic_goal. Return an empty terminal_constraints list when none are explicitly required by the instruction."""


ATOMIC_PROGRAM_METHOD = """Compile only the current Structured Semantic Atomic Task from fresh state. The atomic may require repeated Alignment -> Interaction pairs. Complete its dominant semantic commitment without planning later atomics. If terminal constraints are attached, this is the last ready atomic: preserve or restore them by task end without turning them into high-level atomics."""


def task_agent_prompt(*, task: str, objects: List[str]) -> str:
    return (
        f"{TASK_AGENT_METHOD}\n\n"
        f"NATURAL-LANGUAGE INSTRUCTION: {task}\n"
        f"SCENE OBJECT CLASSES: {json.dumps(objects)}\n"
    )


def generate_structured_ir(
    client: ModernLLMClient,
    *,
    task: str,
    objects: List[str],
    llm_config: Dict[str, Any],
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    call = client.generate(
        task_agent_prompt(task=task, objects=objects),
        max_tokens=int(llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]),
        seed=llm_config.get("seed"),
        instructions="Return only the requested strict Structured Atomic Task IR JSON object.",
    )
    parsed, parse_error = parse_ir_json(call.output_text)
    if parse_error or parsed is None:
        return {}, call, f"parse_failure: {parse_error}"
    validation = validate_ir(parsed, objects)
    if not validation.valid:
        summary = "; ".join(
            f"{item.category}:{item.path}:{item.message}" for item in validation.issues
        )
        return {}, call, f"validator_rejection: {summary}"
    normalized = {
        "atomic_tasks": [dict(item) for item in parsed["atomic_tasks"]],
        "terminal_constraints": [dict(item) for item in parsed["terminal_constraints"]],
        "dependency_depth": validation.dependency_depth,
    }
    return normalized, call, None


def generate_atomic_program(
    client: ModernLLMClient,
    *,
    original_task: str,
    atomic_task: Dict[str, Any],
    terminal_constraints: List[Dict[str, Any]],
    state: str,
    objects: List[str],
    actions_payload: Dict[str, Any],
    llm_config: Dict[str, Any],
    compact: bool,
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    execution_contract = dict(atomic_task)
    execution_contract["terminal_constraints_at_task_end"] = terminal_constraints
    prompt = f"""You are the HPAF ProgramAgent for VirtualHome.
{ATOMIC_PROGRAM_METHOD}

Return strict JSON only:
{{"plan_brief":"...","program":"# comments\\nfind('object')\\n..."}}

ORIGINAL INSTRUCTION: {original_task}
CURRENT STRUCTURED ATOMIC: {json.dumps(execution_contract, ensure_ascii=False)}
FRESH CURRENT STATE: {state}
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


def prompt_bundle_text() -> str:
    """Stable method/prompt material used by the pre-run freeze lock."""
    return "\n\n".join([TASK_AGENT_METHOD, ATOMIC_PROGRAM_METHOD, program_rules(compact=False)])
