"""Phase-10 development/final orchestration with structured DAG execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.adapters.virtualhome import available_object_classes
from experiments.progprompt_vh.phase6.verification.deterministic_evaluator import (
    evaluate_conditions,
)
from experiments.progprompt_vh.phase7.verification.trace_evaluator import (
    evaluate_trace_goal,
)
from experiments.progprompt_vh.phase8 import runner as phase8_runner
from experiments.progprompt_vh.phase8.methods.hpaf_full import generate_repair_program
from experiments.progprompt_vh.phase10.verification.online_verifier import (
    verify_task_completion,
)
from experiments.progprompt_vh.phase10.ir import topological_order
from experiments.progprompt_vh.phase10.methods.hpaf_full import (
    generate_atomic_program,
    generate_structured_ir,
)
from experiments.progprompt_vh.phase10.verification.partial_order_evaluator import (
    evaluate_partial_order_goal,
    phase9_goal_to_partial_order,
)


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase10"
CONFIG_PATH = ROOT / "configs/benchmark.yaml"
DEVELOPMENT_MANIFEST = PROJECT_ROOT / "experiments/progprompt_vh/phase9/data/vh40_manifest.json"
FINAL_MANIFEST = ROOT / "PHASE10_FINAL_HOLDOUT_MANIFEST.json"
METHODS = ["ProgPrompt-Compat", "HPAF-Flat", "HPAF-Full"]

METHOD_IMPLEMENTATION_FILES = [
    ROOT / "runner.py",
    ROOT / "ir.py",
    ROOT / "methods/hpaf_full.py",
    ROOT / "verification/online_verifier.py",
    CONFIG_PATH,
    PROJECT_ROOT / "experiments/progprompt_vh/adapters/llm_client.py",
    PROJECT_ROOT / "experiments/progprompt_vh/adapters/virtualhome.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/compat_client.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/execution.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/representation.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/methods/common.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/methods/hpaf_flat.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/verification/llm_verifier.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase6/methods/progprompt.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase6/methods/common.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase5/execution.py",
]
EVALUATOR_FILES = [
    ROOT / "verification/partial_order_evaluator.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase6/verification/deterministic_evaluator.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase7/verification/trace_evaluator.py",
]


def load_development_entries() -> List[Dict[str, Any]]:
    rows = json.loads(DEVELOPMENT_MANIFEST.read_text(encoding="utf-8"))["entries"]
    if len(rows) != 40 or len({item["task_id"] for item in rows}) != 40:
        raise RuntimeError("Phase-10 development regression requires the 40 unique VH-40 tasks")
    return rows


def load_final_entries() -> List[Dict[str, Any]]:
    rows = json.loads(FINAL_MANIFEST.read_text(encoding="utf-8"))["entries"]
    if len(rows) != 12 or len({item["task_id"] for item in rows}) != 12:
        raise RuntimeError("Phase-10 final manifest requires 12 unique tasks")
    return rows


def _score(
    final_state: Dict[str, Any],
    artifacts: Dict[str, Any],
    entry: Dict[str, Any],
    initial_graph: Dict[str, Any],
) -> Dict[str, Any]:
    evaluator_type = entry.get("evaluator_type")
    record_view = {"graph_execution_trace": artifacts["graph_execution_trace"]}
    if evaluator_type == "semantic_partial_order":
        return evaluate_partial_order_goal(record_view, entry["gold_semantics"], final_state)
    if evaluator_type == "generic_causal_trace_state":
        goal = phase9_goal_to_partial_order(entry["causal_goal"], entry["category"])
        return evaluate_partial_order_goal(record_view, goal, final_state)
    if evaluator_type == "generic_trace":
        return evaluate_trace_goal(record_view, entry["trace_goal"], initial_graph)
    if evaluator_type == "persistent_state":
        return evaluate_conditions(final_state, entry["semantic_goal"]["conditions"])
    raise ValueError(f"Unsupported Phase-10 evaluator type: {evaluator_type}")


def _explicit_objects(
    atomic: Mapping[str, Any], terminals: Sequence[Mapping[str, Any]]
) -> List[Optional[str]]:
    values: List[Optional[str]] = [
        atomic.get("focal_object"),
        atomic.get("source"),
        atomic.get("target"),
    ]
    for item in terminals:
        values.extend([item.get("subject"), item.get("object")])
    return values


def run_full(
    client,
    entry: Dict[str, Any],
    initial_graph: Dict[str, Any],
    actions: Dict[str, Any],
    unity_comm,
    config: Dict[str, Any],
    *,
    compact: bool,
) -> Dict[str, Any]:
    """Execute fresh-state atomics in stable topological order with Retry-1."""
    roles: List[str] = []
    executor = phase8_runner._new_executor(initial_graph, actions, client, unity_comm, config)
    objects = available_object_classes(initial_graph)
    ir, task_call, task_error = generate_structured_ir(
        client,
        task=entry["task_text"],
        objects=objects,
        llm_config=config["llm"],
    )
    roles.append("task_agent")
    parse_success = not bool(task_error and task_error.startswith("parse_failure:"))
    validator_rejected = bool(task_error and task_error.startswith("validator_rejection:"))
    planning_errors: List[Dict[str, Any]] = []
    if task_error:
        planning_errors.append(
            {
                "error_type": (
                    "taskagent_validator_rejection" if validator_rejected else "taskagent_parse_failure"
                ),
                "message": task_error,
            }
        )

    atomics = list(ir.get("atomic_tasks", []))
    terminals = list(ir.get("terminal_constraints", []))
    ordered = topological_order(ir) if not task_error else []
    records: List[Dict[str, Any]] = []
    programs: List[str] = []
    online_outputs: List[Dict[str, Any]] = []
    completed: set[str] = set()
    retry_count = 0
    early_stop = 1 if task_error else 0

    for position, atomic in enumerate(ordered):
        if not set(atomic["depends_on"]) <= completed:
            raise RuntimeError(f"Executor selected non-ready atomic {atomic['id']}")
        is_last = position == len(ordered) - 1
        active_terminals = terminals if is_last else []
        execution_contract = dict(atomic)
        execution_contract["terminal_constraints_at_task_end"] = active_terminals
        state = phase8_runner._state(
            executor.final_graph,
            task=entry["task_text"],
            atomic_task=execution_contract,
            errors=(),
            compact=compact,
        )
        event_start = len(executor.events)
        error_start = len(executor.error_events)
        data, _, program_error = generate_atomic_program(
            client,
            original_task=entry["task_text"],
            atomic_task=atomic,
            terminal_constraints=active_terminals,
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
            programs.append(f"# atomic {atomic['id']}: {atomic['semantic_goal']}\n{program}")
            executor.execute(program)
        first_trace = phase8_runner._event_slice(executor, event_start)
        first_errors = list(executor.error_events[error_start:])
        if program_error:
            first_errors.append(
                {"error_type": "parse_failure", "message": program_error, "line": ""}
            )
        observation = phase8_runner._state(
            executor.final_graph,
            task=entry["task_text"],
            atomic_task=execution_contract,
            errors=first_errors,
            compact=compact,
        )
        relevant = phase8_runner._relevant_objects(
            entry["task_text"],
            objects,
            _explicit_objects(atomic, active_terminals),
        )
        first_verifier, first_call, first_verifier_error = verify_task_completion(
            client,
            atomic_task=execution_contract,
            current_symbolic_observation=observation,
            relevant_objects=relevant,
            execution_context={
                "program": program,
                "execution_trace": phase8_runner._compact_trace(first_trace),
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
            repair_state = phase8_runner._state(
                executor.final_graph,
                task=entry["task_text"],
                atomic_task=execution_contract,
                errors=first_errors,
                compact=compact,
            )
            repair_data, _, repair_error = generate_repair_program(
                client,
                original_task=entry["task_text"],
                atomic_task=execution_contract,
                state=repair_state,
                objects=objects,
                actions_payload=actions,
                previous_program=program,
                failed_actions=(
                    phase8_runner._failed_actions(first_trace)
                    if compact
                    else phase8_runner._compact_trace(first_trace)
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
            repair_trace = phase8_runner._event_slice(executor, repair_event_start)
            repair_errors = list(executor.error_events[repair_error_start:])
            if repair_error:
                repair_errors.append(
                    {"error_type": "repair_parse_failure", "message": repair_error, "line": ""}
                )
            repair_observation = phase8_runner._state(
                executor.final_graph,
                task=entry["task_text"],
                atomic_task=execution_contract,
                errors=repair_errors,
                compact=compact,
            )
            repair_verifier, repair_call, repair_verifier_error = verify_task_completion(
                client,
                atomic_task=execution_contract,
                current_symbolic_observation=repair_observation,
                relevant_objects=relevant,
                execution_context={
                    "program": repair_program,
                    "execution_trace": phase8_runner._compact_trace(repair_trace),
                    "errors": repair_errors,
                    "previous_verifier": first_verifier,
                },
                llm_config=config["llm"],
                compact=compact,
            )
            roles.append("post_repair_verifier")
            online_outputs.append(
                {
                    "atomic_id": atomic["id"],
                    "attempt": "repair",
                    "observation": repair_observation,
                    "result": repair_verifier,
                    "raw_output": repair_call.raw_output,
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
                "dependencies_ready": sorted(set(atomic["depends_on"]) & completed),
                "terminal_constraints_active": active_terminals,
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
        completed.add(atomic["id"])

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
            and len(completed) == len(atomics),
            "taskagent_raw_output": task_call.raw_output,
            "llm_call_roles": roles,
            "structured_ir": ir,
            "taskagent_parse_success": parse_success,
            "taskagent_validator_rejected": validator_rejected,
            "dependency_execution_order": [item["atomic_task"]["id"] for item in records],
            "dependency_depth": int(ir.get("dependency_depth", 0)),
            "terminal_constraints": terminals,
            "terminal_constraint_count": len(terminals),
            "process_atomic_count": sum(item["type"] == "PROCESS" for item in atomics),
            "atomic_verifier_success_count": sum(item["final_done"] for item in records),
        }
    )
    return artifacts


def configure_runtime() -> None:
    phase8_runner.CONFIG_PATH = CONFIG_PATH
    phase8_runner.DEVELOPMENT_MANIFEST = DEVELOPMENT_MANIFEST
    phase8_runner.FINAL_MANIFEST = FINAL_MANIFEST
    phase8_runner.IMPLEMENTATION_FILES = [*METHOD_IMPLEMENTATION_FILES, *EVALUATOR_FILES]
    phase8_runner._score = _score
    phase8_runner.run_full = run_full


def run_matrix(
    *,
    entries: Sequence[Dict[str, Any]],
    methods: Sequence[str],
    output_root: Path,
    phase: str,
) -> List[Dict[str, Any]]:
    configure_runtime()
    return phase8_runner.run_matrix(
        entries=entries,
        methods=methods,
        output_root=output_root,
        phase=phase,
        representation="uncompressed",
    )
