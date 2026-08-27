from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient
from experiments.progprompt_vh.adapters.paths import PROGPROMPT_ROOT


ACTION_IMPORT = (
    "from actions import turnright, turnleft, walkforward, walktowards <obj>, "
    "walk <obj>, run <obj>, grab <obj>, switchon <obj>, switchoff <obj>, "
    "open <obj>, close <obj>, lookat <obj>, sit <obj>, standup, find <obj>, "
    "turnto <obj>, drink <obj>, pointat <obj>, watch <obj>, "
    "putin <obj> <obj>, putback <obj> <obj>"
)

PRIMITIVE_API = """Available VirtualHome primitive calls (use exactly these lowercase names):
- turnright(), turnleft(), walkforward(), standup()
- walktowards('object'), walk('object'), run('object'), find('object'), turnto('object')
- grab('object'), open('object'), close('object')
- switchon('object'), switchoff('object')
- lookat('object'), sit('object'), drink('object'), pointat('object'), watch('object')
- putin('held_object', 'container'), putback('held_object', 'surface')

Use only object class names present in AVAILABLE OBJECTS. ``find``/``walk`` are
responsible for navigation and grounding. The interpreter binds class names to
scene instance IDs."""


@dataclass
class ParsedJSON:
    value: Optional[Dict[str, Any]]
    error: Optional[str]


def parse_json_object(text: str) -> ParsedJSON:
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
        return ParsedJSON(None, "no JSON object found")
    try:
        value, _ = json.JSONDecoder().raw_decode(stripped[start:])
    except json.JSONDecodeError as exc:
        return ParsedJSON(None, f"JSON parse failure: {exc}")
    if not isinstance(value, dict):
        return ParsedJSON(None, "top-level JSON value is not an object")
    return ParsedJSON(value, None)


def build_progprompt_prefix(objects: List[str], example_names: List[str]) -> str:
    train_path = (
        PROGPROMPT_ROOT / "data" / "pythonic_plans" / "train_complete_plan_set.json"
    )
    with train_path.open("r", encoding="utf-8") as handle:
        examples = json.load(handle)
    prompt = f"{ACTION_IMPORT}\n\nobjects = {objects}"
    for name in example_names:
        prompt += "\n\n" + examples[name]
    return prompt


def generate_progprompt_program(
    client: ModernLLMClient,
    *,
    task: str,
    objects: List[str],
    prompt_config: Dict[str, Any],
) -> Tuple[str, LLMCall]:
    prefix = build_progprompt_prefix(objects, prompt_config["prompt_examples"])
    function_header = f"def {'_'.join(task.split(' '))}():"
    prompt = f"{prefix}\n\n{function_header}\n\t"
    call = client.generate(
        prompt,
        max_tokens=int(prompt_config["max_tokens"]),
        temperature=float(prompt_config["temperature"]),
        stop=list(prompt_config.get("stop") or []),
        frequency_penalty=float(prompt_config.get("frequency_penalty", 0.0)),
        seed=None,
        instructions=(
            "Complete only the body of the final unfinished ProgPrompt action-DSL "
            "function in the supplied text. Output DSL body lines only: comments, "
            "available action calls, assertions, and indented else recovery calls. "
            "Do not discuss Python syntax, ask questions, use Markdown, repeat earlier "
            "functions, or emit a new def."
        ),
    )
    return call.output_text, call


def decompose_task(
    client: ModernLLMClient,
    *,
    task: str,
    objects: List[str],
    state: str,
    llm_config: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], LLMCall, Optional[str]]:
    prompt = f"""You are the HPAF TaskAgent for a VirtualHome symbolic benchmark.

Decompose the complex household instruction into an ordered list of explicit
semantic atomic tasks. TaskAgent decides WHAT must be achieved; ProgramAgent
will later decide HOW to call primitive actions.

Rules:
1. Each atomic task has one clear semantic operation or subgoal.
2. Do not merge independent target objects into one atomic task.
3. Do not emit primitive API calls or instance IDs.
4. Do not invent objects absent from AVAILABLE OBJECTS.
5. Preserve necessary ordering and do not add optional cleanup unrelated to the instruction.
6. Return strict JSON only, exactly shaped as:
{{"atomic_tasks":[{{"id":1,"task":"..."}}]}}

ORIGINAL TASK:
{task}

AVAILABLE OBJECTS:
{objects}

INITIAL SYMBOLIC SCENE OBSERVATION:
{state or "No agent-local relations are currently visible."}
"""
    call = client.generate(
        prompt,
        max_tokens=int(llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]),
        seed=llm_config.get("seed"),
    )
    parsed = parse_json_object(call.output_text)
    if parsed.error:
        return [], call, parsed.error
    atomic_tasks = parsed.value.get("atomic_tasks")
    if not isinstance(atomic_tasks, list) or not atomic_tasks:
        return [], call, "TaskAgent produced no atomic_tasks list"
    normalized = []
    for index, item in enumerate(atomic_tasks, start=1):
        if not isinstance(item, dict) or not str(item.get("task", "")).strip():
            return [], call, f"Invalid atomic task at index {index}"
        normalized.append({"id": int(item.get("id", index)), "task": str(item["task"]).strip()})
    return normalized, call, None


