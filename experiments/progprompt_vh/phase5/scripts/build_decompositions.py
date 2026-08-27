#!/usr/bin/env python3
"""Call TaskAgent once per task and freeze one validated decomposition set."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from experiments.progprompt_vh.adapters.llm_client import ModernLLMClient
from experiments.progprompt_vh.methods.planners import parse_json_object


ROOT = Path(__file__).resolve().parents[4]
PHASE5 = ROOT / "experiments/progprompt_vh/phase5"
CONFIG = PHASE5 / "configs/benchmark.yaml"
SEMANTIC = PHASE5 / "data/semantic_goals_test_unseen.json"
ACTIONS = PHASE5 / "data/graph_supported_actions.json"
INITIAL_GRAPH = ROOT / "experiments/progprompt_vh/results/environment_initial_state.json"
OUTPUT = PHASE5 / "data/frozen_decompositions.json"
STAGING = PHASE5 / "results/decomposition_freeze_calls.jsonl"

DISALLOWED_ATOMIC_START = re.compile(
    r"^(locate|find|walk|navigate|move|position|open|close|wait)\b", re.IGNORECASE
)
DISALLOWED_TEXT = re.compile(r"\b(wait|sleep for|minutes?|seconds?|automatically)\b", re.IGNORECASE)
ALLOWED_RELATIONS = {"INSIDE", "ON", "HOLDS"}
ALLOWED_STATES = {"ON", "OFF", "OPEN", "CLOSED", "HEATED", "WASHED"}


def canonical_condition(condition: Dict[str, Any]) -> Tuple[str, ...]:
    predicate = str(condition.get("predicate", "")).upper()
    if predicate == "STATE":
        return (
            "STATE",
            str(condition.get("object", "")).lower(),
            str(condition.get("value", "")).upper(),
        )
    if predicate == "RELATION":
        return (
            "RELATION",
            str(condition.get("subject", "")).lower(),
            str(condition.get("relation", "")).upper(),
            str(condition.get("object", "")).lower(),
        )
    return (predicate,)


def taskagent_prompt(
    task_spec: Dict[str, Any], objects: List[str], actions: List[str]
) -> str:
    frozen_goals = [
        {key: value for key, value in condition.items() if key != "rationale"}
        for condition in task_spec["conditions"]
    ]
    return f"""You are the HPAF TaskAgent for a controlled VirtualHome experiment.

Decompose WHAT the original instruction requires into ordered semantic atomic
tasks. A separate ProgramAgent will handle HOW: object finding, walking,
alignment, hand management, and prerequisite open/close actions.

Rules:
1. Each atomic task has exactly one primary persistent graph state transition.
2. Never create Locate/Find/Walk/Navigate/Move/Position atomic tasks.
3. Never make OPEN/CLOSE a separate atomic task when it is only a prerequisite.
4. Never create waiting, elapsed-time, or simulator-unrepresentable tasks.
5. Prefer the fewest semantic atomics. A grab/HOLDS transition is allowed only
   when it is a meaningful dependency; do not split every interaction mechanically.
6. Every FROZEN TASK GOAL must appear exactly once as a primary goal. You may
   add an earlier HOLDS transition when semantically useful, but must not replace,
   weaken, or invent an alternative to a frozen goal.
7. Use only object classes in AVAILABLE OBJECTS. Do not use instance IDs, ground-
   truth final graphs, primitive calls, or task-specific cleanup.
8. Allowed primary predicates are STATE with values {sorted(ALLOWED_STATES)}, or
   RELATION with values {sorted(ALLOWED_RELATIONS)}. CLOSE and room location are
   ProgramAgent preconditions, not semantic atomic goals.
9. Condition schemas are exact. A STATE condition has exactly the semantic keys
   {{"predicate":"STATE","object":"...","value":"ON"}}. A RELATION condition
   has exactly the semantic keys {{"predicate":"RELATION","subject":"...",
   "relation":"INSIDE","object":"..."}}. For RELATION, never put the relation
   name under `value` and never use `target_object`.
