"""Run and freeze the bounded Phase-8 development protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Sequence

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import read_jsonl, sha256
from experiments.progprompt_vh.phase8 import runner


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase8"
RESULTS = ROOT / "results/development"
DATA = ROOT / "data"
PROCESS_LOCK = DATA / "PROCESS_PROMPT_LOCK.json"
COMPRESSION_LOCK = DATA / "TOKEN_COMPRESSION_LOCK.json"
HISTORY_PATH = DATA / "process_development_history.json"

PROCESS_FILES = [
    ROOT / "methods/common.py",
    ROOT / "methods/hpaf_flat.py",
    ROOT / "methods/hpaf_full.py",
    ROOT / "verification/llm_verifier.py",
]
COMPRESSION_FILES = [
    ROOT / "representation.py",
    ROOT / "methods/common.py",
    ROOT / "methods/hpaf_flat.py",
    ROOT / "methods/hpaf_full.py",
    ROOT / "verification/llm_verifier.py",
    ROOT / "runner.py",
    ROOT / "configs/benchmark.yaml",
]


def _bundle_hash(paths: Sequence[Path]) -> str:
    payload = [(str(path.relative_to(PROJECT_ROOT)), sha256(path)) for path in paths]
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    return {
        "n": len(rows),
        "success": sum(int(row["final_semantic_SR"]) for row in rows),
        "sr": mean(float(row["final_semantic_SR"]) for row in rows),
        "macro_exec": mean(float(row["Exec"]) for row in rows),
        "micro_exec": (
            sum(
                sum(int(item.get("success", False)) for item in row["graph_execution_trace"])
                for row in rows
            )
            / max(
                1,
                sum(len(row["graph_execution_trace"]) for row in rows),
            )
        ),
        "avg_tokens": mean(float(row["total_tokens"]) for row in rows),
        "avg_calls": mean(float(row["total_calls"]) for row in rows),
    }


def _phase7_full_metrics() -> Dict[str, Any]:
    regression = [
        row
        for row in read_jsonl(
            PROJECT_ROOT
            / "experiments/progprompt_vh/phase7/results/regression/raw_runs.jsonl"
        )
        if row["method"] == "HPAF-Full"
    ]
    process = [
        row
        for row in read_jsonl(
            PROJECT_ROOT
            / "experiments/progprompt_vh/phase7/results/confirmatory/raw_runs.jsonl"
        )
        if row["method"] == "HPAF-Full"
    ]
    return {"persistent": _metrics(regression), "process": _metrics(process)}


def _split_full(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    entries = {item["task_id"]: item for item in runner.load_development_entries()}
    persistent = [
        row for row in rows if entries[row["task_id"]]["evaluator_type"] == "persistent_state"
    ]
    process = [
        row for row in rows if entries[row["task_id"]]["evaluator_type"] == "generic_trace"
    ]
    return {
        "combined": _metrics(rows),
        "persistent": _metrics(persistent),
        "process": _metrics(process),
    }


def _write_once(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise RuntimeError(f"Refusing to overwrite frozen file: {path}")
        return
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def run_process() -> Dict[str, Any]:
    if PROCESS_LOCK.exists():
        return json.loads(PROCESS_LOCK.read_text(encoding="utf-8"))
    entries = runner.load_development_entries()
    rows = runner.run_matrix(
        entries=entries,
        methods=["HPAF-Full"],
        output_root=RESULTS / "full_uncompressed",
        phase="development_process",
        representation="uncompressed",
    )
    current = _split_full(rows)
    previous = _phase7_full_metrics()
    gate = {
        "persistent_success_at_least_19_of_20": current["persistent"]["success"] >= 19,
        "persistent_macro_exec_drop_at_most_0_01": (
            current["persistent"]["macro_exec"]
            >= previous["persistent"]["macro_exec"] - 0.01
        ),
        "process_success_not_below_phase7": (
            current["process"]["success"] >= previous["process"]["success"]
        ),
    }
    history = {
        "schema_version": 1,
        "maximum_iterations": 2,
        "iterations_used": 1,
        "iterations": [
            {
                "iteration": 1,
                "prompt_bundle_sha256": _bundle_hash(PROCESS_FILES),
                "metrics": current,
                "gate": gate,
            }
        ],
    }
    _write_once(HISTORY_PATH, history)
    if not all(gate.values()):
        raise RuntimeError(f"Process prompt failed development gate: {gate}")
    lock = {
        "schema_version": 1,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "development_only": True,
        "development_manifest_sha256": sha256(runner.DEVELOPMENT_MANIFEST),
        "prompt_bundle_sha256": _bundle_hash(PROCESS_FILES),
        "source_files": {
            str(path.relative_to(PROJECT_ROOT)): sha256(path) for path in PROCESS_FILES
        },
        "phase7_baseline": previous,
        "adopted_uncompressed_metrics": current,
        "gate": gate,
        "gate_pass": True,
        "prompt_development_iterations_used": 1,
    }
    _write_once(PROCESS_LOCK, lock)
    return lock


def run_compression() -> Dict[str, Any]:
    process = run_process()
    if not process.get("gate_pass"):
        raise RuntimeError("Process prompt is not frozen/passing")
    if COMPRESSION_LOCK.exists():
        return json.loads(COMPRESSION_LOCK.read_text(encoding="utf-8"))
    entries = runner.load_development_entries()
    compressed_rows = runner.run_matrix(
        entries=entries,
        methods=["HPAF-Full"],
        output_root=RESULTS / "full_compressed",
        phase="development_compression",
        representation="compressed",
    )
    uncompressed_rows = read_jsonl(RESULTS / "full_uncompressed/raw_runs.jsonl")
    uncompressed = _split_full(uncompressed_rows)
    compressed = _split_full(compressed_rows)
    token_reduction = 1.0 - (
        compressed["combined"]["avg_tokens"] / uncompressed["combined"]["avg_tokens"]
    )
    gate = {
        "success_drop_at_most_one_task": (
            compressed["combined"]["success"] >= uncompressed["combined"]["success"] - 1
        ),
        "macro_exec_drop_at_most_0_01": (
            compressed["combined"]["macro_exec"]
            >= uncompressed["combined"]["macro_exec"] - 0.01
        ),
        "token_reduction_at_least_15_percent": token_reduction >= 0.15,
    }
    adopted = "compressed" if all(gate.values()) else "uncompressed"
    lock = {
        "schema_version": 1,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "development_only": True,
        "complete_ab_runs_used": 1,
        "development_manifest_sha256": sha256(runner.DEVELOPMENT_MANIFEST),
        "process_prompt_lock_sha256": sha256(PROCESS_LOCK),
        "compression_bundle_sha256": _bundle_hash(COMPRESSION_FILES),
        "source_files": {
            str(path.relative_to(PROJECT_ROOT)): sha256(path) for path in COMPRESSION_FILES
        },
        "uncompressed_metrics": uncompressed,
        "compressed_metrics": compressed,
        "token_reduction_fraction": token_reduction,
        "gate": gate,
        "gate_pass": all(gate.values()),
        "adopted_representation": adopted,
    }
    _write_once(COMPRESSION_LOCK, lock)
    return lock


def run_supplementary() -> List[Dict[str, Any]]:
    lock = run_compression()
    representation = str(lock["adopted_representation"])
    entries = runner.load_development_entries()
    others = runner.run_matrix(
        entries=entries,
        methods=["ProgPrompt-Compat", "HPAF-Flat"],
        output_root=RESULTS / "supplementary",
        phase="development_supplementary",
        representation=representation,
    )
    full = read_jsonl(RESULTS / f"full_{representation}/raw_runs.jsonl")
    rows = [*others, *full]
    if len(rows) != 87:
        raise RuntimeError(f"Development supplementary matrix must have 87 rows, got {len(rows)}")
    table = []
    for method in runner.METHODS:
        selected = [row for row in rows if row["method"] == method]
        metrics = _metrics(selected)
        table.append({"method": method, **metrics})
    output = RESULTS / "official_development_regression.json"
    _write_once(
        output,
        {
            "label": "OFFICIAL DEVELOPMENT REGRESSION",
            "development_regression_only": True,
            "rows": table,
        },
    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "stage", choices=["process", "compression", "supplementary", "all"]
    )
    args = parser.parse_args()
    if args.stage == "process":
        result: Any = run_process()
    elif args.stage == "compression":
        result = run_compression()
    elif args.stage == "supplementary":
        result = {"records": len(run_supplementary())}
    else:
        result = {"records": len(run_supplementary())}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