def generate_atomic_program(
    client: ModernLLMClient,
    *,
    original_task: str,
    atomic_task: Dict[str, Any],
    objects: List[str],
    state: str,
    llm_config: Dict[str, Any],
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    prompt = f"""You are the HPAF ProgramAgent for VirtualHome.

Compile only the CURRENT ATOMIC TASK into a short executable program over the
bounded primitive API. Do not redo already completed atomic tasks and do not
plan future atomic tasks. Use the current symbolic scene to omit actions whose
effects are already true. Output no imports, functions, loops, assertions,
instance IDs, or unsupported calls.

Return strict JSON only:
{{
  "atomic_task": "...",
  "plan_brief": "...",
  "program": "# one concise subgoal comment\\nfind('object')\\n...",
  "completion_conditions": [
    {{"predicate":"STATE","object":"tv","value":"ON"}},
    {{"predicate":"RELATION","subject":"salmon","relation":"INSIDE","object":"fridge"}}
  ]
}}

``completion_conditions`` must contain only effects of this atomic task that
can be checked from a symbolic graph. Use predicate STATE or RELATION. If the
semantic completion is not representable, return an empty list; never use a
ground-truth answer or invent a condition. RELATION values must use VirtualHome
semantics: INSIDE, ON, CLOSE, or HOLDS (character HOLDS object).

ORIGINAL TASK:
{original_task}

CURRENT ATOMIC TASK:
{atomic_task["task"]}

AVAILABLE OBJECTS:
{objects}

CURRENT SYMBOLIC SCENE OBSERVATION:
{state or "No agent-local relations are currently visible."}

{PRIMITIVE_API}
"""
    call = client.generate(
        prompt,
        max_tokens=int(llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]),
        seed=llm_config.get("seed"),
    )
    parsed = parse_json_object(call.output_text)
    if parsed.error:
        return {}, call, parsed.error
    value = parsed.value
    program = value.get("program")
    if not isinstance(program, str) or not program.strip():
        return value, call, "ProgramAgent produced an empty program"
    conditions = value.get("completion_conditions", [])
    if not isinstance(conditions, list):
        return value, call, "completion_conditions is not a list"
    value["completion_conditions"] = conditions
    return value, call, None


def verify_completion_conditions(
    graph: Dict[str, Any], conditions: List[Dict[str, Any]]
) -> Tuple[Optional[bool], List[Dict[str, Any]]]:
    """Check planner-authored effects without consulting benchmark GT goals."""
    if not conditions:
        return None, []
    node_class = {node["id"]: node["class_name"] for node in graph["nodes"]}
    details: List[Dict[str, Any]] = []
    all_satisfied = True
    for condition in conditions:
        predicate = str(condition.get("predicate", "")).upper()
        satisfied = False
        evidence = ""
        if predicate == "STATE":
            object_name = str(condition.get("object", "")).lower()
            state = str(condition.get("value", "")).upper()
            satisfied = any(
                node["class_name"] == object_name and state in node.get("states", [])
                for node in graph["nodes"]
            )
            if satisfied:
                evidence = "direct state"
        elif predicate == "RELATION":
            subject = str(condition.get("subject", "")).lower()
            relation = str(condition.get("relation", "")).upper()
            object_name = str(condition.get("object", "")).lower()
            if relation in {"HOLD", "HOLDS"}:
                satisfied = any(
                    node_class.get(edge["from_id"]) == subject
                    and "HOLD" in edge["relation_type"]
                    and node_class.get(edge["to_id"]) == object_name
                    for edge in graph["edges"]
                )
            elif relation == "HELD":
                # Accept the inverse natural-language form
                # ``object HELD character`` for graph ``character HOLDS object``.
                satisfied = any(
                    node_class.get(edge["from_id"]) == object_name
                    and "HOLD" in edge["relation_type"]
                    and node_class.get(edge["to_id"]) == subject
                    for edge in graph["edges"]
                )
            else:
                satisfied = any(
                    node_class.get(edge["from_id"]) == subject
                    and edge["relation_type"] == relation
                    and node_class.get(edge["to_id"]) == object_name
                    for edge in graph["edges"]
                )
            if satisfied:
                evidence = "direct graph edge"
            elif relation == "CLOSE":
                # A carried object's proximity is encoded indirectly as
                # character--HOLD-->object plus character--CLOSE-->target.
                # This closure uses only the current graph, never benchmark GT.
                character_ids = {
                    node_id
                    for node_id, class_name in node_class.items()
                    if class_name == "character"
                }
                held_subject_ids = {
                    edge["to_id"]
                    for edge in graph["edges"]
                    if edge["from_id"] in character_ids
                    and "HOLD" in edge["relation_type"]
                    and node_class.get(edge["to_id"]) == subject
                }
                carriers = {
                    edge["from_id"]
                    for edge in graph["edges"]
                    if edge["to_id"] in held_subject_ids
                    and "HOLD" in edge["relation_type"]
                }
                satisfied = any(
                    edge["from_id"] in carriers
                    and edge["relation_type"] == "CLOSE"
                    and node_class.get(edge["to_id"]) == object_name
                    for edge in graph["edges"]
                )
                if satisfied:
                    evidence = "derived: carrier HOLDS subject and carrier CLOSE object"
        else:
            details.append({"condition": condition, "satisfied": None, "error": "unsupported predicate"})
            return None, details
        details.append(
            {"condition": condition, "satisfied": satisfied, "evidence": evidence}
        )
        all_satisfied = all_satisfied and satisfied
    return all_satisfied, details
