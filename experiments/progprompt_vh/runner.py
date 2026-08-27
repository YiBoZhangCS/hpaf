from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from experiments.progprompt_vh.adapters.dataset import TaskRecord, load_task_records
from experiments.progprompt_vh.adapters.evaluator import evaluate_task
from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient
from experiments.progprompt_vh.adapters.paths import EXPERIMENT_ROOT, PROJECT_ROOT, RESULTS_ROOT
from experiments.progprompt_vh.adapters.program_executor import ProgramExecutor
from experiments.progprompt_vh.adapters.virtualhome import (
    UnitySession,
    available_object_classes,
    local_symbolic_state,
)
from experiments.progprompt_vh.methods.planners import (
    decompose_task,
    generate_atomic_program,
    generate_progprompt_program,
    verify_completion_conditions,
)


METHODS = [
    "ProgPrompt-Full",
    "HPAF-Decomp-Static",
    "HPAF-Decomp-ClosedLoop",
]


def slug(text: str) -> str:
    return "_".join("".join(char if char.isalnum() else " " for char in text).split()).lower()


def graph_hash(graph: Dict[str, Any]) -> str:
    encoded = json.dumps(graph, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sum_optional(calls: List[LLMCall], field: str) -> Optional[int]:
    values = [getattr(call, field) for call in calls]
    if any(value is None for value in values):
        return None
    return sum(int(value) for value in values)


def first_error(errors: List[Dict[str, str]]) -> tuple[str, str]:
    if not errors:
        return "", ""
    return errors[0].get("error_type", "execution_error"), errors[0].get("message", "")


def executor_artifacts(executor: ProgramExecutor) -> Dict[str, Any]:
    return {
        "final_state": executor.final_graph,
        "Exec": executor.exec_ratio,
        "program_length": executor.program_length,
        "compiled_virtualhome_actions": executor.compiled_actions,
        "execution_trace": [asdict(event) for event in executor.events],
        "graph_execution_trace": [asdict(trace) for trace in executor.graph_executor.trace],
        "execution_errors": list(executor.error_events),
    }


def run_progprompt(
    *,
    client: ModernLLMClient,
    task: TaskRecord,
    initial_graph: Dict[str, Any],
    unity_comm,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    objects = available_object_classes(initial_graph)
    program, _ = generate_progprompt_program(
        client,
        task=task.task,
        objects=objects,
        prompt_config=config["progprompt"],
    )
    executor = ProgramExecutor(
        initial_graph,
        llm_client=client,
        unity_comm=unity_comm,
        seed=int(config["benchmark"]["seed"]),
        state_check_max_tokens=int(config["llm"]["state_check_max_tokens"]),
    )
    executor.execute(program)
    artifacts = executor_artifacts(executor)
    artifacts.update(
        {
            "generated_program": program,
            "atomic_tasks": [],
            "number_of_atomic_tasks": 0,
            "atomic_programs": [],
            "atomic_verifications": [],
            "planning_errors": [],
        }
    )
    return artifacts


def run_hpaf_static(
    *,
    client: ModernLLMClient,
    task: TaskRecord,
    initial_graph: Dict[str, Any],
    unity_comm,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    objects = available_object_classes(initial_graph)
    initial_state_text = local_symbolic_state(initial_graph, include_inside=False)
    atomic_tasks, _, decomposition_error = decompose_task(
        client,
        task=task.task,
        objects=objects,
        state=initial_state_text,
        llm_config=config["llm"],
    )
    planning_errors: List[Dict[str, str]] = []
    if decomposition_error:
        planning_errors.append(
            {"error_type": "parse_failure", "message": decomposition_error}
        )

    atomic_programs = []
    combined_parts = []
    for atomic_task in atomic_tasks:
        program_data, _, program_error = generate_atomic_program(
            client,
            original_task=task.task,
            atomic_task=atomic_task,
            objects=objects,
            state=initial_state_text,
            llm_config=config["llm"],
        )
        atomic_entry = {
            "atomic_task": atomic_task,
            "program_data": program_data,
            "error": program_error,
            "state_refresh": False,
            "state_used": initial_state_text,
        }
        atomic_programs.append(atomic_entry)
        if program_error:
            planning_errors.append(
                {
                    "error_type": "parse_failure",
                    "message": f'Atomic {atomic_task["id"]}: {program_error}',
                }
            )
            continue
        combined_parts.append(
            f'# HPAF atomic {atomic_task["id"]}: {atomic_task["task"]}\n'
            f'{program_data["program"]}'
        )

    combined_program = "\n".join(combined_parts)
    executor = ProgramExecutor(
        initial_graph,
        llm_client=client,
        unity_comm=unity_comm,
        seed=int(config["benchmark"]["seed"]),
        state_check_max_tokens=int(config["llm"]["state_check_max_tokens"]),
    )
    if combined_program.strip():
        executor.execute(combined_program)
    elif not planning_errors:
        planning_errors.append(
            {"error_type": "incomplete_generation", "message": "No combined program"}
        )
    artifacts = executor_artifacts(executor)
    artifacts.update(
        {
            "generated_program": combined_program,
            "atomic_tasks": atomic_tasks,
            "number_of_atomic_tasks": len(atomic_tasks),
            "atomic_programs": atomic_programs,
            "atomic_verifications": [],
            "planning_errors": planning_errors,
        }
    )
    return artifacts


def run_hpaf_closed_loop(
    *,
    client: ModernLLMClient,
    task: TaskRecord,
    initial_graph: Dict[str, Any],
    unity_comm,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    objects = available_object_classes(initial_graph)
    initial_state_text = local_symbolic_state(initial_graph, include_inside=False)
    atomic_tasks, _, decomposition_error = decompose_task(
        client,
        task=task.task,
        objects=objects,
        state=initial_state_text,
        llm_config=config["llm"],
    )
    planning_errors: List[Dict[str, str]] = []
    if decomposition_error:
        planning_errors.append(
            {"error_type": "parse_failure", "message": decomposition_error}
        )

    executor = ProgramExecutor(
        initial_graph,
        llm_client=client,
        unity_comm=unity_comm,
        seed=int(config["benchmark"]["seed"]),
        state_check_max_tokens=int(config["llm"]["state_check_max_tokens"]),
    )
    atomic_programs = []
    atomic_verifications = []
    program_parts = []

    for atomic_task in atomic_tasks:
        current_state = local_symbolic_state(
            executor.graph_executor.graph, include_inside=True
        )
        before_total = executor.graph_executor.total_steps
        before_success = executor.graph_executor.executable_steps
        program_data, _, program_error = generate_atomic_program(
            client,
            original_task=task.task,
            atomic_task=atomic_task,
            objects=objects,
            state=current_state,
            llm_config=config["llm"],
        )
        atomic_entry = {
            "atomic_task": atomic_task,
            "program_data": program_data,
            "error": program_error,
            "state_refresh": True,
            "state_used": current_state,
        }
        atomic_programs.append(atomic_entry)
        if program_error:
            planning_errors.append(
                {
                    "error_type": "parse_failure",
                    "message": f'Atomic {atomic_task["id"]}: {program_error}',
                }
            )
            atomic_verifications.append(
                {
                    "atomic_task": atomic_task,
                    "verified": False,
                    "can_continue": False,
                    "reason": program_error,
                }
            )
            break

        program = program_data["program"]
        program_parts.append(
            f'# HPAF atomic {atomic_task["id"]}: {atomic_task["task"]}\n{program}'
        )
        executor.execute(program)
        attempted = executor.graph_executor.total_steps - before_total
        succeeded = executor.graph_executor.executable_steps - before_success
        boundary_executable = attempted > 0 and attempted == succeeded
        conditions = program_data.get("completion_conditions", [])
        verified, condition_details = verify_completion_conditions(
            executor.final_graph, conditions
        )
        can_continue = boundary_executable and verified is not False
        atomic_verifications.append(
            {
                "atomic_task": atomic_task,
                "verified": verified,
                "completion_conditions": conditions,
                "condition_details": condition_details,
                "attempted_actions": attempted,
                "successful_actions": succeeded,
                "boundary_executable": boundary_executable,
                "can_continue": can_continue,
                "reason": (
                    "symbolic conditions satisfied"
                    if verified is True
                    else "symbolic conditions failed"
                    if verified is False
                    else "no graph-representable condition; used executable boundary"
                ),
            }
        )
        if not can_continue:
            planning_errors.append(
                {
                    "error_type": "atomic_verification_failure",
                    "message": f'Atomic {atomic_task["id"]} did not pass its boundary check',
                }
            )
            break

    artifacts = executor_artifacts(executor)
    artifacts.update(
        {
            "generated_program": "\n".join(program_parts),
            "atomic_tasks": atomic_tasks,
            "number_of_atomic_tasks": len(atomic_tasks),
            "atomic_programs": atomic_programs,
            "atomic_verifications": atomic_verifications,
            "planning_errors": planning_errors,
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
) -> Dict[str, Any]:
    started = time.perf_counter()
    call_start = len(client.calls)
    live_initial_graph = unity.reset_graph(int(config["benchmark"]["scene"]))
    cached_initial_path = RESULTS_ROOT / "environment_initial_state.json"
    with cached_initial_path.open("r", encoding="utf-8") as handle:
        initial_graph = json.load(handle)
    live_inventory = {
        (node["id"], node["class_name"]) for node in live_initial_graph["nodes"]
    }
    cached_inventory = {(node["id"], node["class_name"]) for node in initial_graph["nodes"]}
    if live_inventory != cached_inventory:
        raise RuntimeError("Unity reset inventory differs from cached Phase 0 initial graph")
    execution_unity_comm = (
        unity.comm if bool(config["virtualhome"].get("render_unity_actions", False)) else None
    )
    if method == "ProgPrompt-Full":
        artifacts = run_progprompt(
            client=client,
            task=task,
            initial_graph=initial_graph,
            unity_comm=execution_unity_comm,
            config=config,
        )
    elif method == "HPAF-Decomp-Static":
        artifacts = run_hpaf_static(
            client=client,
            task=task,
            initial_graph=initial_graph,
            unity_comm=execution_unity_comm,
            config=config,
        )
    elif method == "HPAF-Decomp-ClosedLoop":
        artifacts = run_hpaf_closed_loop(
            client=client,
            task=task,
            initial_graph=initial_graph,
            unity_comm=execution_unity_comm,
            config=config,
        )
    else:
        raise ValueError(method)

    calls = client.calls[call_start:]
    metrics = evaluate_task(
        final_state=artifacts.pop("final_state"),
        ground_truth_final_state=task.final_state,
        initial_state=initial_graph,
        exec_ratio=float(artifacts.pop("Exec")),
    )
    errors = artifacts["planning_errors"] + artifacts["execution_errors"]
    error_type, error_message = first_error(errors)
    timestamp = datetime.now(timezone.utc).isoformat()
    run_id = f'{timestamp.replace(":", "").replace("+", "_")}_{slug(method)}_{slug(task.task)}'
    return {
        "run_id": run_id,
        "timestamp": timestamp,
        "task": task.task,
        "method": method,
        "provider": client.provider,
        "model": client.model,
        "api_interface": client.api_interface,
        "temperature": float(config["llm"]["temperature"]),
        "max_tokens": int(config["llm"]["max_tokens"]),
        "seed": config["llm"].get("seed"),
        "scene": int(config["benchmark"]["scene"]),
        "initial_state_sha256": graph_hash(initial_graph),
        "ground_truth_action_length": task.ground_truth_action_length,
        "difficulty_bucket": task.difficulty_bucket,
        "goal_condition_count": metrics["goal_condition_count"],
        "atomic_tasks": artifacts["atomic_tasks"],
        "number_of_atomic_tasks": artifacts["number_of_atomic_tasks"],
        "atomic_programs": artifacts["atomic_programs"],
        "atomic_verifications": artifacts["atomic_verifications"],
        "raw_prompts": [
            {"instructions": call.instructions, "input": call.prompt} for call in calls
        ],
        "raw_model_outputs": [call.raw_output for call in calls],
        "llm_call_records": [call.to_dict() for call in calls],
        "generated_program": artifacts["generated_program"],
        "compiled_virtualhome_actions": artifacts["compiled_virtualhome_actions"],
        "execution_trace": artifacts["execution_trace"],
        "graph_execution_trace": artifacts["graph_execution_trace"],
        "SR": metrics["SR"],
        "GCR": metrics["GCR"],
        "PSR": metrics["PSR"],
        "Precision": metrics["Precision"],
        "Exec": metrics["Exec"],
        "program_length": artifacts["program_length"],
        "llm_calls": len(calls),
        "prompt_tokens": sum_optional(calls, "prompt_tokens"),
        "completion_tokens": sum_optional(calls, "completion_tokens"),
        "planning_latency": sum(call.latency_s for call in calls),
        "wall_clock_total_s": time.perf_counter() - started,
        "error_type": error_type,
        "error_message": error_message,
        "errors": errors,
        "missing_goal_relations": metrics["missing_goal_relations"],
        "missing_goal_states": metrics["missing_goal_states"],
    }


def load_existing_pairs(path: Path) -> set[tuple[str, str]]:
    pairs = set()
    if not path.exists():
        return pairs
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                pairs.add((row["task"], row["method"]))
    return pairs


def save_run(output_root: Path, record: Dict[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    runs_dir = output_root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_path = runs_dir / f'{slug(record["method"])}__{slug(record["task"])}.json'
    with run_path.open("w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
    with (output_root / "raw_runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=EXPERIMENT_ROOT / "configs" / "benchmark.yaml",
    )
    parser.add_argument("--tasks", nargs="+", required=True)
    parser.add_argument("--methods", nargs="+", choices=METHODS, required=True)
    parser.add_argument("--output-root", type=Path, default=RESULTS_ROOT)
    parser.add_argument("--provider", choices=["primary", "fallback"])
    args = parser.parse_args()

    with args.config.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    records = load_task_records(config["benchmark"]["test_set"])
    record_by_task = {record.task: record for record in records}
    missing = [task for task in args.tasks if task not in record_by_task]
    if missing:
        raise KeyError(f"Unknown task(s): {missing}")

    provider_key = args.provider or config["llm"].get("active_provider", "primary")
    provider_spec = {
        **config["llm"][provider_key],
        "timeout_s": config["llm"]["primary"].get("timeout_s", 180),
        "wall_clock_timeout_s": config["llm"]["primary"].get(
            "wall_clock_timeout_s", 240
        ),
    }
    client = ModernLLMClient.from_env_spec(provider_spec)
    existing = load_existing_pairs(args.output_root / "raw_runs.jsonl")
    vh_config = config["virtualhome"]
    executable = PROJECT_ROOT / vh_config["executable"]
    with UnitySession(
        executable=executable,
        port=int(vh_config["port"]),
        no_graphics=bool(vh_config["no_graphics"]),
    ) as unity:
        for task_name in args.tasks:
            for method in args.methods:
                pair = (task_name, method)
                if pair in existing:
                    print(f"SKIP existing {method} :: {task_name}", flush=True)
                    continue
                print(f"RUN {method} :: {task_name}", flush=True)
                try:
                    result = run_one(
                        method=method,
                        task=record_by_task[task_name],
                        client=client,
                        unity=unity,
                        config=config,
                    )
                except Exception as exc:
                    # A task-level record must still exist for simulator/API
                    # failures; then stop so the issue can be diagnosed before
                    # continuing the ordered phases.
                    failure = {
                        "run_id": f"failed_{slug(method)}_{slug(task_name)}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "task": task_name,
                        "method": method,
                        "provider": client.provider,
                        "model": client.model,
                        "error_type": "simulator_or_api_error",
                        "error_message": str(exc),
                    }
                    save_run(args.output_root, failure)
                    raise
                save_run(args.output_root, result)
                existing.add(pair)
                print(
                    json.dumps(
                        {
                            "method": method,
                            "task": task_name,
                            "SR": result["SR"],
                            "GCR": result["GCR"],
                            "Exec": result["Exec"],
                            "llm_calls": result["llm_calls"],
                            "tokens": (result["prompt_tokens"] or 0)
                            + (result["completion_tokens"] or 0),
                            "error_type": result["error_type"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )


if __name__ == "__main__":
    main()
