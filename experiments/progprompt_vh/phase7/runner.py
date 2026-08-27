"""Phase-7 isolated runner built on the audited Phase-6 orchestration."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase5.evaluation.official_evaluator import evaluate_task
from experiments.progprompt_vh.phase6 import runner as phase6_runner
from experiments.progprompt_vh.phase6.dataset import load_final_graph, load_initial_graph, sha256
from experiments.progprompt_vh.phase6.verification.deterministic_evaluator import evaluate_conditions
from experiments.progprompt_vh.phase7.dataset import PHASE7_ROOT, build_manifests
from experiments.progprompt_vh.phase7.execution import Phase7GraphProgramExecutor
from experiments.progprompt_vh.phase7.methods import hpaf_flat, hpaf_full
from experiments.progprompt_vh.phase7.verification.trace_evaluator import evaluate_trace_goal


METHODS = ["ProgPrompt", "HPAF-Flat", "HPAF-Full"]
CONFIG_PATH = PHASE7_ROOT / "configs/benchmark.yaml"


def implementation_sha256() -> str:
    files = [
        PHASE7_ROOT / "runner.py", PHASE7_ROOT / "execution.py", PHASE7_ROOT / "dataset.py",
        PHASE7_ROOT / "configs/benchmark.yaml",
        PHASE7_ROOT / "methods/common.py", PHASE7_ROOT / "methods/hpaf_flat.py",
        PHASE7_ROOT / "methods/hpaf_full.py", PHASE7_ROOT / "verification/trace_evaluator.py",
        PROJECT_ROOT / "experiments/progprompt_vh/phase6/runner.py",
        PROJECT_ROOT / "experiments/progprompt_vh/phase6/methods/progprompt.py",
        PROJECT_ROOT / "experiments/progprompt_vh/phase6/verification/llm_verifier.py",
        PROJECT_ROOT / "experiments/progprompt_vh/phase6/verification/deterministic_evaluator.py",
        PROJECT_ROOT / "experiments/progprompt_vh/phase5/execution.py",
        PROJECT_ROOT / "experiments/progprompt_vh/phase5/methods/progprompt_graph_compatible.py",
        PROJECT_ROOT / "experiments/progprompt_vh/adapters/llm_client.py",
        PROJECT_ROOT / "experiments/progprompt_vh/adapters/virtualhome.py",
    ]
    payload = [(str(path.relative_to(PROJECT_ROOT)), sha256(path)) for path in files]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def load_config() -> Dict[str, Any]:
    import yaml
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def verify_protocol_lock() -> Dict[str, Any]:
    lock_path = PHASE7_ROOT / "data/protocol_lock.json"
    prompt_path = PHASE7_ROOT / "data/prompt_lock.json"
    if not lock_path.exists() or not prompt_path.exists():
        raise RuntimeError("Phase-7 protocol/prompt lock is missing")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    actual = {
        "prompt_lock_sha256": sha256(prompt_path),
        "dataset_stats_sha256": sha256(PHASE7_ROOT / "data/dataset_stats.json"),
        "trace_evaluator_sha256": sha256(PHASE7_ROOT / "verification/trace_evaluator.py"),
        "action_set_sha256": sha256(PROJECT_ROOT / "experiments/progprompt_vh/phase5/data/graph_supported_actions.json"),
        "config_sha256": sha256(CONFIG_PATH),
        "implementation_sha256": implementation_sha256(),
        "phase6_manifest_sha256": sha256(PROJECT_ROOT / "experiments/progprompt_vh/phase6/data/task_manifest.json"),
        "phase6_semantic_goals_sha256": sha256(PROJECT_ROOT / "experiments/progprompt_vh/phase6/data/semantic_goals.json"),
    }
    actual_manifests = {
        name: sha256(PHASE7_ROOT / "data" / f"{name}_manifest.json")
        for name in ["regression", "confirmatory", "combined"]
    }
    mismatch = {key: {"expected": lock.get(key), "actual": value} for key, value in actual.items() if lock.get(key) != value}
    if lock.get("manifest_sha256") != actual_manifests:
        mismatch["manifest_sha256"] = {"expected": lock.get("manifest_sha256"), "actual": actual_manifests}
    if mismatch:
        raise RuntimeError(f"Phase-7 frozen protocol mismatch: {json.dumps(mismatch)}")
    return lock


def _phase6_hooks() -> None:
    """Patch only this process's imported Phase-6 globals for isolation."""
    phase6_runner.GraphProgramExecutor = Phase7GraphProgramExecutor
    phase6_runner.generate_flat_program = hpaf_flat.generate_flat_program
    phase6_runner.generate_atomic_program = hpaf_full.generate_atomic_program
    phase6_runner.generate_repair_program = hpaf_full.generate_repair_program
    phase6_runner.generate_atomic_tasks = hpaf_full.generate_atomic_tasks


def load_frozen(set_name: str) -> Dict[str, Any]:
    data = build_manifests()
    if set_name not in data:
        raise KeyError(set_name)
    rows = data[set_name]
    semantic = {item["task_id"]: item for item in rows}
    lock = {
        "task_manifest_sha256": sha256(PHASE7_ROOT / "data" / f"{set_name}_manifest.json"),
        "semantic_goals_sha256": sha256(PHASE7_ROOT / "data" / f"{set_name}_manifest.json"),
        "long_horizon_manifest_sha256": sha256(PHASE7_ROOT / "data" / "dataset_stats.json"),
        "action_set_sha256": sha256(PROJECT_ROOT / "experiments/progprompt_vh/phase5/data/graph_supported_actions.json"),
    }
    return {
        "selected": rows,
        "actions": json.loads((PROJECT_ROOT / "experiments/progprompt_vh/phase5/data/graph_supported_actions.json").read_text()),
        "semantic": {"tasks": [{"task_id": key, "conditions": item["semantic_goal"]["conditions"]} for key, item in semantic.items()]},
        "lock": lock,
    }


