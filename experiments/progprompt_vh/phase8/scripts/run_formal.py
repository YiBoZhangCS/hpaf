"""Execute the one frozen 30 x 3 Phase-8 formal matrix."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import sha256
from experiments.progprompt_vh.phase8 import runner
from experiments.progprompt_vh.phase8.scripts import generate_compositional_benchmark as generator


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase8"
OUTPUT = ROOT / "results/final"
STARTED = OUTPUT / "FORMAL_RUN_STARTED.json"
COMPLETE = OUTPUT / "FORMAL_RUN_COMPLETE.json"


def verify_final_lock() -> Dict[str, Any]:
    lock = json.loads(generator.LOCK_PATH.read_text(encoding="utf-8"))
    checks = {
        "manifest_sha256": sha256(generator.MANIFEST_PATH),
        "reference_final_states_sha256": sha256(generator.FINAL_STATES_PATH),
        "protocol_sha256": sha256(generator.PROTOCOL_PATH),
        "process_prompt_lock_sha256": sha256(generator.PROCESS_LOCK),
        "token_compression_lock_sha256": sha256(generator.COMPRESSION_LOCK),
        "method_bundle_sha256": generator._bundle_hash(generator.METHOD_FILES),
        "evaluator_bundle_sha256": generator._bundle_hash(generator.EVALUATOR_FILES),
        "action_set_sha256": sha256(generator.ACTION_PATH),
    }
    mismatch = {
        key: {"expected": lock.get(key), "actual": value}
        for key, value in checks.items()
        if lock.get(key) != value
    }
    if mismatch:
        raise RuntimeError(f"Frozen Phase-8 protocol mismatch: {json.dumps(mismatch)}")
    compression = json.loads(generator.COMPRESSION_LOCK.read_text(encoding="utf-8"))
    if compression.get("adopted_representation") not in {"compressed", "uncompressed"}:
        raise RuntimeError("Frozen compression lock has no valid adopted representation")
    entries = runner.load_final_entries()
    if lock.get("records_required") != len(entries) * len(runner.METHODS):
        raise RuntimeError("Frozen formal record count is inconsistent")
    return lock


def _write_once(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise RuntimeError(f"Refusing to overwrite marker: {path}")
        return
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def run() -> Dict[str, Any]:
    lock = verify_final_lock()
    representation = lock_representation()
    if COMPLETE.exists():
        raise RuntimeError("Formal Phase-8 matrix is already complete; repeats are forbidden")
    if not STARTED.exists():
        _write_once(
            STARTED,
            {
                "started_at": datetime.now(timezone.utc).isoformat(),
                "final_protocol_lock_sha256": sha256(generator.LOCK_PATH),
                "manifest_sha256": lock["manifest_sha256"],
                "methods": runner.METHODS,
                "order": "task-major, method-minor",
                "representation": representation,
                "records_required": 90,
            },
        )
    rows = runner.run_matrix(
        entries=runner.load_final_entries(),
        methods=runner.METHODS,
        output_root=OUTPUT,
        phase="formal",
        representation=representation,
    )
    if len(rows) != 90 or len({(row["task_id"], row["method"]) for row in rows}) != 90:
        raise RuntimeError("Formal matrix is not exactly 90 unique records")
    marker = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "records": 90,
        "unique_task_method_pairs": 90,
        "raw_runs_sha256": sha256(OUTPUT / "raw_runs.jsonl"),
        "final_protocol_lock_sha256": sha256(generator.LOCK_PATH),
        "no_repeats": True,
    }
    _write_once(COMPLETE, marker)
    return marker


def lock_representation() -> str:
    compression = json.loads(generator.COMPRESSION_LOCK.read_text(encoding="utf-8"))
    representation = compression.get("adopted_representation")
    if representation not in {"compressed", "uncompressed"}:
        raise RuntimeError("Invalid adopted representation in compression lock")
    return str(representation)


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
