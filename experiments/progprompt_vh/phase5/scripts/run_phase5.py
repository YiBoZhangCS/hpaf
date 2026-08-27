#!/usr/bin/env python3
"""Run the one allowed ordered 10-task × three-method formal matrix."""

from __future__ import annotations

import json

from experiments.progprompt_vh.adapters.dataset import load_task_records
from experiments.progprompt_vh.phase5.runner import (
    PHASE5_ROOT,
    load_config,
    run_matrix,
    verify_protocol_lock,
)


def main() -> None:
    config = load_config()
    frozen = verify_protocol_lock(config)
    marker_path = PHASE5_ROOT / "results/smoke/PASSED.json"
    if not marker_path.exists():
        raise RuntimeError("Formal run blocked: no complete Phase-5 smoke marker")
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    if marker.get("hashes") != frozen["lock"] or marker.get("record_count") != 6:
        raise RuntimeError("Formal run blocked: smoke marker does not match frozen protocol")
    if marker.get("verified_but_stopped_count") != 0:
        raise RuntimeError("Formal run blocked: smoke found verified-but-stopped")
    tasks = [
        record.task for record in load_task_records(config["benchmark"]["test_set"])
    ]
    rows = run_matrix(
        output_root=PHASE5_ROOT / "results",
        task_names=tasks,
        phase="formal",
    )
    if len(rows) != 30:
        raise RuntimeError("Formal matrix did not produce exactly 30 records")
    print("FORMAL FIRST RUN COMPLETE :: 30 unique records", flush=True)


if __name__ == "__main__":
    main()

