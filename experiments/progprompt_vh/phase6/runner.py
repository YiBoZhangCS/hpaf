"""Locked Phase-6 smoke/formal orchestration and complete cost accounting."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient
from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.adapters.virtualhome import UnitySession, available_object_classes
from experiments.progprompt_vh.phase5.evaluation.official_evaluator import evaluate_task
from experiments.progprompt_vh.phase5.execution import GraphProgramExecutor, symbolic_state_snapshot
from experiments.progprompt_vh.phase6.dataset import (
    ACTION_PATH,
    PHASE6_ROOT,
    graph_sha256,
    load_final_graph,
    load_initial_graph,
    read_jsonl,
    sha256,
)
from experiments.progprompt_vh.phase6.methods.hpaf_flat import generate_flat_program
from experiments.progprompt_vh.phase6.methods.hpaf_full import (
    generate_atomic_program,
    generate_atomic_tasks,
    generate_repair_program,
)
from experiments.progprompt_vh.phase6.methods.progprompt import generate_progprompt_program
from experiments.progprompt_vh.phase6.verification.deterministic_evaluator import evaluate_conditions
from experiments.progprompt_vh.phase6.verification.llm_verifier import verify_task_completion


CONFIG_PATH = PHASE6_ROOT / "configs/benchmark.yaml"
LOCK_PATH = PHASE6_ROOT / "data/protocol_lock.json"
MANIFEST_PATH = PHASE6_ROOT / "data/task_manifest.json"
SEMANTIC_PATH = PHASE6_ROOT / "data/semantic_goals.json"
LONG_PATH = PHASE6_ROOT / "data/long_horizon_manifest.json"
METHODS = ["ProgPrompt", "HPAF-Flat", "HPAF-Full"]

IMPLEMENTATION_FILES = [
    PHASE6_ROOT / "runner.py",
    PHASE6_ROOT / "configs/benchmark.yaml",
    PHASE6_ROOT / "methods/common.py",
    PHASE6_ROOT / "methods/progprompt.py",
    PHASE6_ROOT / "methods/hpaf_flat.py",
    PHASE6_ROOT / "methods/hpaf_full.py",
    PHASE6_ROOT / "verification/llm_verifier.py",
    PHASE6_ROOT / "verification/deterministic_evaluator.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase5/execution.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase5/methods/progprompt_graph_compatible.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase5/evaluation/official_evaluator.py",
    PROJECT_ROOT / "experiments/progprompt_vh/adapters/virtualhome.py",
    PROJECT_ROOT / "experiments/progprompt_vh/adapters/llm_client.py",
]

BROAD_ROLE = {
    "whole_program_generation": "generation",
    "flat_program_agent": "generation",
    "task_agent": "generation",
    "atomic_program_agent": "generation",
    "assertion_verification": "verification",
    "flat_verifier": "verification",
    "atomic_verifier": "verification",
    "post_repair_verifier": "verification",
    "repair_program_agent": "repair",
}


def slug(text: str) -> str:
    return "_".join("".join(char if char.isalnum() else " " for char in text).split()).lower()


def implementation_sha256() -> str:
    payload = [(str(path.relative_to(PROJECT_ROOT)), sha256(path)) for path in IMPLEMENTATION_FILES]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode("utf-8")).hexdigest()


def load_config() -> Dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def verify_protocol_lock(config: Dict[str, Any]) -> Dict[str, Any]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    checks = {
        "task_manifest_sha256": sha256(MANIFEST_PATH),
        "semantic_goals_sha256": sha256(SEMANTIC_PATH),
        "long_horizon_manifest_sha256": sha256(LONG_PATH),
        "action_set_sha256": sha256(ACTION_PATH),
        "phase5_raw_runs_sha256": sha256(PROJECT_ROOT / "experiments/progprompt_vh/phase5/results/raw_runs.jsonl"),
    }
    for source, expected in lock["dataset_source_files"].items():
        actual = sha256(PROJECT_ROOT / source)
        if actual != expected:
            raise RuntimeError(f"Frozen source file changed: {source}")
    mismatch = {key: {"expected": lock.get(key), "actual": value} for key, value in checks.items() if lock.get(key) != value}
    if mismatch:
        raise RuntimeError(f"Frozen Phase-6 protocol mismatch: {json.dumps(mismatch)}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    semantic = json.loads(SEMANTIC_PATH.read_text(encoding="utf-8"))
    long_manifest = json.loads(LONG_PATH.read_text(encoding="utf-8"))
    actions = json.loads(ACTION_PATH.read_text(encoding="utf-8"))
    selected = [item for item in manifest["entries"] if item["filter_status"] == "included"]
    selected_ids = [item["task_id"] for item in selected]
    semantic_ids = [item["task_id"] for item in semantic["tasks"]]
    if selected_ids != semantic_ids or len(selected_ids) != 20:
        raise RuntimeError("Selected task and frozen semantic-goal order mismatch")
    expected_long = [item["task_id"] for item in selected if item["is_long_horizon"]]
    if long_manifest["task_ids"] != expected_long:
        raise RuntimeError("Frozen long-horizon manifest mismatch")
    if config["benchmark"]["methods"] != METHODS:
        raise RuntimeError("Configured method order differs from Phase-6 protocol")
    if actions["actions"] != [
        "close", "drink", "find", "grab", "lookat", "open", "pointat", "putback",
        "putin", "run", "sit", "standup", "switchoff", "switchon", "turnto", "walk", "watch",
    ]:
        raise RuntimeError("Shared action list differs from the frozen 17-action protocol")
    return {"lock": lock, "manifest": manifest, "semantic": semantic, "long": long_manifest, "actions": actions, "selected": selected}


def make_client(config: Dict[str, Any]) -> ModernLLMClient:
    client = ModernLLMClient.from_env_spec(config["llm"]["ark"])
    if client.provider != "ark" or client.model != "doubao-seed-2-1-pro-260628" or client.api_interface != "responses.create" or client.extra_body != {"thinking": {"type": "disabled"}}:
        raise RuntimeError("LLM backend/settings differ from the frozen protocol")
    return client


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
    return Counter(node["class_name"] for node in graph["nodes"] if node["class_name"] != "character")


def _event_slice(executor: GraphProgramExecutor, start: int) -> List[Dict[str, Any]]:
    return [asdict(item) for item in executor.events[start:]]


def _compact_trace(events: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {key: item.get(key) for key in ["line", "event", "success", "detail", "compiled_action"]}
        for item in events[-30:]
        if item.get("event") in {"action", "assert", "recovery_skip", "step_cap"}
    ]


def _relevant_objects(task: str, objects: Sequence[str], explicit: Sequence[Optional[str]] = ()) -> List[str]:
    selected = {item for item in explicit if item}
    tokens = [token for token in re.findall(r"[a-z]+", task.lower()) if len(token) >= 3]
    for obj in objects:
        compact = obj.replace("_", "").lower()
        if compact in task.lower().replace(" ", "") or any(token in compact for token in tokens):
            selected.add(obj)
    return sorted(selected)


def _new_executor(initial_graph: Dict[str, Any], actions: Dict[str, Any], client: ModernLLMClient, unity_comm, config: Dict[str, Any]) -> GraphProgramExecutor:
    return GraphProgramExecutor(
        initial_graph,
        actions_payload=actions,
        llm_client=client,
        unity_comm=unity_comm,
        seed=int(config["benchmark"]["seed"]),
        state_check_max_tokens=int(config["llm"]["state_check_max_tokens"]),
    )


def run_progprompt(client: ModernLLMClient, entry: Dict[str, Any], initial_graph: Dict[str, Any], actions: Dict[str, Any], unity_comm, config: Dict[str, Any]) -> Dict[str, Any]:
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
    assert_events = [item for item in artifacts["execution_trace"] if item["event"] == "assert"]
    artifacts.update({
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
    })
    return artifacts


def run_flat(client: ModernLLMClient, entry: Dict[str, Any], initial_graph: Dict[str, Any], actions: Dict[str, Any], unity_comm, config: Dict[str, Any]) -> Dict[str, Any]:
    roles: List[str] = []
    executor = _new_executor(initial_graph, actions, client, unity_comm, config)
    objects = available_object_classes(initial_graph)
    initial_observation = symbolic_state_snapshot(initial_graph)
    program_data, _, program_error = generate_flat_program(
        client,
        task=entry["task_text"],
        state=initial_observation,
        objects=objects,
        actions_payload=actions,
        llm_config=config["llm"],
    )
    roles.append("flat_program_agent")
    program = str(program_data.get("program", ""))
    planning_errors: List[Dict[str, Any]] = []
    if program_error:
        planning_errors.append({"error_type": "parse_failure", "message": program_error})
    else:
        executor.execute(program)
    execution = executor.artifacts()
    observation = symbolic_state_snapshot(executor.final_graph)
    verifier_result, verifier_call, verifier_error = verify_task_completion(
        client,
        task=entry["task_text"],
        current_symbolic_observation=observation,
        relevant_objects=_relevant_objects(entry["task_text"], objects),
        execution_context={
            "generated_program": program,
            "execution_trace": _compact_trace(execution["execution_trace"]),
            "errors": execution["execution_errors"],
        },
        llm_config=config["llm"],
    )
    roles.append("flat_verifier")
    if verifier_error:
        planning_errors.append({"error_type": "verifier_parse_failure", "message": verifier_error})
    execution.update({
        "generated_program": program,
        "atomic_tasks": [],
        "number_of_atomic_tasks": 0,
        "atomic_tasks_attempted": 0,
        "atomic_records": [],
        "retry_count": 0,
        "early_stop_count": 0,
        "planning_errors": planning_errors,
        "flat_initial_observation": initial_observation,
        "online_verification_outputs": [{"task": entry["task_text"], "observation": observation, "result": verifier_result, "raw_output": verifier_call.raw_output}],
        "online_verification_count": 1,
        "final_online_done": verifier_result["done"],
        "llm_call_roles": roles,
    })
    return execution


def run_full(client: ModernLLMClient, entry: Dict[str, Any], initial_graph: Dict[str, Any], actions: Dict[str, Any], unity_comm, config: Dict[str, Any]) -> Dict[str, Any]:
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
        planning_errors.append({"error_type": "taskagent_parse_failure", "message": task_error})
    records: List[Dict[str, Any]] = []
    programs: List[str] = []
    online_outputs: List[Dict[str, Any]] = []
    retry_count = 0
    early_stop = 1 if task_error else 0

    for atomic in atomics:
        state = symbolic_state_snapshot(executor.final_graph)
        event_start = len(executor.events)
        error_start = len(executor.error_events)
        data, program_call, program_error = generate_atomic_program(
            client,
            original_task=entry["task_text"],
            atomic_task=atomic,
            state=state,
            objects=objects,
            actions_payload=actions,
            llm_config=config["llm"],
        )
        roles.append("atomic_program_agent")
        program = str(data.get("program", ""))
        if program_error:
            planning_errors.append({"error_type": "parse_failure", "message": f"Atomic {atomic['id']}: {program_error}"})
        else:
            programs.append(f"# atomic {atomic['id']}: {atomic['instruction']}\n{program}")
            executor.execute(program)
        first_trace = _event_slice(executor, event_start)
        first_errors = list(executor.error_events[error_start:])
        if program_error:
            first_errors.append({"error_type": "parse_failure", "message": program_error, "line": ""})
        observation = symbolic_state_snapshot(executor.final_graph)
        relevant = _relevant_objects(entry["task_text"], objects, [atomic["manipulated_object"], atomic.get("target_object")])
        first_verifier, first_call, first_verifier_error = verify_task_completion(
            client,
            task=atomic["instruction"],
            current_symbolic_observation=observation,
            relevant_objects=relevant,
            execution_context={"original_task": entry["task_text"], "program": program, "execution_trace": _compact_trace(first_trace), "errors": first_errors},
            llm_config=config["llm"],
        )
        roles.append("atomic_verifier")
        online_outputs.append({"atomic_id": atomic["id"], "attempt": "initial", "observation": observation, "result": first_verifier, "raw_output": first_call.raw_output})
        if first_verifier_error:
            planning_errors.append({"error_type": "verifier_parse_failure", "message": f"Atomic {atomic['id']}: {first_verifier_error}"})

        repair_program = ""
        repair_trace: List[Dict[str, Any]] = []
        repair_errors: List[Dict[str, Any]] = []
        repair_verifier: Optional[Dict[str, Any]] = None
        final_done = bool(first_verifier["done"])
        retry_used = not final_done
        if retry_used:
            retry_count += 1
            repair_data, repair_call, repair_error = generate_repair_program(
                client,
                original_task=entry["task_text"],
                atomic_task=atomic,
                state=observation,
                objects=objects,
                actions_payload=actions,
                previous_program=program,
                execution_trace=first_trace,
                typed_errors=first_errors,
                verifier_result=first_verifier,
                llm_config=config["llm"],
            )
            roles.append("repair_program_agent")
            repair_program = str(repair_data.get("program", ""))
            repair_event_start = len(executor.events)
            repair_error_start = len(executor.error_events)
            if repair_error:
                planning_errors.append({"error_type": "repair_parse_failure", "message": f"Atomic {atomic['id']}: {repair_error}"})
            else:
                programs.append(f"# atomic {atomic['id']} Retry-1\n{repair_program}")
                executor.execute(repair_program)
            repair_trace = _event_slice(executor, repair_event_start)
            repair_errors = list(executor.error_events[repair_error_start:])
            if repair_error:
                repair_errors.append({"error_type": "repair_parse_failure", "message": repair_error, "line": ""})
            repair_observation = symbolic_state_snapshot(executor.final_graph)
            repair_verifier, repair_verifier_call, repair_verifier_error = verify_task_completion(
                client,
                task=atomic["instruction"],
                current_symbolic_observation=repair_observation,
                relevant_objects=relevant,
                execution_context={"original_task": entry["task_text"], "program": repair_program, "execution_trace": _compact_trace(repair_trace), "errors": repair_errors, "previous_verifier": first_verifier},
                llm_config=config["llm"],
            )
            roles.append("post_repair_verifier")
            online_outputs.append({"atomic_id": atomic["id"], "attempt": "repair", "observation": repair_observation, "result": repair_verifier, "raw_output": repair_verifier_call.raw_output})
            if repair_verifier_error:
                planning_errors.append({"error_type": "verifier_parse_failure", "message": f"Atomic {atomic['id']} repair: {repair_verifier_error}"})
            final_done = bool(repair_verifier["done"])

        records.append({
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
        })
        if not final_done:
            early_stop = 1
            planning_errors.append({"error_type": "atomic_online_verification_failure", "message": f"Atomic {atomic['id']} remained done=false after Retry-1"})
            break

    artifacts = executor.artifacts()
    artifacts.update({
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
        "final_online_done": bool(records) and not early_stop and all(item["final_done"] for item in records),
        "taskagent_raw_output": task_call.raw_output,
        "llm_call_roles": roles,
    })
    return artifacts


def _first_error(errors: Sequence[Dict[str, Any]]) -> Tuple[str, str]:
    if not errors:
        return "", ""
    return str(errors[0].get("error_type", "execution_error")), str(errors[0].get("message", ""))


def run_one(method: str, entry: Dict[str, Any], client: ModernLLMClient, unity: UnitySession, config: Dict[str, Any], frozen: Dict[str, Any], phase: str) -> Dict[str, Any]:
    started = time.perf_counter()
    call_start = len(client.calls)
    initial_graph = load_initial_graph(entry)
    live_graph = unity.reset_graph(int(entry["scene"]))
    if _inventory(live_graph) != _inventory(initial_graph):
        missing = _inventory(initial_graph) - _inventory(live_graph)
        extra = _inventory(live_graph) - _inventory(initial_graph)
        raise RuntimeError(f"Unity/cached class inventory mismatch for {entry['task_id']}: missing={missing}, extra={extra}")
    unity_comm = unity.comm if bool(config["virtualhome"].get("render_unity_actions", False)) else None
    if method == "ProgPrompt":
        artifacts = run_progprompt(client, entry, initial_graph, frozen["actions"], unity_comm, config)
    elif method == "HPAF-Flat":
        artifacts = run_flat(client, entry, initial_graph, frozen["actions"], unity_comm, config)
    elif method == "HPAF-Full":
        artifacts = run_full(client, entry, initial_graph, frozen["actions"], unity_comm, config)
    else:
        raise ValueError(method)

    final_state = artifacts.pop("final_state")
    exec_ratio = float(artifacts.pop("Exec"))
    official = evaluate_task(final_state=final_state, ground_truth_final_state=load_final_graph(entry), initial_state=initial_graph, exec_ratio=exec_ratio)
    semantic_by_id = {item["task_id"]: item for item in frozen["semantic"]["tasks"]}
    semantic = evaluate_conditions(final_state, semantic_by_id[entry["task_id"]]["conditions"])
    calls = client.calls[call_start:]
    roles = artifacts.pop("llm_call_roles")
    if len(calls) != len(roles) or any(role not in BROAD_ROLE for role in roles):
        raise RuntimeError(f"Incomplete LLM call-role accounting for {entry['task_id']}/{method}")
    tagged_calls = [{"call_role": role, "broad_role": BROAD_ROLE[role], **call.to_dict()} for call, role in zip(calls, roles)]
    grouped = {name: [call for call, role in zip(calls, roles) if BROAD_ROLE[role] == name] for name in ["generation", "verification", "repair"]}
    errors = artifacts.pop("planning_errors") + artifacts.pop("execution_errors")
    error_type, error_message = _first_error(errors)
    timestamp = datetime.now(timezone.utc).isoformat()
    total_prompt = _sum(calls, "prompt_tokens")
    total_completion = _sum(calls, "completion_tokens")
    return {
        "run_id": f'{phase}_{timestamp.replace(":", "").replace("+", "_")}_{slug(method)}_{slug(entry["task_id"])}',
        "phase": phase,
        "timestamp": timestamp,
        "task_id": entry["task_id"],
        "task": entry["task_text"],
        "split": entry["official_split"],
        "scene": entry["scene"],
        "gt_action_length": entry["gt_action_length"],
        "horizon": entry["horizon"],
        "method": method,
        "provider": client.provider,
        "model": client.model,
        "api_interface": client.api_interface,
        "temperature": float(config["llm"]["temperature"]),
        "thinking": "disabled",
        "max_tokens": int(config["llm"]["max_tokens"]),
        "initial_state_sha256": graph_sha256(initial_graph),
        "task_manifest_sha256": frozen["lock"]["task_manifest_sha256"],
        "semantic_goals_sha256": frozen["lock"]["semantic_goals_sha256"],
        "long_horizon_manifest_sha256": frozen["lock"]["long_horizon_manifest_sha256"],
        "action_set_sha256": frozen["lock"]["action_set_sha256"],
        "implementation_sha256": implementation_sha256(),
        "generated_programs": artifacts.get("atomic_records") if method == "HPAF-Full" else [artifacts.get("generated_program", "")],
        "generated_program": artifacts.pop("generated_program"),
        "atomic_tasks": artifacts.pop("atomic_tasks"),
        "number_of_atomic_tasks": artifacts.pop("number_of_atomic_tasks"),
        "atomic_tasks_attempted": artifacts.pop("atomic_tasks_attempted"),
        "atomic_records": artifacts.pop("atomic_records"),
        "retry_count": artifacts.pop("retry_count"),
        "early_stop_count": artifacts.pop("early_stop_count"),
        "online_verification_calls": [item for item in tagged_calls if item["broad_role"] == "verification"],
        "online_verification_outputs": artifacts.pop("online_verification_outputs"),
        "online_verification_count": artifacts.pop("online_verification_count"),
        "final_online_done": artifacts.pop("final_online_done"),
        "execution_trace": artifacts.pop("execution_trace"),
        "graph_execution_trace": artifacts.pop("graph_execution_trace"),
        "compiled_virtualhome_actions": artifacts.pop("compiled_virtualhome_actions"),
        "program_length": artifacts.pop("program_length"),
        **semantic,
        "official_SR": official["SR"],
        "official_GCR": official["GCR"],
        "official_PSR": official["PSR"],
        "official_Precision": official["Precision"],
        "Exec": official["Exec"],
        "official_goal_condition_count": official["goal_condition_count"],
        "official_missing_goal_relations": official["missing_goal_relations"],
        "official_missing_goal_states": official["missing_goal_states"],
        "generation_calls": len(grouped["generation"]),
        "verification_calls": len(grouped["verification"]),
        "repair_calls": len(grouped["repair"]),
        "total_calls": len(calls),
        "generation_prompt_tokens": _sum(grouped["generation"], "prompt_tokens"),
        "generation_completion_tokens": _sum(grouped["generation"], "completion_tokens"),
        "verification_prompt_tokens": _sum(grouped["verification"], "prompt_tokens"),
        "verification_completion_tokens": _sum(grouped["verification"], "completion_tokens"),
        "repair_tokens": _tokens(grouped["repair"]),
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": None if total_prompt is None or total_completion is None else total_prompt + total_completion,
        "planning_latency": sum(call.latency_s for call in grouped["generation"] + grouped["repair"]),
        "verification_latency": sum(call.latency_s for call in grouped["verification"]),
        "total_llm_latency": sum(call.latency_s for call in calls),
        "wall_clock_total_s": time.perf_counter() - started,
        "llm_call_records": tagged_calls,
        "raw_prompts": [{"role": role, "instructions": call.instructions, "input": call.prompt} for call, role in zip(calls, roles)],
        "raw_model_outputs": [{"role": role, "output": call.raw_output} for call, role in zip(calls, roles)],
        "error_type": error_type,
        "error_message": error_message,
        "errors": errors,
        **artifacts,
    }


def load_existing(output_root: Path) -> Dict[Tuple[str, str], Dict[str, Any]]:
    path = output_root / "raw_runs.jsonl"
    if not path.exists():
        return {}
    result = {}
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
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output_root / "raw_runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def validate_complete_records(rows: Iterable[Dict[str, Any]], task_ids: Sequence[str], phase: str) -> None:
    rows = list(rows)
    expected = {(task_id, method) for task_id in task_ids for method in METHODS}
    actual = {(row["task_id"], row["method"]) for row in rows}
    if actual != expected or len(rows) != len(expected):
        raise RuntimeError(f"Run matrix incomplete: expected={len(expected)} actual={len(rows)} missing={sorted(expected-actual)} extra={sorted(actual-expected)}")
    required = {"final_semantic_SR", "semantic_GCR", "official_SR", "official_GCR", "Exec", "generation_calls", "verification_calls", "repair_calls", "total_calls", "total_tokens", "total_llm_latency", "online_verification_outputs"}
    current_impl = implementation_sha256()
    for row in rows:
        missing = required - set(row)
        if missing:
            raise RuntimeError(f"{row['task_id']}/{row['method']}: missing {sorted(missing)}")
        if row["phase"] != phase or row["implementation_sha256"] != current_impl:
            raise RuntimeError(f"{row['task_id']}/{row['method']}: phase/implementation mismatch")
        if row["method"] == "HPAF-Flat" and (row["generation_calls"], row["verification_calls"], row["repair_calls"]) != (1, 1, 0):
            raise RuntimeError(f"{row['task_id']}: Flat call accounting invariant failed")
        if row["method"] == "HPAF-Full" and not any(call["call_role"] == "task_agent" for call in row["llm_call_records"]):
            raise RuntimeError(f"{row['task_id']}: Full omitted TaskAgent cost")


def run_matrix(output_root: Path, task_ids: Sequence[str], phase: str) -> List[Dict[str, Any]]:
    config = load_config()
    frozen = verify_protocol_lock(config)
    by_id = {item["task_id"]: item for item in frozen["selected"]}
    if any(task_id not in by_id for task_id in task_ids):
        raise KeyError("Requested matrix contains a non-selected task")
    existing = load_existing(output_root)
    expected = {(task_id, method) for task_id in task_ids for method in METHODS}
    if not set(existing) <= expected:
        raise RuntimeError("Output contains pairs outside this matrix")
    if len(existing) == len(expected):
        validate_complete_records(existing.values(), task_ids, phase)
        return list(existing.values())
    client = make_client(config)
    vh = config["virtualhome"]
    with UnitySession(PROJECT_ROOT / vh["executable"], int(vh["port"]), bool(vh["no_graphics"])) as unity:
        for task_id in task_ids:
            for method in METHODS:
                pair = (task_id, method)
                if pair in existing:
                    print(f"SKIP existing {method} :: {task_id}", flush=True)
                    continue
                print(f"RUN {method} :: {task_id}", flush=True)
                result = run_one(method, by_id[task_id], client, unity, config, frozen, phase)
                save_run(output_root, result)
                existing[pair] = result
                print(json.dumps({
                    "method": method,
                    "task_id": task_id,
                    "semantic_sr": result["final_semantic_SR"],
                    "official_sr": result["official_SR"],
                    "exec": result["Exec"],
                    "calls": result["total_calls"],
                    "tokens": result["total_tokens"],
                    "verification_calls": result["verification_calls"],
                    "retry_count": result["retry_count"],
                    "error_type": result["error_type"],
                }, ensure_ascii=False), flush=True)
    validate_complete_records(existing.values(), task_ids, phase)
    return list(existing.values())

