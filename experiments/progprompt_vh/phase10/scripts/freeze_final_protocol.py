"""Lock method, prompts, final manifest, and evaluator before the sole final run."""

from __future__ import annotations

import json

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import sha256
from experiments.progprompt_vh.phase10 import runner
from experiments.progprompt_vh.phase10.scripts.freeze_method import (
    LOCK as METHOD_LOCK,
    verify_method_freeze,
)


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase10"
LOCK = ROOT / "PHASE10_EXPERIMENT_LOCK.json"


def freeze() -> dict:
    if LOCK.exists():
        raise RuntimeError("Phase-10 final experiment protocol is already frozen")
    method = verify_method_freeze()
    entries = runner.load_final_entries()
    payload = {
        "schema_version": 1,
        "status": "FINAL_PROTOCOL_FROZEN",
        "seed": 20260827,
        "records_required": 36,
        "task_count": 12,
        "method_order": runner.METHODS,
        "runs_per_pair": 1,
        "resample_allowed": False,
        "post_result_filtering_allowed": False,
        "post_start_prompt_change_allowed": False,
        "post_start_evaluator_change_allowed": False,
        "method_freeze_sha256": sha256(METHOD_LOCK),
        "method_sha256": method["method_sha256"],
        "prompt_sha256": method["prompt_sha256"],
        "manifest_sha256": sha256(runner.FINAL_MANIFEST),
        "evaluator_sha256": method["evaluator_sha256"],
        "config_sha256": method["config_sha256"],
        "task_ids": [item["task_id"] for item in entries],
    }
    with LOCK.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def verify_final_lock() -> dict:
    if not LOCK.exists():
        raise RuntimeError("Phase-10 final experiment lock is absent")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    method = verify_method_freeze()
    checks = {
        "method_freeze_sha256": sha256(METHOD_LOCK),
        "method_sha256": method["method_sha256"],
        "prompt_sha256": method["prompt_sha256"],
        "manifest_sha256": sha256(runner.FINAL_MANIFEST),
        "evaluator_sha256": method["evaluator_sha256"],
        "config_sha256": method["config_sha256"],
    }
    mismatch = {
        key: {"expected": lock.get(key), "actual": value}
        for key, value in checks.items()
        if lock.get(key) != value
    }
    if mismatch:
        raise RuntimeError(f"Phase-10 final protocol mismatch: {json.dumps(mismatch)}")
    if lock.get("records_required") != 36 or lock.get("method_order") != runner.METHODS:
        raise RuntimeError("Phase-10 final record count or method order is invalid")
    return lock


if __name__ == "__main__":
    print(json.dumps(freeze(), ensure_ascii=False, indent=2))

