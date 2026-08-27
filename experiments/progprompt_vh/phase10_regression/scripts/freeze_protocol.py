"""Freeze Phase-10R identities before the unified regression starts."""

from __future__ import annotations

import json

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import sha256
from experiments.progprompt_vh.phase10_regression.protocol import (
    LOCK,
    METHODS,
    ROOT,
    current_identity,
)


RUNNER = ROOT / "scripts/run_formal.py"
PROTOCOL = ROOT / "protocol.py"


def freeze() -> dict:
    if LOCK.exists():
        raise RuntimeError("Phase-10R protocol is already frozen")
    formal_root = ROOT / "results/formal"
    if (formal_root / "FORMAL_RUN_STARTED.json").exists() or (
        formal_root / "raw_runs.jsonl"
    ).exists():
        raise RuntimeError("Cannot freeze after formal execution has started")
    payload = {
        "schema_version": 1,
        "status": "PHASE10R_UNIFIED_REGRESSION_FROZEN",
        "experiment_name": "VH-40 Unified Regression Matrix",
        "classification": "REGRESSION_MATRIX_NOT_UNSEEN_OR_HELD_OUT",
        "records_required": 120,
        "runs_per_pair": 1,
        "method_order": METHODS,
        "execution_order": "task-major, method-minor",
        "planning_resamples_allowed": False,
        "post_result_filtering_allowed": False,
        "method_changes_after_start_allowed": False,
        "evaluator_changes_after_start_allowed": False,
        "orchestration_sha256": sha256(RUNNER),
        "protocol_code_sha256": sha256(PROTOCOL),
        **current_identity(),
    }
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


if __name__ == "__main__":
    print(json.dumps(freeze(), ensure_ascii=False, indent=2))
