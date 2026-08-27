"""Freeze Phase-10 method/prompt/evaluator after development and before holdout."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import sha256
from experiments.progprompt_vh.phase10 import runner
from experiments.progprompt_vh.phase10.methods.hpaf_full import prompt_bundle_text


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase10"
LOCK = ROOT / "PHASE10_METHOD_FREEZE.json"
PROMPT_FILES = [
    PROJECT_ROOT / "experiments/progprompt_vh/phase6/methods/progprompt.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/methods/hpaf_flat.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase10/verification/online_verifier.py",
]


def bundle_hash(paths: Iterable[Path]) -> str:
    payload = [(str(path.relative_to(PROJECT_ROOT)), sha256(path)) for path in paths]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def current_hashes() -> Dict[str, str]:
    prompt_payload = prompt_bundle_text().encode("utf-8") + b"\n" + b"\n".join(
        path.read_bytes() for path in PROMPT_FILES
    )
    return {
        "method_sha256": bundle_hash(runner.METHOD_IMPLEMENTATION_FILES),
        "prompt_sha256": hashlib.sha256(prompt_payload).hexdigest(),
        "evaluator_sha256": bundle_hash(runner.EVALUATOR_FILES),
        "config_sha256": sha256(runner.CONFIG_PATH),
    }


def latest_development() -> tuple[int, Path, Dict[str, Any]]:
    for iteration in (2, 1):
        root = ROOT / f"results/development/iteration_{iteration}"
        complete = root / "DEVELOPMENT_COMPLETE.json"
        metrics = root / "metrics.json"
        if complete.exists() and metrics.exists():
            return iteration, root, json.loads(metrics.read_text(encoding="utf-8"))
    raise RuntimeError("A complete Phase-10 VH-40 development iteration is required")


def freeze() -> Dict[str, Any]:
    if LOCK.exists():
        raise RuntimeError("Phase-10 method is already frozen")
    iteration, development_root, metrics = latest_development()
    if metrics["taskagent_parse_success_rate"] != 1.0:
        raise RuntimeError("Cannot freeze: Structured IR parse success is below 100%")
    if metrics["validator_rejection_rate"] != 0.0:
        raise RuntimeError("Cannot freeze: semantic validator rejection is non-zero")
    rows_path = development_root / "raw_runs.jsonl"
    rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line]
    dependency_ok = all(
        set(record["atomic_task"]["depends_on"]) == set(record["dependencies_ready"])
        for row in rows
        for record in row["atomic_records"]
    )
    if not dependency_ok:
        raise RuntimeError("Cannot freeze: dependency execution audit failed")
    payload = {
        "schema_version": 1,
        "status": "METHOD_FROZEN_BEFORE_FINAL_HOLDOUT_GENERATION",
        "development_iteration_adopted": iteration,
        "development_records": len(rows),
        "development_raw_runs_sha256": sha256(rows_path),
        "development_metrics": metrics,
        "dependency_execution_audit": "PASS",
        "flat_has_taskagent": False,
        "flat_full_shared_program_rules": True,
        "gold_semantics_enter_method_prompt": False,
        **current_hashes(),
        "method_files": [str(path.relative_to(PROJECT_ROOT)) for path in runner.METHOD_IMPLEMENTATION_FILES],
        "evaluator_files": [str(path.relative_to(PROJECT_ROOT)) for path in runner.EVALUATOR_FILES],
    }
    with LOCK.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def verify_method_freeze() -> Dict[str, Any]:
    if not LOCK.exists():
        raise RuntimeError("Phase-10 method freeze is absent")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    current = current_hashes()
    mismatch = {
        key: {"expected": lock.get(key), "actual": value}
        for key, value in current.items()
        if lock.get(key) != value
    }
    if mismatch:
        raise RuntimeError(f"Frozen Phase-10 method mismatch: {json.dumps(mismatch)}")
    return lock


if __name__ == "__main__":
    print(json.dumps(freeze(), ensure_ascii=False, indent=2))
