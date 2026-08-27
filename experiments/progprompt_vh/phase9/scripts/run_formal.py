"""Execute the one frozen 40 x 3 VH-40 formal matrix."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import sha256
from experiments.progprompt_vh.phase9 import runner


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase9"
OUTPUT = ROOT / "results/formal"
LOCK_PATH = ROOT / "data/VH40_PROTOCOL_LOCK.json"
STARTED = OUTPUT / "FORMAL_RUN_STARTED.json"
COMPLETE = OUTPUT / "FORMAL_RUN_COMPLETE.json"
ACTION_PATH = PROJECT_ROOT / "experiments/progprompt_vh/phase5/data/graph_supported_actions.json"


def _bundle_hash(paths: Iterable[Path]) -> str:
    payload = [(str(path.relative_to(PROJECT_ROOT)), sha256(path)) for path in paths]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def verify_lock() -> Dict[str, Any]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    checks = {
        "manifest_sha256": sha256(runner.MANIFEST_PATH),
        "protocol_sha256": sha256(ROOT / "VH40_PROTOCOL.md"),
        "long11_manifest_sha256": sha256(ROOT / "data/long11_manifest.json"),
        "long11_reference_states_sha256": sha256(ROOT / "data/long11_reference_final_states.jsonl"),
        "token_final_lock_sha256": sha256(runner.TOKEN_LOCK_PATH),
        "config_sha256": sha256(runner.CONFIG_PATH),
        "method_bundle_sha256": _bundle_hash(runner.METHOD_IMPLEMENTATION_FILES),
        "evaluator_bundle_sha256": _bundle_hash(runner.EVALUATOR_FILES),
        "action_set_sha256": sha256(ACTION_PATH),
    }
    mismatch = {
        key: {"expected": lock.get(key), "actual": value}
        for key, value in checks.items() if lock.get(key) != value
    }
    if mismatch:
        raise RuntimeError(f"Frozen VH-40 protocol mismatch: {json.dumps(mismatch)}")
    if lock.get("records_required") != 120 or lock.get("method_order") != runner.METHODS:
        raise RuntimeError("Frozen record count/method order invalid")
    return lock


def _write_once(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise RuntimeError(f"Refusing to overwrite formal marker: {path}")
        return
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def run() -> Dict[str, Any]:
    lock = verify_lock()
    if COMPLETE.exists():
        raise RuntimeError("VH-40 formal matrix already complete; repeats are forbidden")
    if not STARTED.exists():
        _write_once(STARTED, {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "protocol_lock_sha256": sha256(LOCK_PATH),
            "manifest_sha256": lock["manifest_sha256"],
            "methods": runner.METHODS,
            "order": "task-major, method-minor",
            "records_required": 120,
            "planning_resamples": 0,
        })
    rows = runner.run_matrix(
        entries=runner.load_entries(), output_root=OUTPUT, phase="vh40_formal"
    )
    pairs = {(row["task_id"], row["method"]) for row in rows}
    if len(rows) != 120 or len(pairs) != 120:
        raise RuntimeError("Formal matrix is not exactly 120 unique records")
    marker = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "records": 120,
        "unique_task_method_pairs": 120,
        "duplicates": 0,
        "planning_resamples": 0,
        "post_result_task_filtering": 0,
        "raw_runs_sha256": sha256(OUTPUT / "raw_runs.jsonl"),
        "protocol_lock_sha256": sha256(LOCK_PATH),
    }
    _write_once(COMPLETE, marker)
    return marker


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