10. Return 1-4 atomic tasks as strict JSON only, exactly:
{{"atomic_tasks":[{{"id":1,"instruction":"...","primary_goal_condition":{{"predicate":"STATE","object":"tv","value":"ON"}},"supporting_conditions":[]}}]}}

ORIGINAL TASK:
{task_spec['task']}

FROZEN TASK GOALS (conjunctive and immutable):
{json.dumps(frozen_goals, ensure_ascii=False)}

ONTOLOGY AMBIGUITY ALREADY DISCLOSED BY THE PROTOCOL:
{task_spec['ambiguity']}

AVAILABLE OBJECTS:
{json.dumps(objects)}

SHARED PRIMITIVE ACTION NAMES (ProgramAgent only; do not output calls):
{json.dumps(actions)}
"""


def validate_condition(condition: Any, classes: set[str], context: str) -> Dict[str, Any]:
    if not isinstance(condition, dict):
        raise ValueError(f"{context}: condition is not an object")
    predicate = str(condition.get("predicate", "")).upper()
    if predicate == "STATE":
        obj = str(condition.get("object", "")).lower()
        value = str(condition.get("value", "")).upper()
        if obj not in classes or value not in ALLOWED_STATES:
            raise ValueError(f"{context}: invalid STATE({obj}, {value})")
        return {"predicate": "STATE", "object": obj, "value": value}
    if predicate == "RELATION":
        subject = str(condition.get("subject", "")).lower()
        relation = str(condition.get("relation", "")).upper()
        obj = str(condition.get("object", "")).lower()
        if subject not in classes or obj not in classes or relation not in ALLOWED_RELATIONS:
            raise ValueError(f"{context}: invalid {relation}({subject}, {obj})")
        if relation == "HOLDS" and subject != "character":
            raise ValueError(f"{context}: HOLDS subject must be character")
        return {
            "predicate": "RELATION",
            "subject": subject,
            "relation": relation,
            "object": obj,
        }
    raise ValueError(f"{context}: unsupported predicate {predicate}")


def validate_decomposition(
    raw_value: Dict[str, Any], task_spec: Dict[str, Any], classes: set[str]
) -> List[Dict[str, Any]]:
    atomics = raw_value.get("atomic_tasks")
    if not isinstance(atomics, list) or not 1 <= len(atomics) <= 4:
        raise ValueError("atomic_tasks must contain 1-4 items")
    normalized = []
    primary_keys = []
    for index, atomic in enumerate(atomics, start=1):
        if not isinstance(atomic, dict):
            raise ValueError(f"atomic {index}: not an object")
        instruction = str(atomic.get("instruction", "")).strip()
        if not instruction:
            raise ValueError(f"atomic {index}: empty instruction")
        if DISALLOWED_ATOMIC_START.search(instruction) or DISALLOWED_TEXT.search(instruction):
            raise ValueError(f"atomic {index}: low-level or unrepresentable instruction: {instruction}")
        primary = validate_condition(
            atomic.get("primary_goal_condition"), classes, f"atomic {index} primary"
        )
        primary_key = canonical_condition(primary)
        if primary_key in primary_keys:
            raise ValueError(f"atomic {index}: duplicate primary goal {primary_key}")
        primary_keys.append(primary_key)
        supporting_raw = atomic.get("supporting_conditions", [])
        if not isinstance(supporting_raw, list):
            raise ValueError(f"atomic {index}: supporting_conditions is not a list")
        supporting = [
            validate_condition(item, classes, f"atomic {index} supporting")
            for item in supporting_raw
        ]
        normalized.append(
            {
                "id": index,
                "instruction": instruction,
                "primary_goal_condition": primary,
                "supporting_conditions": supporting,
            }
        )
    frozen_keys = [canonical_condition(item) for item in task_spec["conditions"]]
    for frozen in frozen_keys:
        if primary_keys.count(frozen) != 1:
            raise ValueError(f"frozen task goal must be a primary goal exactly once: {frozen}")
    return normalized


def load_staging() -> Dict[str, Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    if not STAGING.exists():
        return rows
    with STAGING.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if row["task"] in rows:
                    raise RuntimeError(f'Duplicate staged TaskAgent call for {row["task"]}')
                rows[row["task"]] = row
    return rows


def append_staging(row: Dict[str, Any]) -> None:
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    with STAGING.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite frozen decompositions: {OUTPUT}")
    semantic = json.loads(SEMANTIC.read_text(encoding="utf-8"))
    action_payload = json.loads(ACTIONS.read_text(encoding="utf-8"))
    graph = json.loads(INITIAL_GRAPH.read_text(encoding="utf-8"))
    objects = sorted({node["class_name"] for node in graph["nodes"]})
    classes = set(objects)
    with CONFIG.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    llm_config = config["llm"]
    client = ModernLLMClient.from_env_spec(llm_config["ark"])
    if client.provider != "ark" or client.model != "doubao-seed-2-1-pro-260628":
        raise RuntimeError(f"Unexpected TaskAgent backend: {client.provider}/{client.model}")

    staged = load_staging()
    task_specs = semantic["tasks"]
    expected_tasks = [item["task"] for item in task_specs]
    unexpected = sorted(set(staged) - set(expected_tasks))
    if unexpected:
        raise RuntimeError(f"Unexpected task(s) in staging: {unexpected}")

    for ordinal, task_spec in enumerate(task_specs, start=1):
        task = task_spec["task"]
        if task in staged:
            print(f"RESUME staged TaskAgent {ordinal}/10 :: {task}", flush=True)
            continue
        prompt = taskagent_prompt(task_spec, objects, action_payload["actions"])
        print(f"CALL TaskAgent {ordinal}/10 :: {task}", flush=True)
        call = client.generate(
            prompt,
            max_tokens=int(llm_config["max_tokens"]),
            temperature=float(llm_config["temperature"]),
            seed=llm_config.get("seed"),
            instructions="Return only the strict JSON object requested by the TaskAgent protocol.",
        )
        row = {
            "task": task,
            "decomposition_raw_prompt": prompt,
            "decomposition_raw_output": call.raw_output,
            "model": call.model,
            "provider": call.provider,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "llm_call_record": call.to_dict(),
        }
        append_staging(row)
        staged[task] = row

    frozen_rows = []
    validation_errors = []
    for task_spec in task_specs:
        row = staged[task_spec["task"]]
        parsed = parse_json_object(row["decomposition_raw_output"])
        try:
            if parsed.error or parsed.value is None:
                raise ValueError(parsed.error or "empty parsed output")
            atomics = validate_decomposition(parsed.value, task_spec, classes)
        except ValueError as exc:
            validation_errors.append({"task": task_spec["task"], "error": str(exc)})
            continue
        frozen_rows.append(
            {
                "task": task_spec["task"],
                "atomic_tasks": atomics,
                "decomposition_raw_prompt": row["decomposition_raw_prompt"],
                "decomposition_raw_output": row["decomposition_raw_output"],
                "model": row["model"],
                "provider": row["provider"],
                "timestamp": row["timestamp"],
            }
        )
    if validation_errors:
        error_path = PHASE5 / "results/decomposition_validation_errors.json"
        error_path.write_text(
            json.dumps(validation_errors, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(validation_errors, ensure_ascii=False, indent=2), flush=True)
        raise RuntimeError(
            "Decomposition freeze rejected. No frozen file was written; stop and "
            "revise generic rules before a whole-set refreeze."
        )

    prior_attempt = PHASE5 / "results/decomposition_freeze_attempt1_calls.jsonl"
    payload = {
        "schema_version": 1,
        "test_set": semantic["test_set"],
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "taskagent_calls": len(frozen_rows),
        "freeze_attempt": 2 if prior_attempt.exists() else 1,
        "prior_attempt_status": (
            "whole set rejected before freeze because two outputs violated the generic condition schema"
            if prior_attempt.exists()
            else "none"
        ),
        "generation_policy": "exactly one TaskAgent call per test_unseen task; formal runs make zero TaskAgent calls",
        "tasks": frozen_rows,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    print(f"decomposition_sha256={digest}")
    print(f"wrote={OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
