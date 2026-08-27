"""Execute the sole frozen 12 x 3 x 1 Phase-10 final matrix."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import sha256
from experiments.progprompt_vh.phase10 import runner
from experiments.progprompt_vh.phase10.scripts.freeze_final_protocol import (
    LOCK,
    verify_final_lock,
)


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase10"
OUTPUT = ROOT / "results/final"
STARTED = OUTPUT / "FORMAL_RUN_STARTED.json"
COMPLETE = OUTPUT / "FORMAL_RUN_COMPLETE.json"


def _write_once(path, payload):
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise RuntimeError(f"Refusing to overwrite formal marker: {path}")
        return
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def run() -> dict:
    lock = verify_final_lock()
    if COMPLETE.exists():
        raise RuntimeError("Phase-10 final matrix is complete; repeats are forbidden")
    if not STARTED.exists():
        _write_once(
            STARTED,
            {
                "started_at": datetime.now(timezone.utc).isoformat(),
                "protocol_lock_sha256": sha256(LOCK),
                "manifest_sha256": lock["manifest_sha256"],
                "method_order": runner.METHODS,
                "records_required": 36,
                "planning_resamples": 0,
            },
        )
    rows = runner.run_matrix(
        entries=runner.load_final_entries(),
        methods=runner.METHODS,
        output_root=OUTPUT,
        phase="formal",
    )
    pairs = {(item["task_id"], item["method"]) for item in rows}
    if len(rows) != 36 or len(pairs) != 36:
        raise RuntimeError("Final matrix is not exactly 36 unique task-method records")
    marker = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "records": 36,
        "unique_task_method_pairs": 36,
        "duplicates": 0,
        "planning_resamples": 0,
        "post_result_task_filtering": 0,
        "raw_runs_sha256": sha256(OUTPUT / "raw_runs.jsonl"),
        "protocol_lock_sha256": sha256(LOCK),
    }
    _write_once(COMPLETE, marker)
    return marker


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))

