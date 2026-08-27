"""Build the immutable-field-complete Phase-10R record delivery archive.

The append-only runner capture remains untouched.  This offline step adds only
the arithmetically derived per-call ``total_tokens`` field required by the
record schema and records source/delivery hashes for traceability.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from experiments.progprompt_vh.phase6.dataset import read_jsonl, sha256
from experiments.progprompt_vh.phase10_regression.protocol import (
    METHODS,
    ROOT,
    load_entries,
    verify_protocol_lock,
)
from experiments.progprompt_vh.phase10_regression.scripts.run_formal import COMPLETE, OUTPUT


SOURCE = OUTPUT / "raw_runs.jsonl"
DELIVERY = OUTPUT / "PHASE10R_FORMAL_RECORDS.jsonl"
AUDIT = OUTPUT / "FORMAL_RECORDS_AUDIT.json"


def finalize() -> Dict[str, Any]:
    if DELIVERY.exists() or AUDIT.exists():
        raise RuntimeError("Refusing to overwrite Phase-10R formal record delivery artifacts")
    verify_protocol_lock()
    if not COMPLETE.exists():
        raise RuntimeError("Phase-10R formal matrix is incomplete")
    complete = json.loads(COMPLETE.read_text(encoding="utf-8"))
    if sha256(SOURCE) != complete["raw_runs_sha256"]:
        raise RuntimeError("Source raw record hash does not match completion marker")

    rows = read_jsonl(SOURCE)
    task_ids = [entry["task_id"] for entry in load_entries()]
    expected = {(task_id, method) for task_id in task_ids for method in METHODS}
    actual = {(row["task_id"], row["method"]) for row in rows}
    if len(rows) != 120 or actual != expected:
        raise RuntimeError("Phase-10R source record matrix is not exactly 120 unique pairs")

    call_count = 0
    enriched: List[Dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        calls = []
        for source_call in row["llm_call_records"]:
            call = dict(source_call)
            derived_total = int(call["prompt_tokens"]) + int(call["completion_tokens"])
            if "total_tokens" in call and int(call["total_tokens"]) != derived_total:
                raise RuntimeError("Existing per-call total_tokens disagrees with token components")
            call["total_tokens"] = derived_total
            calls.append(call)
            call_count += 1
        record["llm_call_records"] = calls
        enriched.append(record)

    DELIVERY.parent.mkdir(parents=True, exist_ok=True)
    with DELIVERY.open("x", encoding="utf-8") as handle:
        for record in enriched:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    audit = {
        "status": "PASS",
        "transformation": "per-call total_tokens = prompt_tokens + completion_tokens only",
        "model_calls_added": 0,
        "scores_changed": 0,
        "records": len(enriched),
        "unique_task_method_pairs": len(actual),
        "llm_calls": call_count,
        "per_call_total_tokens_present": call_count,
        "source_raw_runs_sha256": complete["raw_runs_sha256"],
        "formal_records_sha256": sha256(DELIVERY),
    }
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return audit


if __name__ == "__main__":
    print(json.dumps(finalize(), ensure_ascii=False, indent=2))
