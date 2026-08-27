#!/usr/bin/env python3
"""Run one locked Medium+Long × three-method Phase-5 smoke attempt."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from experiments.progprompt_vh.phase5.runner import (
    PHASE5_ROOT,
    load_config,
    run_matrix,
    verify_protocol_lock,
)


def next_attempt(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    numbers = []
    for path in root.glob("attempt_*"):
        match = re.fullmatch(r"attempt_(\d+)", path.name)
        if match:
            numbers.append(int(match.group(1)))
    return root / f"attempt_{max(numbers, default=0) + 1:03d}"


def main() -> None:
    config = load_config()
    frozen = verify_protocol_lock(config)
    tasks = list(config["benchmark"]["smoke_tasks"])
    if len(tasks) != 2:
        raise RuntimeError("Smoke protocol requires exactly two tasks")
    attempt = next_attempt(PHASE5_ROOT / "results/smoke")
    rows = run_matrix(output_root=attempt, task_names=tasks, phase="smoke")
    marker = {
        "passed_at": datetime.now(timezone.utc).isoformat(),
        "attempt": str(attempt.relative_to(PHASE5_ROOT)),
        "record_count": len(rows),
        "tasks": tasks,
        "hashes": frozen["lock"],
        "verified_but_stopped_count": sum(
            int(row["verified_but_stopped_count"]) for row in rows
        ),
    }
    marker_path = PHASE5_ROOT / "results/smoke/PASSED.json"
    marker_path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    print(f"SMOKE PASSED :: {attempt}", flush=True)


if __name__ == "__main__":
    main()