def _score_record(record: Dict[str, Any], entry: Dict[str, Any]) -> None:
    if entry["evaluator_type"] == "generic_trace":
        semantic = evaluate_trace_goal(record, entry["trace_goal"], load_initial_graph(entry))
    else:
        semantic = evaluate_conditions(record["final_state_reconstructed"], entry["semantic_goal"]["conditions"])
    record.update(semantic)
    record["phase7_set"] = entry["set"]
    record["evaluator_type"] = entry["evaluator_type"]
    record["trace_goal"] = entry.get("trace_goal")


def run_one(method: str, entry: Dict[str, Any], client, unity, config: Dict[str, Any], frozen: Dict[str, Any], phase: str) -> Dict[str, Any]:
    _phase6_hooks()
    # phase6_runner.run_one performs execution, LLM role accounting, and official
    # metrics. Its proxy semantic result is replaced immediately by the frozen
    # Phase-7 persistent or trace predicate below.
    record = phase6_runner.run_one(method, entry, client, unity, config, frozen, phase)
    # The runner does not retain final_state after scoring. Reconstruct it from
    # the grounded trace using the audited offline executor, without new calls.
    executor = Phase7GraphProgramExecutor(
        load_initial_graph(entry), actions_payload=frozen["actions"], llm_client=None, unity_comm=None, seed=0
    )
    for action in record["graph_execution_trace"]:
        if action["parsed_action"] is None:
            executor.graph_executor.record_failed_attempt(action["source_action"], action["error"])
        else:
            trace = executor.graph_executor.execute_ground_truth_action(action["source_action"])
            if bool(trace.success) != bool(action["success"]) or (trace.error or "") != (action["error"] or ""):
                raise RuntimeError(f"Immediate replay mismatch: {record['task_id']}/{record['method']}")
            if trace.success:
                executor._refresh_evaluator_augmentations()
    record["final_state_reconstructed"] = executor.final_graph
    _score_record(record, entry)
    record.pop("final_state_reconstructed", None)
    record["implementation_sha256"] = implementation_sha256()
    record["task_manifest_sha256"] = frozen["lock"]["task_manifest_sha256"]
    record["semantic_goals_sha256"] = frozen["lock"]["semantic_goals_sha256"]
    record["long_horizon_manifest_sha256"] = frozen["lock"]["long_horizon_manifest_sha256"]
    return record


def _read_existing(path: Path) -> Dict[Tuple[str, str], Dict[str, Any]]:
    raw = path / "raw_runs.jsonl"
    if not raw.exists():
        return {}
    result = {}
    for line in raw.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            key = (row["task_id"], row["method"])
            if key in result:
                raise RuntimeError(f"Duplicate Phase-7 record: {key}")
            result[key] = row
    return result


def _save(output: Path, row: Dict[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "runs").mkdir(exist_ok=True)
    name = f"{row['method'].lower().replace('-', '_')}__{row['task_id'].replace('::', '__').replace(' ', '_').replace(',', '')}.json"
    (output / "runs" / name).write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output / "raw_runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_matrix(
    set_name: str, output: Path, phase: str, task_ids: Sequence[str] | None = None
) -> List[Dict[str, Any]]:
    verify_protocol_lock()
    config = load_config()
    frozen = load_frozen(set_name)
    all_ids = [item["task_id"] for item in frozen["selected"]]
    ids = list(task_ids) if task_ids is not None else all_ids
    if len(ids) != len(set(ids)) or any(task_id not in all_ids for task_id in ids):
        raise RuntimeError("Requested Phase-7 matrix has duplicate or out-of-set task IDs")
    by_id = {item["task_id"]: item for item in frozen["selected"]}
    existing = _read_existing(output)
    expected = {(task_id, method) for task_id in ids for method in METHODS}
    if not set(existing) <= expected:
        raise RuntimeError("Existing Phase-7 output contains out-of-set task")
    if len(existing) < len(expected):
        client = phase6_runner.make_client(config)
        vh = config["virtualhome"]
        with phase6_runner.UnitySession(PROJECT_ROOT / vh["executable"], int(vh["port"]), bool(vh["no_graphics"])) as unity:
            for task_id in ids:
                for method in METHODS:
                    if (task_id, method) in existing:
                        continue
                    print(f"RUN {set_name} {method} :: {task_id}", flush=True)
                    row = run_one(method, by_id[task_id], client, unity, config, frozen, phase)
                    _save(output, row)
                    existing[(task_id, method)] = row
    if set(existing) != expected:
        raise RuntimeError(f"Incomplete Phase-7 matrix: {len(existing)}/{len(expected)}")
    return list(existing.values())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("set_name", choices=["regression", "confirmatory", "combined"])
    args = parser.parse_args()
    rows = run_matrix(args.set_name, PHASE7_ROOT / "results" / args.set_name, phase="formal")
    print(json.dumps({"set": args.set_name, "records": len(rows), "new_calls": "external API calls permitted by protocol"}, indent=2))
