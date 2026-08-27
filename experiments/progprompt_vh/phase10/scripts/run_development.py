"""Run one of at most two complete VH-40 HPAF-Full development iterations."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import sha256
from experiments.progprompt_vh.phase10 import runner


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase10"


def _write_once(path: Path, payload: Dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise RuntimeError(f"Refusing to overwrite development artifact: {path}")
        return
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def summarize(rows: List[Dict[str, Any]], iteration: int) -> Dict[str, Any]:
    entries = {item["task_id"]: item for item in runner.load_development_entries()}
    atomics = sum(item["number_of_atomic_tasks"] for item in rows)
    attempts = sum(item["atomic_tasks_attempted"] for item in rows)
    verifier_success = sum(item.get("atomic_verifier_success_count", 0) for item in rows)
    persistent = [
        item for item in rows
        if entries[item["task_id"]]["evaluator_type"] == "persistent_state"
    ]
    trace_process = [
        item for item in rows
        if entries[item["task_id"]]["evaluator_type"] == "generic_trace"
    ]
    long11 = [item for item in rows if item["task_id"].startswith("vh40_long_")]
    return {
        "iteration": iteration,
        "tasks": len(rows),
        "success": sum(item["final_semantic_SR"] for item in rows),
        "sr": mean(item["final_semantic_SR"] for item in rows),
        "macro_exec": mean(item["Exec"] for item in rows),
        "taskagent_parse_success_rate": mean(item.get("taskagent_parse_success", False) for item in rows),
        "validator_rejection_rate": mean(item.get("taskagent_validator_rejected", False) for item in rows),
        "mean_atomic_count": mean(item["number_of_atomic_tasks"] for item in rows),
        "mean_dependency_depth": mean(item.get("dependency_depth", 0) for item in rows),
        "mean_terminal_constraint_count": mean(item.get("terminal_constraint_count", 0) for item in rows),
        "atomic_verifier_success_rate": verifier_success / attempts if attempts else 0.0,
        "retry_rate_per_task": mean(item["retry_count"] for item in rows),
        "early_stop_rate": mean(item["early_stop_count"] for item in rows),
        "calls_per_task": mean(item["total_calls"] for item in rows),
        "tokens_per_task": mean(item["total_tokens"] for item in rows),
        "persistent_success": sum(item["final_semantic_SR"] for item in persistent),
        "persistent_n": len(persistent),
        "generic_trace_process_success": sum(item["final_semantic_SR"] for item in trace_process),
        "generic_trace_process_n": len(trace_process),
        "long11_success": sum(item["final_semantic_SR"] for item in long11),
        "long11_n": len(long11),
        "raw_runs_sha256": sha256(
            ROOT / f"results/development/iteration_{iteration}/raw_runs.jsonl"
        ),
    }


def run(iteration: int) -> Dict[str, Any]:
    if iteration not in {1, 2}:
        raise ValueError("Only development iterations 1 and 2 are allowed")
    output = ROOT / f"results/development/iteration_{iteration}"
    started = output / "DEVELOPMENT_STARTED.json"
    complete = output / "DEVELOPMENT_COMPLETE.json"
    summary_path = output / "metrics.json"
    if complete.exists():
        raise RuntimeError(f"Development iteration {iteration} is already complete")
    if iteration == 2 and not (
        ROOT / "results/development/iteration_1/DEVELOPMENT_COMPLETE.json"
    ).exists():
        raise RuntimeError("Iteration 1 must complete before iteration 2")
    if not started.exists():
        _write_once(
            started,
            {
                "iteration": iteration,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "tasks": 40,
                "methods": ["HPAF-Full"],
                "manifest_sha256": sha256(runner.DEVELOPMENT_MANIFEST),
                "config_sha256": sha256(runner.CONFIG_PATH),
            },
        )
    rows = runner.run_matrix(
        entries=runner.load_development_entries(),
        methods=["HPAF-Full"],
        output_root=output,
        phase=f"phase10_development_{iteration}",
    )
    metrics = summarize(rows, iteration)
    _write_once(summary_path, metrics)
    _write_once(
        complete,
        {
            "iteration": iteration,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "records": 40,
            "duplicates": 0,
            "planning_resamples": 0,
            "raw_runs_sha256": metrics["raw_runs_sha256"],
        },
    )
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iteration", type=int, choices=[1, 2], required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.iteration), ensure_ascii=False, indent=2))

