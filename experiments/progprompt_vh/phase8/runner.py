"""Phase-8 development and frozen-benchmark execution orchestration."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import yaml

from experiments.progprompt_vh.adapters.llm_client import LLMCall
from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.adapters.virtualhome import (
    UnitySession,
    available_object_classes,
)
from experiments.progprompt_vh.phase5.evaluation.official_evaluator import evaluate_task
from experiments.progprompt_vh.phase5.execution import symbolic_state_snapshot
from experiments.progprompt_vh.phase6.dataset import (
    graph_sha256,
    load_final_graph,
    load_initial_graph,
    read_jsonl,
    sha256,
)
from experiments.progprompt_vh.phase6.methods.progprompt import generate_progprompt_program
from experiments.progprompt_vh.phase6.verification.deterministic_evaluator import (
    evaluate_conditions,
)
from experiments.progprompt_vh.phase7.verification.trace_evaluator import (
    evaluate_trace_goal,
)
from experiments.progprompt_vh.phase8.compat_client import Phase8LLMClient
from experiments.progprompt_vh.phase8.execution import Phase8GraphProgramExecutor
from experiments.progprompt_vh.phase8.methods.hpaf_flat import generate_flat_program
from experiments.progprompt_vh.phase8.methods.hpaf_full import (
    generate_atomic_program,
    generate_atomic_tasks,
    generate_repair_program,
)
from experiments.progprompt_vh.phase8.representation import (
    project_relevant_symbolic_state,
)
from experiments.progprompt_vh.phase8.verification.llm_verifier import (
    verify_task_completion,
)


PHASE8_ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase8"
CONFIG_PATH = PHASE8_ROOT / "configs/benchmark.yaml"
ACTION_PATH = PROJECT_ROOT / "experiments/progprompt_vh/phase5/data/graph_supported_actions.json"
DEVELOPMENT_MANIFEST = PROJECT_ROOT / "experiments/progprompt_vh/phase7/data/combined_manifest.json"
FINAL_MANIFEST = PHASE8_ROOT / "data/final_compositional_manifest.json"
METHODS = ["ProgPrompt-Compat", "HPAF-Flat", "HPAF-Full"]
REPRESENTATIONS = {"uncompressed", "compressed"}


BROAD_ROLE = {
    "whole_program_generation": "generation",
    "assertion_verification": "verification",
    "flat_program_agent": "generation",
    "flat_verifier": "verification",
    "task_agent": "generation",
    "atomic_program_agent": "generation",
    "atomic_verifier": "verification",
    "repair_program_agent": "repair",
    "post_repair_verifier": "verification",
}


IMPLEMENTATION_FILES = [
    PHASE8_ROOT / "runner.py",
    PHASE8_ROOT / "compat_client.py",
    PHASE8_ROOT / "execution.py",
    PHASE8_ROOT / "representation.py",
    PHASE8_ROOT / "methods/common.py",
    PHASE8_ROOT / "methods/hpaf_flat.py",
    PHASE8_ROOT / "methods/hpaf_full.py",
    PHASE8_ROOT / "verification/llm_verifier.py",
    CONFIG_PATH,
    ACTION_PATH,
    PROJECT_ROOT / "experiments/progprompt_vh/phase5/execution.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase6/methods/progprompt.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase6/verification/deterministic_evaluator.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase7/verification/trace_evaluator.py",
]


def slug(text: str) -> str:
    return "_".join("".join(char if char.isalnum() else " " for char in text).split()).lower()


def implementation_sha256() -> str:
    payload = [
        (str(path.relative_to(PROJECT_ROOT)), sha256(path))
        for path in IMPLEMENTATION_FILES
    ]
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def load_config() -> Dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def make_client(config: Mapping[str, Any]) -> Phase8LLMClient:
    client = Phase8LLMClient.from_env_spec(config["llm"]["ark"])
    if (
        client.provider != "ark"
        or client.model != "doubao-seed-2-1-pro-260628"
        or client.api_interface != "responses.create"
        or client.extra_body != {"thinking": {"type": "disabled"}}
    ):
        raise RuntimeError("LLM backend/settings differ from the Phase-8 protocol")
    return client


def load_development_entries() -> List[Dict[str, Any]]:
    payload = json.loads(DEVELOPMENT_MANIFEST.read_text(encoding="utf-8"))
    rows = payload["entries"]
    if len(rows) != 29 or len({item["task_id"] for item in rows}) != 29:
        raise RuntimeError("Phase-8 development set must be the frozen Phase-7 29 instances")
    return rows


def load_final_entries() -> List[Dict[str, Any]]:
    payload = json.loads(FINAL_MANIFEST.read_text(encoding="utf-8"))
    rows = payload["entries"]
    if len(rows) != 30 or len({item["task_id"] for item in rows}) != 30:
        raise RuntimeError("Final compositional manifest must contain 30 unique tasks")
    return rows


def _sum(calls: Sequence[LLMCall], field: str) -> Optional[int]:
    values = [getattr(call, field) for call in calls]
    if any(value is None for value in values):
        return None
    return sum(int(value) for value in values)


def _tokens(calls: Sequence[LLMCall]) -> Optional[int]:
    prompt = _sum(calls, "prompt_tokens")
    completion = _sum(calls, "completion_tokens")
    return None if prompt is None or completion is None else prompt + completion


def _inventory(graph: Dict[str, Any]) -> Counter:
    return Counter(
        node["class_name"]
        for node in graph["nodes"]
        if node["class_name"] != "character"
    )


def _new_executor(
    initial_graph: Dict[str, Any],
    actions: Dict[str, Any],
    client: Phase8LLMClient,
    unity_comm,
    config: Mapping[str, Any],
) -> Phase8GraphProgramExecutor:
    return Phase8GraphProgramExecutor(
        initial_graph,
        actions_payload=actions,
        llm_client=client,
        unity_comm=unity_comm,
        seed=int(config["benchmark"]["seed"]),
        state_check_max_tokens=int(config["progprompt"]["assertion_max_tokens"]),
    )


def _event_slice(executor: Phase8GraphProgramExecutor, start: int) -> List[Dict[str, Any]]:
    return [asdict(item) for item in executor.events[start:]]


def _compact_trace(events: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            key: item.get(key)
            for key in ["line", "event", "success", "detail", "compiled_action"]
        }
        for item in events[-30:]
        if item.get("event")
        in {"action", "assert", "recovery_skip", "recovery_unknown", "step_cap"}
    ]


def _failed_actions(events: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            key: item.get(key)
            for key in ["line", "event", "success", "detail", "compiled_action"]
        }
        for item in events
        if item.get("event") in {"action", "step_cap"} and not item.get("success")
    ]


def _relevant_objects(
    task: str,
    objects: Sequence[str],
    explicit: Sequence[Optional[str]] = (),
) -> List[str]:
    selected = {item for item in explicit if item}
    compact_task = re.sub(r"[^a-z0-9]", "", task.lower())
    for obj in objects:
        if re.sub(r"[^a-z0-9]", "", obj.lower()) in compact_task:
            selected.add(obj)
    return sorted(selected)


def _state(
    graph: Dict[str, Any],
    *,
    task: str,
    atomic_task: Mapping[str, Any] | None,
    errors: Sequence[Mapping[str, Any]],
    compact: bool,
) -> str:
    if compact:
        return project_relevant_symbolic_state(
            graph,
            task=task,
            atomic_task=atomic_task,
            recent_errors=errors,
        )
    return symbolic_state_snapshot(graph)


def run_progprompt(
    client: Phase8LLMClient,
    entry: Dict[str, Any],
    initial_graph: Dict[str, Any],
    actions: Dict[str, Any],
    unity_comm,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    roles: List[str] = []
    program, _ = generate_progprompt_program(
        client,
        task=entry["task_text"],
        objects=available_object_classes(initial_graph),
        actions_payload=actions,
        prompt_config=config["progprompt"],
    )
    roles.append("whole_program_generation")
    executor = _new_executor(initial_graph, actions, client, unity_comm, config)
    assertion_start = len(client.calls)
    executor.execute(program)
    assertion_calls = client.calls[assertion_start:]
    roles.extend(["assertion_verification"] * len(assertion_calls))
    artifacts = executor.artifacts()
    assert_events = [
        item for item in artifacts["execution_trace"] if item["event"] == "assert"
    ]
    artifacts.update(
        {
            "generated_program": program,
            "atomic_tasks": [],
            "number_of_atomic_tasks": 0,
            "atomic_tasks_attempted": 0,
            "atomic_records": [],
            "retry_count": 0,
            "early_stop_count": 0,
            "planning_errors": [],
            "online_verification_outputs": assert_events,
            "online_verification_count": len(assertion_calls),
            "final_online_done": None,
            "llm_call_roles": roles,
        }
    )
    return artifacts


def run_flat(
    client: Phase8LLMClient,
    entry: Dict[str, Any],
    initial_graph: Dict[str, Any],
    actions: Dict[str, Any],
    unity_comm,
    config: Dict[str, Any],
    *,
    compact: bool,
) -> Dict[str, Any]:
    roles: List[str] = []
    executor = _new_executor(initial_graph, actions, client, unity_comm, config)
    objects = available_object_classes(initial_graph)
    task_contract = {
        "instruction": entry["task_text"],
        "completion_mode": "infer",
        "process_intent": "Infer whether the requested operation needs completed process evidence.",
    }
    initial_observation = _state(
        initial_graph,
        task=entry["task_text"],
        atomic_task=None,
        errors=(),
        compact=compact,
    )
    program_data, _, program_error = generate_flat_program(
        client,
        task=entry["task_text"],
        state=initial_observation,
        objects=objects,
        actions_payload=actions,
        llm_config=config["llm"],
        compact=compact,
    )
    roles.append("flat_program_agent")
    program = str(program_data.get("program", ""))
    planning_errors: List[Dict[str, Any]] = []
    if program_error:
        planning_errors.append({"error_type": "parse_failure", "message": program_error})
    else:
        executor.execute(program)
    execution = executor.artifacts()
    observation = _state(
        executor.final_graph,
        task=entry["task_text"],
        atomic_task=None,
        errors=execution["execution_errors"],
        compact=compact,
    )
    verifier_result, verifier_call, verifier_error = verify_task_completion(
        client,
        atomic_task=task_contract,
        current_symbolic_observation=observation,
        relevant_objects=_relevant_objects(entry["task_text"], objects),
        execution_context={
            "program": program,
            "execution_trace": _compact_trace(execution["execution_trace"]),
            "errors": execution["execution_errors"],
        },
        llm_config=config["llm"],
        compact=compact,
    )
    roles.append("flat_verifier")
    if verifier_error:
        planning_errors.append(
            {"error_type": "verifier_parse_failure", "message": verifier_error}
        )
    execution.update(
        {
            "generated_program": program,
            "atomic_tasks": [],
            "number_of_atomic_tasks": 0,
            "atomic_tasks_attempted": 0,
            "atomic_records": [],
            "retry_count": 0,
            "early_stop_count": 0,
            "planning_errors": planning_errors,
            "flat_initial_observation": initial_observation,
            "online_verification_outputs": [
                {
                    "task_contract": task_contract,
                    "observation": observation,
                    "result": verifier_result,
                    "raw_output": verifier_call.raw_output,
                }
            ],
            "online_verification_count": 1,
            "final_online_done": verifier_result["done"],
            "llm_call_roles": roles,
        }
    )
    return execution


def run_full(
    client: Phase8LLMClient,
    entry: Dict[str, Any],
    initial_graph: Dict[str, Any],
    actions: Dict[str, Any],
    unity_comm,
    config: Dict[str, Any],
    *,
    compact: bool,
) -> Dict[str, Any]:
    roles: List[str] = []
    executor = _new_executor(initial_graph, actions, client, unity_comm, config)
    objects = available_object_classes(initial_graph)
    atomics, task_call, task_error = generate_atomic_tasks(
        client,
        task=entry["task_text"],
        objects=objects,
        actions_payload=actions,
        llm_config=config["llm"],
    )
    roles.append("task_agent")
    planning_errors: List[Dict[str, Any]] = []
    if task_error:
        planning_errors.append(
            {"error_type": "taskagent_parse_failure", "message": task_error}
        )
    records: List[Dict[str, Any]] = []
    programs: List[str] = []
    online_outputs: List[Dict[str, Any]] = []
    retry_count = 0
    early_stop = 1 if task_error else 0

    for atomic in atomics:
        state = _state(
            executor.final_graph,
            task=entry["task_text"],
            atomic_task=atomic,
            errors=(),
            compact=compact,
        )
        event_start = len(executor.events)
        error_start = len(executor.error_events)
        data, _, program_error = generate_atomic_program(
            client,
            original_task=entry["task_text"],
            atomic_task=atomic,
            state=state,
            objects=objects,
            actions_payload=actions,
            llm_config=config["llm"],
            compact=compact,
        )
        roles.append("atomic_program_agent")
        program = str(data.get("program", ""))
        if program_error:
            planning_errors.append(
                {
                    "error_type": "parse_failure",
                    "message": f"Atomic {atomic['id']}: {program_error}",
                }
            )
        else:
            programs.append(f"# atomic {atomic['id']}: {atomic['instruction']}\n{program}")
            executor.execute(program)
        first_trace = _event_slice(executor, event_start)
        first_errors = list(executor.error_events[error_start:])
        if program_error:
            first_errors.append(
                {"error_type": "parse_failure", "message": program_error, "line": ""}
            )
        observation = _state(
            executor.final_graph,
            task=entry["task_text"],
            atomic_task=atomic,
            errors=first_errors,
            compact=compact,
        )
        relevant = _relevant_objects(
            entry["task_text"],
            objects,
            [atomic["manipulated_object"], atomic.get("target_object")],
        )
        first_verifier, first_call, first_verifier_error = verify_task_completion(
            client,
            atomic_task=atomic,
            current_symbolic_observation=observation,
            relevant_objects=relevant,
            execution_context={
                "program": program,
                "execution_trace": _compact_trace(first_trace),
                "errors": first_errors,
            },
            llm_config=config["llm"],
            compact=compact,
        )
        roles.append("atomic_verifier")
        online_outputs.append(
            {
                "atomic_id": atomic["id"],
                "attempt": "initial",
                "observation": observation,
                "result": first_verifier,
                "raw_output": first_call.raw_output,
            }
        )
        if first_verifier_error:
            planning_errors.append(
                {
                    "error_type": "verifier_parse_failure",
                    "message": f"Atomic {atomic['id']}: {first_verifier_error}",
                }
            )

        repair_program = ""
        repair_trace: List[Dict[str, Any]] = []
        repair_errors: List[Dict[str, Any]] = []
        repair_verifier: Optional[Dict[str, Any]] = None
        final_done = bool(first_verifier["done"])
        retry_used = not final_done
        if retry_used:
            retry_count += 1
            repair_state = _state(
                executor.final_graph,
                task=entry["task_text"],
                atomic_task=atomic,
                errors=first_errors,
                compact=compact,
            )
            repair_data, _, repair_error = generate_repair_program(
                client,
                original_task=entry["task_text"],
                atomic_task=atomic,
                state=repair_state,
                objects=objects,
                actions_payload=actions,
                previous_program=program,
                failed_actions=(
                    _failed_actions(first_trace) if compact else _compact_trace(first_trace)
                ),
                typed_errors=first_errors,
                verifier_result=first_verifier,
                llm_config=config["llm"],
                compact=compact,
            )
            roles.append("repair_program_agent")
            repair_program = str(repair_data.get("program", ""))
            repair_event_start = len(executor.events)
            repair_error_start = len(executor.error_events)
            if repair_error:
                planning_errors.append(
                    {
                        "error_type": "repair_parse_failure",
                        "message": f"Atomic {atomic['id']}: {repair_error}",
                    }
                )
            else:
                programs.append(f"# atomic {atomic['id']} Retry-1\n{repair_program}")
                executor.execute(repair_program)
            repair_trace = _event_slice(executor, repair_event_start)
            repair_errors = list(executor.error_events[repair_error_start:])
            if repair_error:
                repair_errors.append(
                    {
                        "error_type": "repair_parse_failure",
                        "message": repair_error,
                        "line": "",
                    }
                )
            repair_observation = _state(
                executor.final_graph,
                task=entry["task_text"],
                atomic_task=atomic,
                errors=repair_errors,
                compact=compact,
            )
            repair_verifier, repair_verifier_call, repair_verifier_error = (
                verify_task_completion(
                    client,
                    atomic_task=atomic,
                    current_symbolic_observation=repair_observation,
                    relevant_objects=relevant,
                    execution_context={
                        "program": repair_program,
                        "execution_trace": _compact_trace(repair_trace),
                        "errors": repair_errors,
                        "previous_verifier": first_verifier,
                    },
                    llm_config=config["llm"],
                    compact=compact,
                )
            )
            roles.append("post_repair_verifier")
            online_outputs.append(
                {
                    "atomic_id": atomic["id"],
                    "attempt": "repair",
                    "observation": repair_observation,
                    "result": repair_verifier,
                    "raw_output": repair_verifier_call.raw_output,
                }
            )
            if repair_verifier_error:
                planning_errors.append(
                    {
                        "error_type": "verifier_parse_failure",
                        "message": f"Atomic {atomic['id']} repair: {repair_verifier_error}",
                    }
                )
            final_done = bool(repair_verifier["done"])

        records.append(
            {
                "atomic_task": atomic,
                "initial_observation": state,
                "initial_program": program,
                "initial_generation_error": program_error,
                "initial_execution_trace": first_trace,
                "initial_typed_errors": first_errors,
                "first_verifier": first_verifier,
                "first_done": bool(first_verifier["done"]),
                "retry_used": retry_used,
                "repair_program": repair_program,
                "repair_execution_trace": repair_trace,
                "repair_typed_errors": repair_errors,
                "repair_verifier": repair_verifier,
                "final_done": final_done,
            }
        )
        if not final_done:
            early_stop = 1
            planning_errors.append(
                {
                    "error_type": "atomic_online_verification_failure",
                    "message": f"Atomic {atomic['id']} remained done=false after Retry-1",
                }
            )
            break

    artifacts = executor.artifacts()
    artifacts.update(
        {
            "generated_program": "\n".join(programs),
            "atomic_tasks": atomics,
            "number_of_atomic_tasks": len(atomics),
            "atomic_tasks_attempted": len(records),
            "atomic_records": records,
            "retry_count": retry_count,
            "early_stop_count": early_stop,
            "planning_errors": planning_errors,
            "online_verification_outputs": online_outputs,
            "online_verification_count": len(online_outputs),
            "final_online_done": bool(records)
            and not early_stop
            and all(item["final_done"] for item in records),
            "taskagent_raw_output": task_call.raw_output,
            "llm_call_roles": roles,
        }
    )
    return artifacts


def _first_error(errors: Sequence[Dict[str, Any]]) -> Tuple[str, str]:
    if not errors:
        return "", ""
    return (
        str(errors[0].get("error_type", "execution_error")),
        str(errors[0].get("message", "")),
    )


def _score(
    final_state: Dict[str, Any],
    artifacts: Dict[str, Any],
    entry: Dict[str, Any],
    initial_graph: Dict[str, Any],
) -> Dict[str, Any]:
    if entry.get("evaluator_type") == "generic_trace":
        record_view = {"graph_execution_trace": artifacts["graph_execution_trace"]}
        return evaluate_trace_goal(record_view, entry["trace_goal"], initial_graph)
    conditions = entry.get("goal_predicates") or entry["semantic_goal"]["conditions"]
    return evaluate_conditions(final_state, conditions)


def _load_entry_initial_graph(entry: Dict[str, Any]) -> Dict[str, Any]:
    return load_initial_graph(entry)


def run_one(
    method: str,
    entry: Dict[str, Any],
    client: Phase8LLMClient,
    unity: UnitySession,
    config: Dict[str, Any],
    *,
    phase: str,
    representation: str,
) -> Dict[str, Any]:
    if method not in METHODS:
        raise ValueError(method)
    if representation not in REPRESENTATIONS:
        raise ValueError(representation)
    started = time.perf_counter()
    call_start = len(client.calls)
    initial_graph = _load_entry_initial_graph(entry)
    live_graph = unity.reset_graph(int(entry["scene"]))
    if _inventory(live_graph) != _inventory(initial_graph):
        missing = _inventory(initial_graph) - _inventory(live_graph)
        extra = _inventory(live_graph) - _inventory(initial_graph)
        raise RuntimeError(
            f"Unity/cached class inventory mismatch for {entry['task_id']}: "
            f"missing={missing}, extra={extra}"
        )
    unity_comm = (
        unity.comm if bool(config["virtualhome"].get("render_unity_actions", False)) else None
    )
    compact = representation == "compressed"
    if method == "ProgPrompt-Compat":
        artifacts = run_progprompt(
            client, entry, initial_graph, json.loads(ACTION_PATH.read_text()), unity_comm, config
        )
    elif method == "HPAF-Flat":
        artifacts = run_flat(
            client,
            entry,
            initial_graph,
            json.loads(ACTION_PATH.read_text()),
            unity_comm,
            config,
            compact=compact,
        )
    else:
        artifacts = run_full(
            client,
            entry,
            initial_graph,
            json.loads(ACTION_PATH.read_text()),
            unity_comm,
            config,
            compact=compact,
        )

    final_state = artifacts.pop("final_state")
    exec_ratio = float(artifacts.pop("Exec"))
    semantic = _score(final_state, artifacts, entry, initial_graph)
    official: Dict[str, Any] = {}
    if entry.get("has_final_state") and entry.get("final_state_source"):
        official = evaluate_task(
            final_state=final_state,
            ground_truth_final_state=load_final_graph(entry),
            initial_state=initial_graph,
            exec_ratio=exec_ratio,
        )
    calls = client.calls[call_start:]
    roles = artifacts.pop("llm_call_roles")
    if len(calls) != len(roles) or any(role not in BROAD_ROLE for role in roles):
        raise RuntimeError(
            f"Incomplete LLM call-role accounting for {entry['task_id']}/{method}: "
            f"calls={len(calls)} roles={len(roles)}"
        )
    tagged_calls = [
        {"call_role": role, "broad_role": BROAD_ROLE[role], **call.to_dict()}
        for call, role in zip(calls, roles)
    ]
    grouped = {
        name: [
            call
            for call, role in zip(calls, roles)
            if BROAD_ROLE[role] == name
        ]
        for name in ["generation", "verification", "repair"]
    }
    errors = artifacts.pop("planning_errors") + artifacts.pop("execution_errors")
    error_type, error_message = _first_error(errors)
    timestamp = datetime.now(timezone.utc).isoformat()
    total_prompt = _sum(calls, "prompt_tokens")
    total_completion = _sum(calls, "completion_tokens")
    task_manifest_sha = sha256(
        FINAL_MANIFEST if phase == "formal" else DEVELOPMENT_MANIFEST
    )
    return {
        "run_id": (
            f'{phase}_{timestamp.replace(":", "").replace("+", "_")}_'
            f"{slug(method)}_{slug(entry['task_id'])}"
        ),
        "phase": phase,
        "representation": representation,
        "timestamp": timestamp,
        "task_id": entry["task_id"],
        "task": entry["task_text"],
        "split": entry.get("official_split", "synthetic_composition"),
        "scene": entry["scene"],
        "goal_count": entry.get("goal_count"),
        "method": method,
        "provider": client.provider,
        "model": client.model,
        "api_interface": client.api_interface,
        "temperature": float(config["llm"]["temperature"]),
        "thinking": "disabled",
        "max_tokens": int(config["llm"]["max_tokens"]),
        "initial_state_sha256": graph_sha256(initial_graph),
        "task_manifest_sha256": task_manifest_sha,
        "action_set_sha256": sha256(ACTION_PATH),
        "implementation_sha256": implementation_sha256(),
        "generated_programs": (
            artifacts.get("atomic_records")
            if method == "HPAF-Full"
            else [artifacts.get("generated_program", "")]
        ),
        "generated_program": artifacts.pop("generated_program"),
        "atomic_tasks": artifacts.pop("atomic_tasks"),
        "number_of_atomic_tasks": artifacts.pop("number_of_atomic_tasks"),
        "atomic_tasks_attempted": artifacts.pop("atomic_tasks_attempted"),
        "atomic_records": artifacts.pop("atomic_records"),
        "retry_count": artifacts.pop("retry_count"),
        "early_stop_count": artifacts.pop("early_stop_count"),
        "online_verification_calls": [
            item for item in tagged_calls if item["broad_role"] == "verification"
        ],
        "online_verification_outputs": artifacts.pop("online_verification_outputs"),
        "online_verification_count": artifacts.pop("online_verification_count"),
        "final_online_done": artifacts.pop("final_online_done"),
        "execution_trace": artifacts.pop("execution_trace"),
        "graph_execution_trace": artifacts.pop("graph_execution_trace"),
        "compiled_virtualhome_actions": artifacts.pop("compiled_virtualhome_actions"),
        "program_length": artifacts.pop("program_length"),
        **semantic,
        "official_SR": official.get("SR"),
        "official_GCR": official.get("GCR"),
        "official_PSR": official.get("PSR"),
        "official_Precision": official.get("Precision"),
        "Exec": exec_ratio,
        "generation_calls": len(grouped["generation"]),
        "verification_calls": len(grouped["verification"]),
        "repair_calls": len(grouped["repair"]),
        "total_calls": len(calls),
        "generation_prompt_tokens": _sum(grouped["generation"], "prompt_tokens"),
        "generation_completion_tokens": _sum(grouped["generation"], "completion_tokens"),
        "verification_prompt_tokens": _sum(grouped["verification"], "prompt_tokens"),
        "verification_completion_tokens": _sum(grouped["verification"], "completion_tokens"),
        "repair_prompt_tokens": _sum(grouped["repair"], "prompt_tokens"),
        "repair_completion_tokens": _sum(grouped["repair"], "completion_tokens"),
        "repair_tokens": _tokens(grouped["repair"]),
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": (
            None
            if total_prompt is None or total_completion is None
            else total_prompt + total_completion
        ),
        "planning_latency": sum(
            call.latency_s for call in grouped["generation"] + grouped["repair"]
        ),
        "verification_latency": sum(
            call.latency_s for call in grouped["verification"]
        ),
        "total_llm_latency": sum(call.latency_s for call in calls),
        "wall_clock_total_s": time.perf_counter() - started,
        "llm_call_records": tagged_calls,
        "raw_prompts": [
            {"role": role, "instructions": call.instructions, "input": call.prompt}
            for call, role in zip(calls, roles)
        ],
        "raw_model_outputs": [
            {"role": role, "output": call.raw_output}
            for call, role in zip(calls, roles)
        ],
        "error_type": error_type,
        "error_message": error_message,
        "errors": errors,
        **artifacts,
    }


def load_existing(output_root: Path) -> Dict[Tuple[str, str], Dict[str, Any]]:
    path = output_root / "raw_runs.jsonl"
    if not path.exists():
        return {}
    result: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in read_jsonl(path):
        pair = (row["task_id"], row["method"])
        if pair in result:
            raise RuntimeError(f"Duplicate run pair in {path}: {pair}")
        result[pair] = row
    return result


def save_run(output_root: Path, record: Dict[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    runs = output_root / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f'{slug(record["method"])}__{slug(record["task_id"])}.json'
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing run: {path}")
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (output_root / "raw_runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def validate_complete_records(
    rows: Iterable[Dict[str, Any]],
    task_ids: Sequence[str],
    methods: Sequence[str],
    *,
    phase: str,
) -> None:
    rows = list(rows)
    expected = {(task_id, method) for task_id in task_ids for method in methods}
    actual = {(row["task_id"], row["method"]) for row in rows}
    if actual != expected or len(rows) != len(expected):
        raise RuntimeError(
            f"Run matrix incomplete: expected={len(expected)} actual={len(rows)} "
            f"missing={sorted(expected-actual)} extra={sorted(actual-expected)}"
        )
    required = {
        "final_semantic_SR",
        "semantic_GCR",
        "Exec",
        "total_calls",
        "total_tokens",
        "llm_call_records",
    }
    for row in rows:
        missing = sorted(required - set(row))
        if row.get("phase") != phase or missing:
            raise RuntimeError(
                f"Invalid record {row.get('task_id')}/{row.get('method')}: missing={missing}"
            )


def run_matrix(
    *,
    entries: Sequence[Dict[str, Any]],
    methods: Sequence[str],
    output_root: Path,
    phase: str,
    representation: str,
) -> List[Dict[str, Any]]:
    config = load_config()
    task_ids = [item["task_id"] for item in entries]
    if len(task_ids) != len(set(task_ids)):
        raise RuntimeError("Requested matrix contains duplicate task IDs")
    if len(methods) != len(set(methods)) or any(item not in METHODS for item in methods):
        raise RuntimeError("Requested matrix contains duplicate/unknown methods")
    existing = load_existing(output_root)
    expected = {(task_id, method) for task_id in task_ids for method in methods}
    if not set(existing) <= expected:
        raise RuntimeError("Existing output contains an out-of-matrix task-method pair")
    if len(existing) < len(expected):
        client = make_client(config)
        vh = config["virtualhome"]
        with UnitySession(
            PROJECT_ROOT / vh["executable"],
            int(vh["port"]),
            bool(vh["no_graphics"]),
        ) as unity:
            for entry in entries:
                for method in methods:
                    pair = (entry["task_id"], method)
                    if pair in existing:
                        continue
                    print(
                        f"RUN {phase}/{representation} {method} :: {entry['task_id']}",
                        flush=True,
                    )
                    row = run_one(
                        method,
                        entry,
                        client,
                        unity,
                        config,
                        phase=phase,
                        representation=representation,
                    )
                    save_run(output_root, row)
                    existing[pair] = row
    rows = [existing[pair] for pair in sorted(expected)]
    validate_complete_records(rows, task_ids, methods, phase=phase)
    return rows

