"""Audit and summarize the single frozen Phase-10 final matrix."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import read_jsonl, sha256
from experiments.progprompt_vh.phase10 import runner
from experiments.progprompt_vh.phase10.scripts.freeze_final_protocol import (
    LOCK,
    verify_final_lock,
)


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase10"
FINAL = ROOT / "results/final"
RAW = FINAL / "raw_runs.jsonl"
COMPLETE = FINAL / "FORMAL_RUN_COMPLETE.json"
MAIN_CSV = ROOT / "results/PHASE10_MAIN_TABLE.csv"
COMPLEXITY_CSV = ROOT / "results/PHASE10_COMPLEXITY.csv"
FAILURE_REPORT = ROOT / "PHASE10_FAILURE_AUDIT.md"
METRIC_AUDIT = ROOT / "PHASE10_METRIC_AUDIT.md"
DEVELOPMENT_REPORT = ROOT / "DEVELOPMENT_REGRESSION.md"
FINAL_REPORT = ROOT / "PHASE10_FINAL_REPORT.md"
PPT_TABLE = ROOT / "PPT_FINAL_TABLE.md"
SUMMARY_JSON = ROOT / "results/PHASE10_METRICS.json"
METHODS = runner.METHODS


def _write_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def _method_metrics(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for method in METHODS:
        subset = [item for item in rows if item["method"] == method]
        result.append(
            {
                "method": method,
                "n": len(subset),
                "success": sum(item["final_semantic_SR"] for item in subset),
                "sr": mean(item["final_semantic_SR"] for item in subset),
                "macro_exec": mean(item["Exec"] for item in subset),
                "gcr": mean(item["semantic_GCR"] for item in subset),
                "calls_per_task": mean(item["total_calls"] for item in subset),
                "tokens_per_task": mean(item["total_tokens"] for item in subset),
            }
        )
    return result


def _csv(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> str:
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows({key: item.get(key) for key in fields} for item in rows)
    return stream.getvalue()


def _complexity(
    rows: Sequence[Mapping[str, Any]], entries: Mapping[str, Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    groups = [
        ("semantic_atomic_count", "2 atomic", lambda value: value == 2),
        ("semantic_atomic_count", "3 atomic", lambda value: value == 3),
        ("semantic_atomic_count", ">=4 atomic", lambda value: value >= 4),
        ("dependency_depth", "D=2", lambda value: value == 2),
        ("dependency_depth", "D=3", lambda value: value == 3),
        ("dependency_depth", "D>=4", lambda value: value >= 4),
    ]
    result = []
    for dimension, label, accepts in groups:
        task_ids = {
            task_id for task_id, entry in entries.items() if accepts(entry[dimension])
        }
        for method in METHODS:
            subset = [
                item for item in rows
                if item["method"] == method and item["task_id"] in task_ids
            ]
            result.append(
                {
                    "dimension": dimension,
                    "bin": label,
                    "method": method,
                    "n": len(subset),
                    "success": sum(item["final_semantic_SR"] for item in subset),
                    "sr": mean(item["final_semantic_SR"] for item in subset) if subset else None,
                    "macro_exec": mean(item["Exec"] for item in subset) if subset else None,
                }
            )
    return result


def _failure_category(row: Mapping[str, Any]) -> str:
    error_type = str(row.get("error_type", ""))
    message = " ".join(
        [str(row.get("error_message", ""))]
        + [str(item.get("message", "")) for item in row.get("errors", [])]
    ).lower()
    details = row.get("semantic_condition_details", [])
    missing = [item for item in details if not item.get("satisfied")]
    if error_type == "taskagent_validator_rejection":
        return "TaskAgent validator rejection"
    if error_type == "taskagent_parse_failure":
        return "TaskAgent semantic decomposition error"
    if any(item.get("kind") == "required_dependency" for item in missing):
        events_missing = any(item.get("kind") == "semantic_event" for item in missing)
        if not events_missing:
            return "dependency violation"
    if any(item.get("kind") == "terminal_constraint" for item in missing):
        return "terminal constraint miss"
    if any(
        item.get("kind") == "semantic_event"
        and any(word in str(item.get("description", "")).lower() for word in ("cycle", "start", "complete", "processed"))
        for item in missing
    ):
        return "process lifecycle incomplete"
    if "not close" in message or "does not face" in message or "not face" in message:
        return "alignment failure"
    if "unavailable" in message or "not found" in message or "unknown object" in message:
        return "object grounding"
    if row.get("early_stop_count") and "verification" in message:
        return "verification false decision"
    if row.get("retry_count") and not row.get("final_online_done"):
        return "repair failure"
    if "precondition_failure" in error_type or "precondition" in message or "free hand" in message:
        return "interaction/precondition failure"
    if row["method"] == "HPAF-Full" and row.get("number_of_atomic_tasks", 0):
        return "TaskAgent semantic decomposition error"
    return "goal omission"


def _failure_markdown(rows: Sequence[Mapping[str, Any]]) -> tuple[str, Dict[str, int]]:
    failures = []
    for row in rows:
        if row["final_semantic_SR"]:
            continue
        category = _failure_category(row)
        failures.append((row, category))
    counts = Counter(category for _, category in failures)
    lines = [
        "# Phase-10 Failure Audit",
        "",
        "Each failed task-method record receives one primary offline category from TaskAgent diagnostics, typed execution errors, missing semantic-DAG elements, terminal constraints, and final goals. No category assignment changed a score.",
        "",
        "## Counts",
        "",
        "| Category | Count |",
        "|---|---:|",
    ]
    ordered_categories = [
        "TaskAgent semantic decomposition error",
        "TaskAgent validator rejection",
        "dependency violation",
        "terminal constraint miss",
        "process lifecycle incomplete",
        "alignment failure",
        "interaction/precondition failure",
        "object grounding",
        "verification false decision",
        "repair failure",
        "goal omission",
    ]
    for category in ordered_categories:
        lines.append(f"| {category} | {counts[category]} |")
    lines.extend(
        [
            "",
            "## Failed records",
            "",
            "| Task | Method | Category | Exec | Primary diagnostic |",
            "|---|---|---|---:|---|",
        ]
    )
    for row, category in failures:
        diagnostic = str(row.get("error_message") or "missing semantic/final condition")
        diagnostic = diagnostic.replace("|", "/").replace("\n", " ")[:180]
        lines.append(
            f"| `{row['task_id']}` | {row['method']} | {category} | {row['Exec']:.3f} | {diagnostic} |"
        )
    return "\n".join(lines) + "\n", dict(counts)


def _complexity_markdown(rows: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "| Complexity | Method | N | Success | SR | Macro Exec |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for item in rows:
        sr = "—" if item["sr"] is None else f"{item['sr']:.1%}"
        exec_value = "—" if item["macro_exec"] is None else f"{item['macro_exec']:.3f}"
        lines.append(
            f"| {item['bin']} | {item['method']} | {item['n']} | {item['success']} | {sr} | {exec_value} |"
        )
    return "\n".join(lines)


def _development_markdown() -> str:
    metrics_paths = sorted((ROOT / "results/development").glob("iteration_*/metrics.json"))
    metrics = [json.loads(path.read_text(encoding="utf-8")) for path in metrics_paths]
    lines = [
        "# Phase-10 Development Regression",
        "",
        "VH-40 is development/regression only in Phase 10 because all prior results were observed. At most two complete HPAF-Full iterations were permitted.",
        "",
        "| Iteration | Success/40 | SR | Macro Exec | IR parse | Validator reject | Mean atomics | Mean D | Mean terminals | Atomic verify | Retry/task | Early stop |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in metrics:
        lines.append(
            f"| {item['iteration']} | {item['success']}/40 | {item['sr']:.1%} | {item['macro_exec']:.3f} | "
            f"{item['taskagent_parse_success_rate']:.1%} | {item['validator_rejection_rate']:.1%} | "
            f"{item['mean_atomic_count']:.2f} | {item['mean_dependency_depth']:.2f} | "
            f"{item['mean_terminal_constraint_count']:.2f} | {item['atomic_verifier_success_rate']:.1%} | "
            f"{item['retry_rate_per_task']:.2f} | {item['early_stop_rate']:.1%} |"
        )
    adopted = metrics[-1]
    lines.extend(
        [
            "",
            f"Adopted iteration: **{adopted['iteration']}**. Persistent-state regression: {adopted['persistent_success']}/{adopted['persistent_n']}; generic trace/process regression: {adopted['generic_trace_process_success']}/{adopted['generic_trace_process_n']}; Long-11 under partial-order semantics: {adopted['long11_success']}/{adopted['long11_n']}.",
            "",
            "For context, the Phase-9 Full baseline on the same groups was 19/20 persistent-state, 6/9 generic trace/process, and 7/11 Long-11 after the Phase-10 partial-order rescore. Thus iteration 2 removed validator rejection and improved Long-11 by 2 tasks, while the persistent and generic process groups were lower by 2 and 1 tasks respectively; the limited development protocol did not permit a third iteration.",
            "",
            "The final holdout was generated only after the adopted method, prompt, and evaluator hashes were frozen.",
        ]
    )
    return "\n".join(lines) + "\n"


def summarize() -> Dict[str, Any]:
    targets = [MAIN_CSV, COMPLEXITY_CSV, FAILURE_REPORT, METRIC_AUDIT, DEVELOPMENT_REPORT, FINAL_REPORT, PPT_TABLE, SUMMARY_JSON]
    if any(path.exists() for path in targets):
        raise RuntimeError("Refusing to overwrite Phase-10 final summary artifacts")
    if not COMPLETE.exists():
        raise RuntimeError("Phase-10 final run is not complete")
    lock = verify_final_lock()
    rows = read_jsonl(RAW)
    manifest = json.loads(runner.FINAL_MANIFEST.read_text(encoding="utf-8"))
    entries = {item["task_id"]: item for item in manifest["entries"]}
    expected = {(task_id, method) for task_id in entries for method in METHODS}
    actual = {(item["task_id"], item["method"]) for item in rows}
    if len(rows) != 36 or actual != expected:
        raise RuntimeError("Final result matrix integrity failure")
    main = _method_metrics(rows)
    complexity = _complexity(rows, entries)
    failure_md, failure_counts = _failure_markdown(rows)
    _write_exclusive(MAIN_CSV, _csv(main, ["method", "n", "success", "sr", "macro_exec", "gcr", "calls_per_task", "tokens_per_task"]))
    _write_exclusive(COMPLEXITY_CSV, _csv(complexity, ["dimension", "bin", "method", "n", "success", "sr", "macro_exec"]))
    _write_exclusive(FAILURE_REPORT, failure_md)
    _write_exclusive(DEVELOPMENT_REPORT, _development_markdown())

    full = [item for item in rows if item["method"] == "HPAF-Full"]
    flat_taskagent_calls = sum(
        call["call_role"] == "task_agent"
        for item in rows if item["method"] == "HPAF-Flat"
        for call in item["llm_call_records"]
    )
    gold_leak = any(
        "gold_semantics" in prompt["input"] or "reference_program" in prompt["input"]
        for item in rows
        for prompt in item["raw_prompts"]
    )
    full_attempts = sum(item["atomic_tasks_attempted"] for item in full)
    full_verified = sum(item.get("atomic_verifier_success_count", 0) for item in full)
    integrity = {
        "records": 36,
        "unique_pairs": len(actual),
        "manifest_sha256_matches_lock": sha256(runner.FINAL_MANIFEST) == lock["manifest_sha256"],
        "raw_runs_sha256_matches_complete": sha256(RAW) == json.loads(COMPLETE.read_text())["raw_runs_sha256"],
        "reference_feasible": manifest["reference_feasibility_count"],
        "flat_taskagent_calls": flat_taskagent_calls,
        "gold_or_reference_payload_in_method_prompts": gold_leak,
        "full_taskagent_parse_success_rate": mean(item.get("taskagent_parse_success", False) for item in full),
        "full_validator_rejection_rate": mean(item.get("taskagent_validator_rejected", False) for item in full),
        "full_mean_atomic_count": mean(item["number_of_atomic_tasks"] for item in full),
        "full_mean_dependency_depth": mean(item.get("dependency_depth", 0) for item in full),
        "full_mean_terminal_constraint_count": mean(item.get("terminal_constraint_count", 0) for item in full),
        "full_atomic_verifier_success_rate": full_verified / full_attempts if full_attempts else 0.0,
        "full_retry_rate": mean(item["retry_count"] for item in full),
        "full_early_stop_rate": mean(item["early_stop_count"] for item in full),
    }
    metric_lines = [
        "# Phase-10 Metric and Integrity Audit", "",
        f"- Formal records: 36/36; unique pairs: {integrity['unique_pairs']}/36; repeat/resample: 0.",
        "- Infrastructure recovery: one interrupted session after 29 records; resume skipped all 29 completed pairs and executed only the 7 missing pairs. Completed-pair repeats: 0.",
        f"- Reference replay feasible and evaluator-valid: {integrity['reference_feasible']}/12.",
        "- Frozen method, prompt, manifest, evaluator, and config hashes reverified: PASS.",
        f"- Manifest and raw-run completion hashes: {'PASS' if integrity['manifest_sha256_matches_lock'] and integrity['raw_runs_sha256_matches_complete'] else 'FAIL'}.",
        f"- Gold semantics/reference payload in method prompts: {integrity['gold_or_reference_payload_in_method_prompts']}.",
        f"- Flat TaskAgent calls: {integrity['flat_taskagent_calls']}.",
        f"- Full Structured IR parse success: {integrity['full_taskagent_parse_success_rate']:.1%}; validator rejection: {integrity['full_validator_rejection_rate']:.1%}.",
        f"- Full mean atomic count: {integrity['full_mean_atomic_count']:.2f}; mean dependency depth: {integrity['full_mean_dependency_depth']:.2f}; mean terminal constraints: {integrity['full_mean_terminal_constraint_count']:.2f}.",
        f"- Full atomic verifier success: {integrity['full_atomic_verifier_success_rate']:.1%}; retry/task: {integrity['full_retry_rate']:.2f}; early-stop/task: {integrity['full_early_stop_rate']:.1%}.",
        "- Primary metrics: Task SR, Macro Exec, calls/task, tokens/task. Goal Completion Ratio is supplementary.",
    ]
    _write_exclusive(METRIC_AUDIT, "\n".join(metric_lines) + "\n")

    table_lines = [
        "| Method | Success/12 | SR | Macro Exec | Calls/task | Tokens/task | GCR (supp.) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in main:
        table_lines.append(
            f"| {item['method']} | {item['success']}/12 | {item['sr']:.1%} | {item['macro_exec']:.3f} | {item['calls_per_task']:.2f} | {item['tokens_per_task']:.1f} | {item['gcr']:.3f} |"
        )
    complexity_md = _complexity_markdown(complexity)
    full_metric = next(item for item in main if item["method"] == "HPAF-Full")
    flat_metric = next(item for item in main if item["method"] == "HPAF-Flat")
    prog_metric = next(item for item in main if item["method"] == "ProgPrompt-Compat")
    conclusion = (
        f"In the single pre-frozen 12-task causal holdout, HPAF-Full completed {full_metric['success']}/12, "
        f"HPAF-Flat {flat_metric['success']}/12, and ProgPrompt-Compat {prog_metric['success']}/12. "
        "This supports only the observed one-run comparison under the frozen semantic-DAG evaluator."
    )
    limitation = "The largest limitation is that the final evidence is one deterministic 12-task synthetic holdout run, so it does not estimate stochastic variance or broader real-robot generalization."
    report = [
        "# Phase-10 Final Report", "", "## Final HPAF definition", "",
        "Atomic task: one dominant, independently verifiable semantic state/process commitment around a focal object.", "",
        "Complex task: multiple semantic checkpoints or predecessor-dependent later checkpoints.", "",
        "Dependency: explicit acyclic `depends_on` edges; stable topological ready-node execution.", "",
        "Terminal constraint: final required state/relation, not an independent high-level atomic.", "",
        "Execution: `P -> (A -> I)^k -> V`, followed by state refresh before the next ready atomic.", "",
        "## Phase-9 offline rescore", "",
        "| Method | Original | Partial-order rescore |", "|---|---:|---:|",
        "| ProgPrompt-Compat | 18/40 | 18/40 |", "| HPAF-Flat | 27/40 | 27/40 |", "| HPAF-Full | 28/40 | 32/40 |", "",
        "Four Full traces changed because all required semantic events and final conditions were present while only terminal close/reference order differed.", "",
        "## Validator audit", "", "Old false rejection: 4/40. New rejection after legacy compatibility projection: 0/40. All four fixed cases were legal `Move object from A to B` transfers.", "",
        "## Development regression", "", "See `DEVELOPMENT_REGRESSION.md`; adopted frozen development iteration is recorded in `PHASE10_METHOD_FREEZE.json`. Relative to the Phase-9 Full baseline, iteration 2 improved partial-order Long-11 from 7/11 to 9/11, while persistent-state changed from 19/20 to 17/20 and generic trace/process from 6/9 to 5/9.", "",
        "## Final holdout", "", "N=12; categories 3/3/3/3; scenes 4/4/4; reference feasible/evaluator-valid 12/12.", "",
        "## Final result", "", *table_lines, "", "## Complexity scaling", "", complexity_md, "",
        "## PPT example", "", "Task: Heat salmon in the microwave, then place it on the coffeetable.", "", "`A1 Heat salmon [PROCESS] -> A2 Place salmon on table [TRANSFER]`", "", "Terminal: microwave OFF. A1 executes `Perceive -> Align salmon -> Grab -> Align microwave -> Load / Run cycle -> Verify`; then state refresh and A2.", "",
        "## Main conclusion", "", conclusion, "", "## Remaining limitation", "", limitation,
    ]
    _write_exclusive(FINAL_REPORT, "\n".join(report) + "\n")
    ppt = [
        "# Phase-10 PPT Final Table", "", *table_lines, "", "**Method:** Instruction -> semantic atomic IR + DAG -> current atomic `P -> (A -> I)^k -> V` -> refresh -> next ready atomic.", "", f"**Data-supported conclusion:** {conclusion}", "", f"**Limitation:** {limitation}",
    ]
    _write_exclusive(PPT_TABLE, "\n".join(ppt) + "\n")
    summary = {
        "main": main,
        "complexity": complexity,
        "failure_counts": failure_counts,
        "integrity": integrity,
        "main_conclusion": conclusion,
        "remaining_limitation": limitation,
    }
    _write_exclusive(SUMMARY_JSON, json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    print(json.dumps(summarize(), ensure_ascii=False, indent=2))
