#!/usr/bin/env python3
"""Run and validate one Short, Medium, and Long task across three methods."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from experiments.progprompt_vh.phase6.runner import (
    PHASE6_ROOT,
    implementation_sha256,
    load_config,
    run_matrix,
    verify_protocol_lock,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", default="attempt_001")
    args = parser.parse_args()
    config = load_config()
    frozen = verify_protocol_lock(config)
    task_ids = config["benchmark"]["smoke_task_ids"]
    by_id = {item["task_id"]: item for item in frozen["selected"]}
    if [by_id[item]["horizon"] for item in task_ids] != ["Short", "Medium", "Long"]:
        raise RuntimeError("Smoke tasks are not exactly Short/Medium/Long")
    output = PHASE6_ROOT / "results/smoke" / args.attempt
    rows = run_matrix(output, task_ids, phase="smoke")
    prog = [row for row in rows if row["method"] == "ProgPrompt"]
    flat = [row for row in rows if row["method"] == "HPAF-Flat"]
    full = [row for row in rows if row["method"] == "HPAF-Full"]
    if sum(row["verification_calls"] for row in prog) <= 0:
        raise RuntimeError("Smoke failed: ProgPrompt made no assertion LLM calls")
    if not any(event["event"] == "recovery_skip" or str(event["line"]).startswith("else:") for row in prog for event in row["execution_trace"]):
        raise RuntimeError("Smoke failed: no ProgPrompt recovery branch was exercised or skipped")
    if any((row["generation_calls"], row["verification_calls"], row["repair_calls"]) != (1, 1, 0) for row in flat):
        raise RuntimeError("Smoke failed: Flat generation/verifier accounting")
    if any(not any(call["call_role"] == "task_agent" for call in row["llm_call_records"]) for row in full):
        raise RuntimeError("Smoke failed: Full TaskAgent was not called/costed")
    if any(row["verification_calls"] < row["atomic_tasks_attempted"] for row in full):
        raise RuntimeError("Smoke failed: Full missed per-atomic online verification")
    forbidden = ["FINAL SEMANTIC VERIFICATION TARGET", "semantic_goals.json", "ground-truth final", "official goal set"]
    for row in flat + full:
        for item in row["raw_prompts"]:
            if any(marker.lower() in item["input"].lower() for marker in forbidden):
                raise RuntimeError(f"Smoke failed: evaluator answer leakage in {row['task_id']}/{row['method']}")
    marker = {
        "passed_at": datetime.now(timezone.utc).isoformat(),
        "attempt": args.attempt,
        "record_count": len(rows),
        "task_ids": task_ids,
        "frozen_hashes": frozen["lock"],
        "implementation_sha256": implementation_sha256(),
        "progprompt_assertion_calls": sum(row["verification_calls"] for row in prog),
        "progprompt_recovery_events": sum(event["event"] == "recovery_skip" or str(event["line"]).startswith("else:") for row in prog for event in row["execution_trace"]),
        "full_taskagent_calls": sum(any(call["call_role"] == "task_agent" for call in row["llm_call_records"]) for row in full),
        "full_retry_count": sum(row["retry_count"] for row in full),
    }
    passed = PHASE6_ROOT / "results/smoke/PASSED.json"
    passed.parent.mkdir(parents=True, exist_ok=True)
    passed.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(marker, indent=2))
    print("PHASE-6 SMOKE PASSED", flush=True)


if __name__ == "__main__":
    main()

