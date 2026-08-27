"""Locked Phase-5 smoke/formal orchestration and record construction."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

from experiments.progprompt_vh.adapters.dataset import TaskRecord, load_task_records
from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient
from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.adapters.virtualhome import (
    UnitySession,
    available_object_classes,
)

from .evaluation.official_evaluator import evaluate_task
from .evaluation.semantic_evaluator import evaluate_conditions, verify_primary_goal
from .execution import GraphProgramExecutor, symbolic_state_snapshot
from .methods.hpaf_flat import generate_flat_program
from .methods.hpaf_hierarchical import (
    generate_atomic_program,
    generate_repair_program,
)
from .methods.progprompt_graph_compatible import generate_progprompt_program


PHASE5_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PHASE5_ROOT / "configs/benchmark.yaml"
LOCK_PATH = PHASE5_ROOT / "data/protocol_lock.json"
ACTION_PATH = PHASE5_ROOT / "data/graph_supported_actions.json"
SEMANTIC_PATH = PHASE5_ROOT / "data/semantic_goals_test_unseen.json"
DECOMPOSITION_PATH = PHASE5_ROOT / "data/frozen_decompositions.json"
PHASE4_RAW = PHASE5_ROOT.parent / "results/raw_runs.jsonl"
METHODS = [
    "ProgPrompt-GraphCompatible",
    "HPAF-Flat",
    "HPAF-Hierarchical",
]


def slug(text: str) -> str:
    return "_".join("".join(char if char.isalnum() else " " for char in text).split()).lower()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def graph_hash(graph: Dict[str, Any]) -> str:
    encoded = json.dumps(graph, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_config() -> Dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def verify_protocol_lock(config: Dict[str, Any]) -> Dict[str, Any]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    checks = {
        "action_set_sha256": file_sha256(ACTION_PATH),
        "semantic_goal_sha256": file_sha256(SEMANTIC_PATH),
        "decomposition_sha256": file_sha256(DECOMPOSITION_PATH),
        "phase4_raw_runs_sha256": file_sha256(PHASE4_RAW),
    }
    initial_path = PROJECT_ROOT / config["virtualhome"]["cached_initial_graph"]
    checks["initial_graph_file_sha256"] = file_sha256(initial_path)
    initial_graph = json.loads(initial_path.read_text(encoding="utf-8"))
    checks["initial_graph_canonical_sha256"] = graph_hash(initial_graph)
    mismatch = {
        key: {"expected": lock.get(key), "actual": actual}
        for key, actual in checks.items()
        if lock.get(key) != actual
    }
    if mismatch:
        raise RuntimeError(f"Frozen protocol hash mismatch: {json.dumps(mismatch)}")

    actions = json.loads(ACTION_PATH.read_text(encoding="utf-8"))
    semantic = json.loads(SEMANTIC_PATH.read_text(encoding="utf-8"))
    decompositions = json.loads(DECOMPOSITION_PATH.read_text(encoding="utf-8"))
    task_order = [record.task for record in load_task_records(config["benchmark"]["test_set"])]
    if [item["task"] for item in semantic["tasks"]] != task_order:
        raise RuntimeError("Frozen semantic-goal task order mismatch")
    if [item["task"] for item in decompositions["tasks"]] != task_order:
        raise RuntimeError("Frozen decomposition task order mismatch")
    if decompositions.get("taskagent_calls") != 10:
        raise RuntimeError("Frozen decomposition does not record exactly 10 TaskAgent calls")
    if config["benchmark"]["methods"] != METHODS:
        raise RuntimeError("Configured method order differs from locked Phase-5 protocol")
    return {
        "lock": lock,
        "actions": actions,
        "semantic": semantic,
        "decompositions": decompositions,
        "initial_graph": initial_graph,
    }


def make_client(config: Dict[str, Any]) -> ModernLLMClient:
    client = ModernLLMClient.from_env_spec(config["llm"]["ark"])
    if (
        client.provider != "ark"
        or client.model != "doubao-seed-2-1-pro-260628"
        or client.api_interface != "responses.create"
        or client.extra_body != {"thinking": {"type": "disabled"}}
    ):
        raise RuntimeError("LLM backend/settings differ from the frozen protocol")
    return client


def sum_optional(calls: List[LLMCall], field: str) -> Optional[int]:
    values = [getattr(call, field) for call in calls]
    if any(value is None for value in values):
        return None
    return sum(int(value) for value in values)


def first_error(errors: List[Dict[str, Any]]) -> Tuple[str, str]:
    if not errors:
        return "", ""
    return (
        str(errors[0].get("error_type", "execution_error")),
        str(errors[0].get("message", "")),
    )


def new_executor(
    *,
    initial_graph: Dict[str, Any],
    actions: Dict[str, Any],
    client: ModernLLMClient,
    unity_comm,
    config: Dict[str, Any],
) -> GraphProgramExecutor:
    return GraphProgramExecutor(
        initial_graph,
        actions_payload=actions,
        llm_client=client,
        unity_comm=unity_comm,
        seed=int(config["benchmark"]["seed"]),
        state_check_max_tokens=int(config["llm"]["state_check_max_tokens"]),
    )


def run_progprompt(
    *,
    client: ModernLLMClient,
    task: TaskRecord,
    initial_graph: Dict[str, Any],
    actions: Dict[str, Any],
    unity_comm,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    program, _ = generate_progprompt_program(
        client,
        task=task.task,
        objects=available_object_classes(initial_graph),
        actions_payload=actions,
        prompt_config=config["progprompt"],
    )
    executor = new_executor(
        initial_graph=initial_graph,
        actions=actions,
        client=client,
        unity_comm=unity_comm,
        config=config,
    )
    executor.execute(program)
    artifacts = executor.artifacts()
    artifacts.update(
        {
            "generated_program": program,
            "atomic_tasks": [],
            "number_of_atomic_tasks": 0,
            "atomic_tasks_attempted": 0,
            "atomic_programs": [],
            "atomic_verifications": [],
            "planning_errors": [],
            "retry_count": 0,
            "early_stop_count": 0,
            "verified_but_stopped_count": 0,
        }
    )
    return artifacts


def run_flat(
    *,
    client: ModernLLMClient,
    task: TaskRecord,
    semantic_spec: Dict[str, Any],
    initial_graph: Dict[str, Any],
    actions: Dict[str, Any],
    unity_comm,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    executor = new_executor(
        initial_graph=initial_graph,
        actions=actions,
        client=client,
        unity_comm=unity_comm,
        config=config,
    )
    state = symbolic_state_snapshot(initial_graph)
    program_data, _, program_error = generate_flat_program(
        client,
        task=task.task,
        final_semantic_conditions=semantic_spec["conditions"],
        state=state,
        objects=available_object_classes(initial_graph),
        actions_payload=actions,
        llm_config=config["llm"],
    )
    planning_errors = []
    program = str(program_data.get("program", ""))
    if program_error:
        planning_errors.append({"error_type": "parse_failure", "message": program_error})
    else:
        executor.execute(program)
    artifacts = executor.artifacts()
    artifacts.update(
        {
            "generated_program": program,
            "atomic_tasks": [],
            "number_of_atomic_tasks": 0,
            "atomic_tasks_attempted": 0,
            "atomic_programs": [],
            "atomic_verifications": [],
            "planning_errors": planning_errors,
            "retry_count": 0,
            "early_stop_count": 0,
            "verified_but_stopped_count": 0,
            "flat_state_used": state,
            "flat_final_semantic_targets": semantic_spec["conditions"],
        }
    )
    return artifacts


def event_slice(executor: GraphProgramExecutor, start: int) -> List[Dict[str, Any]]:
    from dataclasses import asdict

    return [asdict(item) for item in executor.events[start:]]


def run_hierarchical(
    *,
    client: ModernLLMClient,
    task: TaskRecord,
    decomposition_spec: Dict[str, Any],
    initial_graph: Dict[str, Any],
    actions: Dict[str, Any],
    unity_comm,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    executor = new_executor(
        initial_graph=initial_graph,
        actions=actions,
        client=client,
        unity_comm=unity_comm,
        config=config,
    )
    objects = available_object_classes(initial_graph)
    atomics = decomposition_spec["atomic_tasks"]
    atomic_programs: List[Dict[str, Any]] = []
    verifications: List[Dict[str, Any]] = []
    planning_errors: List[Dict[str, Any]] = []
    program_parts: List[str] = []
    retry_count = 0
    early_stop_count = 0

    for atomic in atomics:
        state_used = symbolic_state_snapshot(executor.graph_executor.graph)
        event_start = len(executor.events)
        error_start = len(executor.error_events)
        before_total = executor.graph_executor.total_steps
        before_success = executor.graph_executor.executable_steps
        program_data, initial_call, program_error = generate_atomic_program(
            client,
            original_task=task.task,
            atomic_task=atomic,
            state=state_used,
            objects=objects,
            actions_payload=actions,
            llm_config=config["llm"],
        )
        initial_program = str(program_data.get("program", ""))
        if program_error:
            planning_errors.append(
                {
                    "error_type": "parse_failure",
                    "message": f'Atomic {atomic["id"]} initial generation: {program_error}',
                }
            )
        else:
            program_parts.append(f'# atomic {atomic["id"]}: {atomic["instruction"]}\n{initial_program}')
            executor.execute(initial_program)

        first_trace = event_slice(executor, event_start)
        first_errors = list(executor.error_events[error_start:])
        if program_error:
            first_errors.append(
                {"error_type": "parse_failure", "message": program_error, "line": ""}
            )
        first_attempted = executor.graph_executor.total_steps - before_total
        first_successes = executor.graph_executor.executable_steps - before_success
        first_boundary = first_attempted > 0 and first_attempted == first_successes
        first_verified, first_detail = verify_primary_goal(
            executor.final_graph, atomic["primary_goal_condition"]
        )

        retry_used = False
        repair_prompt = ""
        repair_program = ""
        repair_error: Optional[str] = None
        repair_trace: List[Dict[str, Any]] = []
        repair_errors: List[Dict[str, Any]] = []
        repair_attempted = 0
        repair_successes = 0
        repair_boundary = False
        repair_verified: Optional[bool] = None
        repair_detail: Optional[Dict[str, Any]] = None
        final_verified = first_verified

        if not first_verified:
            retry_used = True
            retry_count += 1
            repair_state = symbolic_state_snapshot(executor.graph_executor.graph)
            failed_actions = [
                item
                for item in first_trace
                if item.get("event") == "action" and item.get("success") is False
            ]
            repair_data, repair_call, repair_error = generate_repair_program(
                client,
                original_task=task.task,
                atomic_task=atomic,
                state=repair_state,
                objects=objects,
                actions_payload=actions,
                previous_program=initial_program,
                execution_trace=first_trace,
                failed_actions=failed_actions,
                typed_errors=first_errors,
                llm_config=config["llm"],
            )
            repair_prompt = repair_call.prompt
            repair_program = str(repair_data.get("program", ""))
            repair_event_start = len(executor.events)
            repair_error_start = len(executor.error_events)
            repair_before_total = executor.graph_executor.total_steps
            repair_before_success = executor.graph_executor.executable_steps
            if repair_error:
                planning_errors.append(
                    {
                        "error_type": "parse_failure",
                        "message": f'Atomic {atomic["id"]} repair generation: {repair_error}',
                    }
                )
            else:
                program_parts.append(
                    f'# atomic {atomic["id"]} Retry-1\n{repair_program}'
                )
                executor.execute(repair_program)
            repair_trace = event_slice(executor, repair_event_start)
            repair_errors = list(executor.error_events[repair_error_start:])
            if repair_error:
                repair_errors.append(
                    {"error_type": "parse_failure", "message": repair_error, "line": ""}
                )
            repair_attempted = executor.graph_executor.total_steps - repair_before_total
            repair_successes = (
                executor.graph_executor.executable_steps - repair_before_success
            )
            repair_boundary = (
                repair_attempted > 0 and repair_attempted == repair_successes
            )
            repair_verified, repair_detail = verify_primary_goal(
                executor.final_graph, atomic["primary_goal_condition"]
            )
            final_verified = repair_verified

        # The Phase-5 controller contract: semantic verification alone gates continuation.
        can_continue = bool(final_verified)
        verified_but_stopped = bool(final_verified) and not can_continue
        atomic_record = {
            "atomic_task": atomic,
            "state_used": state_used,
            "initial_prompt": initial_call.prompt,
            "initial_program": initial_program,
            "initial_generation_error": program_error,
            "initial_execution_trace": first_trace,
            "initial_typed_errors": first_errors,
            "initial_attempted_actions": first_attempted,
            "initial_successful_actions": first_successes,
            "initial_boundary_executable": first_boundary,
            "first_verified": first_verified,
            "first_verification_detail": first_detail,
            "retry_used": retry_used,
            "repair_prompt": repair_prompt,
            "repair_program": repair_program,
            "repair_generation_error": repair_error,
            "repair_execution_trace": repair_trace,
            "repair_typed_errors": repair_errors,
            "repair_attempted_actions": repair_attempted,
            "repair_successful_actions": repair_successes,
            "repair_boundary_executable": repair_boundary,
            "repair_verified": repair_verified,
            "repair_verification_detail": repair_detail,
            "final_verified": bool(final_verified),
            "can_continue": can_continue,
            "verified_but_stopped": verified_but_stopped,
        }
        atomic_programs.append(
            {
                "atomic_task": atomic,
                "initial_program": initial_program,
                "repair_program": repair_program,
                "retry_used": retry_used,
            }
        )
        verifications.append(atomic_record)
        if not can_continue:
            early_stop_count = 1
            planning_errors.append(
                {
                    "error_type": "atomic_verification_failure",
                    "message": (
                        f'Atomic {atomic["id"]} primary semantic goal remained false '
                        "after the single allowed repair"
                    ),
                }
            )
            break

    artifacts = executor.artifacts()
    artifacts.update(
        {
            "generated_program": "\n".join(program_parts),
            "atomic_tasks": atomics,
            "number_of_atomic_tasks": len(atomics),
            "atomic_tasks_attempted": len(verifications),
            "atomic_programs": atomic_programs,
            "atomic_verifications": verifications,
            "planning_errors": planning_errors,
            "retry_count": retry_count,
            "early_stop_count": early_stop_count,
            "verified_but_stopped_count": sum(
                int(item["verified_but_stopped"]) for item in verifications
            ),
        }
    )
    return artifacts


def run_one(
    *,
    method: str,
    task: TaskRecord,
    client: ModernLLMClient,
    unity: UnitySession,
    config: Dict[str, Any],
    frozen: Dict[str, Any],
    phase: str,
) -> Dict[str, Any]:
    started = time.perf_counter()
    call_start = len(client.calls)
    live_graph = unity.reset_graph(int(config["benchmark"]["scene"]))
    initial_graph = frozen["initial_graph"]
    live_inventory = {(node["id"], node["class_name"]) for node in live_graph["nodes"]}
    cached_inventory = {
        (node["id"], node["class_name"]) for node in initial_graph["nodes"]
    }
    if live_inventory != cached_inventory:
        raise RuntimeError("Unity reset inventory differs from locked initial graph")
    unity_comm = (
        unity.comm if bool(config["virtualhome"].get("render_unity_actions", False)) else None
    )
    semantic_by_task = {item["task"]: item for item in frozen["semantic"]["tasks"]}
    decomposition_by_task = {
        item["task"]: item for item in frozen["decompositions"]["tasks"]
    }
    if method == "ProgPrompt-GraphCompatible":
        artifacts = run_progprompt(
            client=client,
            task=task,
            initial_graph=initial_graph,
            actions=frozen["actions"],
            unity_comm=unity_comm,
            config=config,
        )
    elif method == "HPAF-Flat":
        artifacts = run_flat(
            client=client,
            task=task,
            semantic_spec=semantic_by_task[task.task],
            initial_graph=initial_graph,
            actions=frozen["actions"],
            unity_comm=unity_comm,
            config=config,
        )
    elif method == "HPAF-Hierarchical":
        artifacts = run_hierarchical(
            client=client,
            task=task,
            decomposition_spec=decomposition_by_task[task.task],
            initial_graph=initial_graph,
            actions=frozen["actions"],
            unity_comm=unity_comm,
            config=config,
        )
    else:
        raise ValueError(method)

    final_state = artifacts.pop("final_state")
    official = evaluate_task(
        final_state=final_state,
        ground_truth_final_state=task.final_state,
        initial_state=initial_graph,
        exec_ratio=float(artifacts.pop("Exec")),
    )
    semantic = evaluate_conditions(
        final_state, semantic_by_task[task.task]["conditions"]
    )
    calls = client.calls[call_start:]
    errors = artifacts.pop("planning_errors") + artifacts.pop("execution_errors")
    error_type, error_message = first_error(errors)
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "run_id": f'{phase}_{timestamp.replace(":", "").replace("+", "_")}_{slug(method)}_{slug(task.task)}',
        "phase": phase,
        "timestamp": timestamp,
        "task": task.task,
        "method": method,
        "provider": client.provider,
        "model": client.model,
        "api_interface": client.api_interface,
        "temperature": float(config["llm"]["temperature"]),
        "thinking": "disabled",
        "max_tokens": int(config["llm"]["max_tokens"]),
        "seed": config["llm"].get("seed"),
        "scene": int(config["benchmark"]["scene"]),
        "initial_state_sha256": graph_hash(initial_graph),
        "action_set_sha256": frozen["lock"]["action_set_sha256"],
        "semantic_goal_sha256": frozen["lock"]["semantic_goal_sha256"],
        "decomposition_sha256": frozen["lock"]["decomposition_sha256"],
        "ground_truth_action_length": task.ground_truth_action_length,
        "difficulty_bucket": task.difficulty_bucket,
        "atomic_tasks": artifacts.pop("atomic_tasks"),
        "number_of_atomic_tasks": artifacts.pop("number_of_atomic_tasks"),
        "atomic_tasks_attempted": artifacts.pop("atomic_tasks_attempted"),
        "atomic_programs": artifacts.pop("atomic_programs"),
        "atomic_verifications": artifacts.pop("atomic_verifications"),
        "retry_count": artifacts.pop("retry_count"),
        "early_stop_count": artifacts.pop("early_stop_count"),
        "verified_but_stopped_count": artifacts.pop("verified_but_stopped_count"),
        "raw_prompts": [
            {"instructions": call.instructions, "input": call.prompt} for call in calls
        ],
        "raw_model_outputs": [call.raw_output for call in calls],
        "llm_call_records": [call.to_dict() for call in calls],
        "generated_program": artifacts.pop("generated_program"),
        "compiled_virtualhome_actions": artifacts.pop("compiled_virtualhome_actions"),
        "execution_trace": artifacts.pop("execution_trace"),
        "graph_execution_trace": artifacts.pop("graph_execution_trace"),
        "SR": official["SR"],
        "GCR": official["GCR"],
        "PSR": official["PSR"],
        "Precision": official["Precision"],
        "Exec": official["Exec"],
        "goal_condition_count": official["goal_condition_count"],
        "missing_goal_relations": official["missing_goal_relations"],
        "missing_goal_states": official["missing_goal_states"],
        **semantic,
        "semantic_goal_ambiguity": semantic_by_task[task.task]["ambiguity"],
        "program_length": artifacts.pop("program_length"),
        "llm_calls": len(calls),
        "prompt_tokens": sum_optional(calls, "prompt_tokens"),
        "completion_tokens": sum_optional(calls, "completion_tokens"),
        "total_tokens": (
            None
            if sum_optional(calls, "prompt_tokens") is None
            or sum_optional(calls, "completion_tokens") is None
            else int(sum_optional(calls, "prompt_tokens") or 0)
            + int(sum_optional(calls, "completion_tokens") or 0)
        ),
        "planning_latency": sum(call.latency_s for call in calls),
        "wall_clock_total_s": time.perf_counter() - started,
        "error_type": error_type,
        "error_message": error_message,
        "errors": errors,
        **artifacts,
    }


def load_existing(output_root: Path) -> Dict[Tuple[str, str], Dict[str, Any]]:
    path = output_root / "raw_runs.jsonl"
    if not path.exists():
        return {}
    rows: Dict[Tuple[str, str], Dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            pair = (row["task"], row["method"])
            if pair in rows:
                raise RuntimeError(f"Duplicate run pair in {path}: {pair}")
            rows[pair] = row
    return rows


def save_run(output_root: Path, record: Dict[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    runs_dir = output_root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_path = runs_dir / f'{slug(record["method"])}__{slug(record["task"])}.json'
    if run_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing run: {run_path}")
    run_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (output_root / "raw_runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def validate_complete_records(
    rows: Iterable[Dict[str, Any]], tasks: Sequence[str]
) -> None:
    rows = list(rows)
    expected = {(task, method) for task in tasks for method in METHODS}
    actual = {(row["task"], row["method"]) for row in rows}
    if actual != expected or len(rows) != len(expected):
        raise RuntimeError(
            f"Run matrix incomplete: expected={len(expected)} actual={len(rows)} "
            f"missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )
    required = {
        "SR", "GCR", "Exec", "Semantic_SR", "Semantic_GCR", "llm_calls",
        "total_tokens", "planning_latency", "execution_trace", "raw_model_outputs",
    }
    for row in rows:
        missing = sorted(required - set(row))
        if missing:
            raise RuntimeError(f'{row["task"]}/{row["method"]}: missing {missing}')
        if row["method"] == "HPAF-Hierarchical" and row["verified_but_stopped_count"]:
            raise RuntimeError(
                f'{row["task"]}: verified_but_stopped_count must be zero'
            )


def run_matrix(
    *,
    output_root: Path,
    task_names: Sequence[str],
    phase: str,
) -> List[Dict[str, Any]]:
    config = load_config()
    frozen = verify_protocol_lock(config)
    records = load_task_records(config["benchmark"]["test_set"])
    record_by_task = {record.task: record for record in records}
    if any(task not in record_by_task for task in task_names):
        raise KeyError(f"Unknown task in requested matrix: {task_names}")
    existing = load_existing(output_root)
    expected_pairs = {(task, method) for task in task_names for method in METHODS}
    if not set(existing) <= expected_pairs:
        raise RuntimeError("Output contains task/method pairs outside this locked matrix")
    if len(existing) == len(expected_pairs):
        validate_complete_records(existing.values(), task_names)
        print(f"COMPLETE existing locked matrix :: {output_root}", flush=True)
        return list(existing.values())

    client = make_client(config)
    vh = config["virtualhome"]
    executable = PROJECT_ROOT / vh["executable"]
    with UnitySession(
        executable=executable,
        port=int(vh["port"]),
        no_graphics=bool(vh["no_graphics"]),
    ) as unity:
        for task_name in task_names:
            for method in METHODS:
                pair = (task_name, method)
                if pair in existing:
                    print(f"SKIP existing {method} :: {task_name}", flush=True)
                    continue
                print(f"RUN {method} :: {task_name}", flush=True)
                result = run_one(
                    method=method,
                    task=record_by_task[task_name],
                    client=client,
                    unity=unity,
                    config=config,
                    frozen=frozen,
                    phase=phase,
                )
                save_run(output_root, result)
                existing[pair] = result
                print(
                    json.dumps(
                        {
                            "method": method,
                            "task": task_name,
                            "official_sr": result["SR"],
                            "semantic_sr": result["Semantic_SR"],
                            "semantic_gcr": result["Semantic_GCR"],
                            "exec": result["Exec"],
                            "calls": result["llm_calls"],
                            "tokens": result["total_tokens"],
                            "retry_count": result["retry_count"],
                            "verified_but_stopped": result["verified_but_stopped_count"],
                            "error_type": result["error_type"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    validate_complete_records(existing.values(), task_names)
    return list(existing.values())

