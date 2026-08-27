#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import yaml

from experiments.progprompt_vh.adapters.dataset import load_task_records
from experiments.progprompt_vh.adapters.evaluator import evaluate_task
from experiments.progprompt_vh.adapters.paths import EXPERIMENT_ROOT, PROJECT_ROOT, RESULTS_ROOT
from experiments.progprompt_vh.adapters.virtualhome import EvolvingGraphExecutor, UnitySession


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=EXPERIMENT_ROOT / "configs" / "benchmark.yaml",
    )
    parser.add_argument("--task", default="watch tv")
    args = parser.parse_args()

    with args.config.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    vh_config = config["virtualhome"]
    benchmark_config = config["benchmark"]
    executable = PROJECT_ROOT / vh_config["executable"]
    records = load_task_records(benchmark_config["test_set"])
    record_by_task = {record.task: record for record in records}
    if args.task not in record_by_task:
        raise KeyError(f"Unknown task: {args.task}")

    with UnitySession(
        executable=executable,
        port=int(vh_config["port"]),
        no_graphics=bool(vh_config["no_graphics"]),
    ) as unity:
        initial_graph = unity.reset_graph(int(benchmark_config["scene"]))
        save_json(RESULTS_ROOT / "environment_initial_state.json", initial_graph)

        record = record_by_task[args.task]
        executor = EvolvingGraphExecutor(initial_graph)
        for action in record.ground_truth_actions:
            executor.execute_ground_truth_action(action, unity=unity.comm)

    metrics = evaluate_task(
        final_state=executor.graph,
        ground_truth_final_state=record.final_state,
        initial_state=initial_graph,
        exec_ratio=executor.exec_ratio,
    )
    smoke = {
        "task": record.task,
        "scene": benchmark_config["scene"],
        "ground_truth_action_length": record.ground_truth_action_length,
        "compiled_virtualhome_actions": record.ground_truth_actions,
        "execution_trace": [trace.__dict__ for trace in executor.trace],
        "metrics": metrics,
        "status": "passed" if metrics["SR"] == 1 and metrics["Exec"] == 1 else "failed",
    }
    save_json(RESULTS_ROOT / "phase0_ground_truth_smoke.json", smoke)
    save_json(RESULTS_ROOT / "phase0_ground_truth_final_state.json", executor.graph)

    metadata_path = RESULTS_ROOT / "task_metadata.csv"
    with metadata_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "task",
                "ground_truth_action_length",
                "difficulty_bucket",
                "scene",
                "goal_condition_count",
                "source_file",
                "final_state_index",
            ],
        )
        writer.writeheader()
        for item in records:
            item_metrics = evaluate_task(
                final_state=initial_graph,
                ground_truth_final_state=item.final_state,
                initial_state=initial_graph,
                exec_ratio=0.0,
            )
            writer.writerow(
                {
                    "task": item.task,
                    "ground_truth_action_length": item.ground_truth_action_length,
                    "difficulty_bucket": item.difficulty_bucket,
                    "scene": benchmark_config["scene"],
                    "goal_condition_count": item_metrics["goal_condition_count"],
                    "source_file": item.source_file,
                    "final_state_index": item.final_state_index,
                }
            )

    print(json.dumps(smoke, ensure_ascii=False, indent=2))
    if smoke["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
