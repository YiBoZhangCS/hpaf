#!/usr/bin/env python3
"""Run the one allowed full Phase-6 held-out matrix."""

from __future__ import annotations

import json

from experiments.progprompt_vh.phase6.runner import (
    PHASE6_ROOT,
    implementation_sha256,
    load_config,
    run_matrix,
    verify_protocol_lock,
)


def main() -> None:
    config = load_config()
    frozen = verify_protocol_lock(config)
    marker_path = PHASE6_ROOT / "results/smoke/PASSED.json"
    if not marker_path.exists():
        raise RuntimeError("Formal run blocked: no passing complete Phase-6 smoke")
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    if marker.get("record_count") != 9 or marker.get("frozen_hashes") != frozen["lock"] or marker.get("implementation_sha256") != implementation_sha256():
        raise RuntimeError("Formal run blocked: smoke marker does not match frozen protocol/implementation")
    task_ids = [item["task_id"] for item in frozen["selected"]]
    rows = run_matrix(PHASE6_ROOT / "results", task_ids, phase="formal")
    if len(rows) != len(task_ids) * 3:
        raise RuntimeError("Formal matrix is incomplete")
    print(f"PHASE-6 FORMAL FIRST RUN COMPLETE :: {len(rows)} unique records", flush=True)


if __name__ == "__main__":
    main()

