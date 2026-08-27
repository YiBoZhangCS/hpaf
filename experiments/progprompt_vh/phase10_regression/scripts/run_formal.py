"""Run the sole frozen 40 x 3 x 1 Phase-10R regression matrix."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.adapters.virtualhome import UnitySession
from experiments.progprompt_vh.phase6.dataset import sha256
from experiments.progprompt_vh.phase8 import runner as phase8_runner
from experiments.progprompt_vh.phase10 import runner as phase10_runner
from experiments.progprompt_vh.phase10_regression.protocol import (
    LOCK,
    MANIFEST,
    METHODS,
    ROOT,
    load_complexity,
    load_entries,
    verify_protocol_lock,
)


OUTPUT = ROOT / "results/formal"
STARTED = OUTPUT / "FORMAL_RUN_STARTED.json"
COMPLETE = OUTPUT / "FORMAL_RUN_COMPLETE.json"
INFRA_FAILURE = OUTPUT / "INFRASTRUCTURE_COMPATIBILITY_FAILURE.json"


def _write_once(path: Path, payload: Mapping[str, Any]) -> None:
    text = json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise RuntimeError(f"Refusing to overwrite Phase-10R marker: {path}")
        return
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def _parsed_output(call: Mapping[str, Any]) -> Any:
    text = str(call.get("output_text", ""))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _enrich(
    row: Dict[str, Any], entry: Mapping[str, Any], complexity: Mapping[str, Any]
) -> Dict[str, Any]:
    result = dict(row)
    result.update(
        {
            "instruction": entry["task_text"],
            "task_source": entry["source"],
            "official_or_extension": entry["official_or_extension"],
            "horizon": entry["horizon"],
            "is_long_horizon": bool(entry["is_long_horizon"]),
            "evaluator_type": entry["evaluator_type"],
            "benchmark_semantic_complexity": dict(complexity),
            "current_ready_nodes": [
                {
                    "atomic_id": record["atomic_task"]["id"],
                    "dependencies_ready": record.get("dependencies_ready", []),
                }
                for record in result.get("atomic_records", [])
            ],
        }
    )
    result["llm_call_records"] = [
        {**call, "parsed_output": _parsed_output(call)}
        for call in result["llm_call_records"]
    ]
    if result["method"] == "HPAF-Full":
        result["validator_result"] = {
            "parse_success": bool(result.get("taskagent_parse_success")),
            "rejected": bool(result.get("taskagent_validator_rejected")),
            "valid": bool(result.get("taskagent_parse_success"))
            and not bool(result.get("taskagent_validator_rejected")),
            "diagnostic": (
                result.get("error_message", "")
                if result.get("error_type", "").startswith("taskagent_")
                else ""
            ),
        }
    else:
        result["validator_result"] = None
    return result


def _assert_strict_binary(row: Mapping[str, Any]) -> None:
    calls = [
        call
        for call in row["llm_call_records"]
        if call["call_role"] == "assertion_verification"
    ]
    nonbinary = [
        {
            "raw_output": call.get("raw_output", ""),
            "output_text": call.get("output_text", ""),
        }
        for call in calls
        if str(call.get("output_text", "")).strip() not in {"True", "False"}
    ]
    if nonbinary:
        _write_once(
            INFRA_FAILURE,
            {
                "stopped_at": datetime.now(timezone.utc).isoformat(),
                "task_id": row["task_id"],
                "method": row["method"],
                "reason": "ProgPrompt assertion output violated strict binary contract",
                "nonbinary_outputs": nonbinary,
                "parser_or_prompt_modified": False,
            },
        )
        raise RuntimeError("Non-binary ProgPrompt assertion; Phase-10R stopped")


def _validate_enriched(row: Mapping[str, Any]) -> None:
    required = {
        "task_id",
        "method",
        "instruction",
        "scene",
        "task_source",
        "horizon",
        "evaluator_type",
        "llm_call_records",
        "semantic_GCR",
        "final_semantic_SR",
        "Exec",
        "semantic_condition_details",
        "benchmark_semantic_complexity",
        "validator_result",
    }
    missing = sorted(required - set(row))
    if missing:
        raise RuntimeError(f"Incomplete enriched record {row.get('task_id')}: {missing}")
    if any("parsed_output" not in call for call in row["llm_call_records"]):
        raise RuntimeError(f"Missing parsed LLM output in {row['task_id']}/{row['method']}")


def _recover_orphaned_record(
    existing: Dict[tuple[str, str], Dict[str, Any]],
    task_id: str,
    method: str,
) -> bool:
    """Recover a fully written per-run JSON without repeating its model calls."""
    pair = (task_id, method)
    run_path = OUTPUT / "runs" / (
        f"{phase8_runner.slug(method)}__{phase8_runner.slug(task_id)}.json"
    )
    if pair in existing or not run_path.exists():
        return False
    row = json.loads(run_path.read_text(encoding="utf-8"))
    if (row.get("task_id"), row.get("method")) != pair:
        raise RuntimeError(f"Orphaned run file identity mismatch: {run_path}")
    _validate_enriched(row)
    if method == "ProgPrompt-Compat":
        _assert_strict_binary(row)
    with (OUTPUT / "raw_runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    existing[pair] = row
    print(f"RECOVER completed pair without model call :: {method} :: {task_id}", flush=True)
    return True


def run() -> Dict[str, Any]:
    lock = verify_protocol_lock()
    if COMPLETE.exists():
        raise RuntimeError("Phase-10R formal matrix is complete; repeats are forbidden")
    if INFRA_FAILURE.exists():
        raise RuntimeError("Phase-10R has a recorded compatibility failure; do not resume")
    entries = load_entries()
    complexity = load_complexity()
    if not STARTED.exists():
        _write_once(
            STARTED,
            {
                "started_at": datetime.now(timezone.utc).isoformat(),
                "protocol_lock_sha256": sha256(LOCK),
                "method_sha256": lock["method_sha256"],
                "prompt_sha256": lock["prompt_sha256"],
                "manifest_sha256": lock["manifest_sha256"],
                "evaluator_sha256": lock["evaluator_sha256"],
                "method_order": METHODS,
                "execution_order": "task-major, method-minor",
                "records_required": 120,
                "planning_resamples": 0,
            },
        )

    phase10_runner.configure_runtime()
    config = phase8_runner.load_config()
    existing = phase8_runner.load_existing(OUTPUT)
    expected = {(entry["task_id"], method) for entry in entries for method in METHODS}
    if not set(existing) <= expected:
        raise RuntimeError("Existing Phase-10R output contains an out-of-matrix pair")
    for entry in entries:
        for method in METHODS:
            _recover_orphaned_record(existing, entry["task_id"], method)

    if len(existing) < len(expected):
        client = phase8_runner.make_client(config)
        vh = config["virtualhome"]
        with UnitySession(
            PROJECT_ROOT / vh["executable"],
            int(vh["port"]),
            bool(vh["no_graphics"]),
        ) as unity:
            for entry in entries:
                for method in METHODS:
                    pair = (entry["task_id"], method)
                    if pair in existing:
                        continue
                    print(f"RUN phase10r_formal/uncompressed {method} :: {entry['task_id']}", flush=True)
                    core = phase8_runner.run_one(
                        method,
                        entry,
                        client,
                        unity,
                        config,
                        phase="phase10r_formal",
                        representation="uncompressed",
                    )
                    row = _enrich(core, entry, complexity[entry["task_id"]])
                    if method == "ProgPrompt-Compat":
                        _assert_strict_binary(row)
                    _validate_enriched(row)
                    phase8_runner.save_run(OUTPUT, row)
                    existing[pair] = row

    rows = [existing[pair] for pair in sorted(expected)]
    phase8_runner.validate_complete_records(
        rows, [entry["task_id"] for entry in entries], METHODS, phase="phase10r_formal"
    )
    for row in rows:
        _validate_enriched(row)
        if row["method"] == "ProgPrompt-Compat":
            _assert_strict_binary(row)
    if any(row["task_manifest_sha256"] != sha256(MANIFEST) for row in rows):
        raise RuntimeError("A Phase-10R record has the wrong VH-40 manifest hash")
    if {row["implementation_sha256"] for row in rows} != {
        lock["runtime_implementation_sha256"]
    }:
        raise RuntimeError("A Phase-10R record has the wrong frozen runtime hash")
    pairs = {(row["task_id"], row["method"]) for row in rows}
    marker = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "records": len(rows),
        "unique_task_method_pairs": len(pairs),
        "duplicates": len(rows) - len(pairs),
        "planning_resamples": 0,
        "post_result_task_filtering": 0,
        "prompt_changes_after_start": 0,
        "evaluator_changes_after_start": 0,
        "raw_runs_sha256": sha256(OUTPUT / "raw_runs.jsonl"),
        "protocol_lock_sha256": sha256(LOCK),
    }
    if marker["records"] != 120 or marker["unique_task_method_pairs"] != 120:
        raise RuntimeError(f"Phase-10R matrix incomplete: {marker}")
    _write_once(COMPLETE, marker)
    return marker


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
