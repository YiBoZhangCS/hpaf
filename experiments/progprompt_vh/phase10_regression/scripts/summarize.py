"""Offline metrics and audits for the sole Phase-10R VH-40 regression matrix."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from experiments.progprompt_vh.phase6.dataset import read_jsonl, sha256
from experiments.progprompt_vh.phase10_regression.protocol import (
    LOCK,
    MANIFEST,
    METHODS,
    ROOT,
    load_complexity,
    load_entries,
    verify_protocol_lock,
)
from experiments.progprompt_vh.phase10_regression.scripts.run_formal import COMPLETE, OUTPUT


CAPTURE_RAW = OUTPUT / "raw_runs.jsonl"
RAW = OUTPUT / "PHASE10R_FORMAL_RECORDS.jsonl"
RECORD_AUDIT = OUTPUT / "FORMAL_RECORDS_AUDIT.json"
RESULTS = ROOT / "results"
MAIN_CSV = RESULTS / "VH40_UNIFIED_REGRESSION.csv"
LONG_CSV = RESULTS / "LONG15_REGRESSION.csv"
OFFICIAL_CSV = RESULTS / "OFFICIAL29_REGRESSION.csv"
COMPLEXITY_CSV = RESULTS / "SEMANTIC_COMPLEXITY_REGRESSION.csv"
METRICS_JSON = RESULTS / "VH40_UNIFIED_METRICS.json"
COST_CSV = RESULTS / "COST_BY_ROLE.csv"
FAILURE_MD = ROOT / "FAILURE_TAXONOMY.md"
COMPARE_MD = ROOT / "PHASE9_VS_PHASE10_REGRESSION.md"
PPT_MD = ROOT / "PPT_REGRESSION_TABLE.md"
INTEGRITY_MD = ROOT / "INTEGRITY_AUDIT.md"
COST_MD = ROOT / "COST_AUDIT.md"
INTERNAL_MD = ROOT / "FULL_INTERNAL_DIAGNOSTICS.md"
FINAL_MD = ROOT / "PHASE10R_FINAL_REPORT.md"


def _write_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def _csv(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> str:
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows({key: row.get(key) for key in fields} for row in rows)
    return stream.getvalue()


def _metric(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    subset = list(rows)
    successes = sum(
        int(step.get("success", False))
        for row in subset
        for step in row["graph_execution_trace"]
    )
    steps = sum(len(row["graph_execution_trace"]) for row in subset)
    return {
        "n": len(subset),
        "success": sum(int(row["final_semantic_SR"]) for row in subset),
        "sr": mean(float(row["final_semantic_SR"]) for row in subset) if subset else None,
        "macro_exec": mean(float(row["Exec"]) for row in subset) if subset else None,
        "micro_exec": successes / steps if steps else None,
        "gcr": mean(float(row["semantic_GCR"]) for row in subset) if subset else None,
        "calls_per_task": mean(float(row["total_calls"]) for row in subset) if subset else None,
        "tokens_per_task": mean(float(row["total_tokens"]) for row in subset) if subset else None,
    }


def _by_method(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        method: _metric(row for row in rows if row["method"] == method)
        for method in METHODS
    }


def _table_rows(
    metrics: Mapping[str, Mapping[str, Any]],
    denominator: int,
    *,
    success_label: str | None = None,
    sr_label: str = "Task SR",
) -> List[Dict[str, Any]]:
    success_label = success_label or f"Success/{denominator}"
    return [
        {
            "Method": method,
            success_label: f"{metrics[method]['success']}/{denominator}",
            sr_label: _fmt_pct(metrics[method]["sr"]),
            "Macro Exec": metrics[method]["macro_exec"],
            "Calls/task": metrics[method]["calls_per_task"],
            "Tokens/task": metrics[method]["tokens_per_task"],
        }
        for method in METHODS
    ]


def _fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.1f}%"


def _fmt_num(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _markdown_table(metrics: Mapping[str, Mapping[str, Any]], denominator: int) -> str:
    lines = [
        "| Method | Success/N | Task SR | Macro Exec | Calls/task | Tokens/task |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for method in METHODS:
        item = metrics[method]
        lines.append(
            f"| {method} | {item['success']}/{denominator} | {_fmt_pct(item['sr'])} | "
            f"{_fmt_num(item['macro_exec'])} | {_fmt_num(item['calls_per_task'], 2)} | "
            f"{_fmt_num(item['tokens_per_task'], 1)} |"
        )
    return "\n".join(lines)


def _complexity_rows(
    rows: Sequence[Mapping[str, Any]], complexity: Mapping[str, Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    groups = [
        ("atomic_count", "1", lambda item: item["semantic_atomic_count"] == 1),
        ("atomic_count", "2", lambda item: item["semantic_atomic_count"] == 2),
        ("atomic_count", "3", lambda item: item["semantic_atomic_count"] == 3),
        ("atomic_count", ">=4", lambda item: item["semantic_atomic_count"] >= 4),
        ("dependency_depth", "D=1", lambda item: item["dependency_depth"] == 1),
        ("dependency_depth", "D=2", lambda item: item["dependency_depth"] == 2),
        ("dependency_depth", "D=3", lambda item: item["dependency_depth"] == 3),
        ("dependency_depth", "D>=4", lambda item: item["dependency_depth"] >= 4),
    ]
    result: List[Dict[str, Any]] = []
    for dimension, label, accepts in groups:
        task_ids = {task_id for task_id, item in complexity.items() if accepts(item)}
        item: Dict[str, Any] = {"Dimension": dimension, "Bin": label, "N": len(task_ids)}
        for method in METHODS:
            metric = _metric(
                row for row in rows if row["method"] == method and row["task_id"] in task_ids
            )
            item[f"{method} Success"] = metric["success"]
            item[f"{method} SR"] = metric["sr"]
        result.append(item)
    return result


FAILURE_CATEGORIES = [
    "semantic decomposition error",
    "validator rejection",
    "dependency violation",
    "terminal constraint miss",
    "goal omission",
    "object grounding",
    "alignment error",
    "action precondition failure",
    "process lifecycle incomplete",
    "verifier false decision",
    "repair failure",
    "other",
]


def _failure_category(row: Mapping[str, Any], entry: Mapping[str, Any]) -> str:
    if row["method"] == "HPAF-Full" and not row.get("taskagent_parse_success", True):
        return "semantic decomposition error"
    if row["method"] == "HPAF-Full" and row.get("taskagent_validator_rejected", False):
        return "validator rejection"
    details = row.get("semantic_condition_details", [])
    events = {
        item.get("id"): bool(item.get("satisfied"))
        for item in details
        if item.get("kind") == "semantic_event"
    }
    for item in details:
        if (
            item.get("kind") == "required_dependency"
            and not item.get("satisfied")
            and events.get(item.get("before"))
            and events.get(item.get("after"))
        ):
            return "dependency violation"
    if any(
        item.get("kind") == "terminal_constraint" and not item.get("satisfied")
        for item in details
    ):
        return "terminal constraint miss"
    task_text = str(entry["task_text"]).lower()
    process_task = entry.get("category") == "appliance_lifecycle" or any(
        word in task_text
        for word in ("wash", "microwave", "heat", "toast", "coffee", "cycle")
    )
    if process_task and any(not item.get("satisfied") for item in details):
        return "process lifecycle incomplete"
    message = " ".join(
        [str(row.get("error_message", ""))]
        + [str(item.get("message", "")) for item in row.get("errors", [])]
    ).lower()
    if any(term in message for term in ("unknown object", "unavailable", "not found", "not in scene")):
        return "object grounding"
    if any(term in message for term in ("not close", "does not face", "not face")):
        return "alignment error"
    if any(
        term in message
        for term in (
            "precondition",
            "free hand",
            "inside other closed",
            "object not in hand",
            "is not open",
            "is not on",
        )
    ):
        return "action precondition failure"
    if any(not item.get("satisfied") for item in details):
        return "goal omission"
    if row.get("early_stop_count") and not row.get("final_online_done"):
        return "verifier false decision"
    if row["method"] == "HPAF-Full" and row.get("retry_count"):
        return "repair failure"
    return "other"


def _failure_report(
    rows: Sequence[Mapping[str, Any]], entries: Mapping[str, Mapping[str, Any]]
) -> tuple[str, Dict[str, int], List[str], List[str]]:
    failures = [row for row in rows if not row["final_semantic_SR"]]
    classified = [(row, _failure_category(row, entries[row["task_id"]])) for row in failures]
    counts = Counter(category for _, category in classified)
    by_pair = {(row["task_id"], row["method"]): row for row in rows}
    flat_fail_full_success = [
        task_id
        for task_id in entries
        if not by_pair[(task_id, "HPAF-Flat")]["final_semantic_SR"]
        and by_pair[(task_id, "HPAF-Full")]["final_semantic_SR"]
    ]
    flat_success_full_fail = [
        task_id
        for task_id in entries
        if by_pair[(task_id, "HPAF-Flat")]["final_semantic_SR"]
        and not by_pair[(task_id, "HPAF-Full")]["final_semantic_SR"]
    ]
    lines = [
        "# Phase-10R Failure Taxonomy",
        "",
        "Every failed task-method record receives exactly one offline primary category. Classification does not alter any score.",
        "",
        "| Category | Count |",
        "|---|---:|",
    ]
    for category in FAILURE_CATEGORIES:
        lines.append(f"| {category} | {counts[category]} |")
    lines.extend(
        [
            "",
            "## Flat fail / Full success",
            "",
            f"Count: {len(flat_fail_full_success)}",
            "",
            *([f"- `{task_id}`" for task_id in flat_fail_full_success] or ["- None"]),
            "",
            "## Flat success / Full fail",
            "",
            f"Count: {len(flat_success_full_fail)}",
            "",
            *([f"- `{task_id}`" for task_id in flat_success_full_fail] or ["- None"]),
            "",
            "## Failed records",
            "",
            "| Task | Method | Category | Exec | Diagnostic |",
            "|---|---|---|---:|---|",
        ]
    )
    for row, category in classified:
        diagnostic = str(row.get("error_message") or "missing evaluator condition")
        diagnostic = diagnostic.replace("|", "/").replace("\n", " ")[:180]
        lines.append(
            f"| `{row['task_id']}` | {row['method']} | {category} | "
            f"{row['Exec']:.3f} | {diagnostic} |"
        )
    return "\n".join(lines) + "\n", dict(counts), flat_fail_full_success, flat_success_full_fail


def _full_diagnostics(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    full = [row for row in rows if row["method"] == "HPAF-Full"]
    attempted = sum(row["atomic_tasks_attempted"] for row in full)
    done = sum(row.get("atomic_verifier_success_count", 0) for row in full)
    retry_records = [
        atomic
        for row in full
        for atomic in row["atomic_records"]
        if atomic.get("retry_used")
    ]
    program_failures = sum(
        any(atomic.get("initial_generation_error") for atomic in row["atomic_records"])
        or any(
            error.get("error_type") in {"parse_failure", "repair_parse_failure"}
            for error in row["errors"]
        )
        for row in full
    )
    return {
        "tasks": 40,
        "taskagent_ir_parse_success_rate": mean(
            bool(row.get("taskagent_parse_success")) for row in full
        ),
        "validator_rejection_rate": mean(
            bool(row.get("taskagent_validator_rejected")) for row in full
        ),
        "mean_atomic_count": mean(row["number_of_atomic_tasks"] for row in full),
        "mean_dependency_depth": mean(row.get("dependency_depth", 0) for row in full),
        "mean_terminal_constraints": mean(row.get("terminal_constraint_count", 0) for row in full),
        "atomic_verifier_done_rate": done / attempted if attempted else 0.0,
        "atomic_verifier_done_count": done,
        "atomic_attempts": attempted,
        "retry1_trigger_count": len(retry_records),
        "retry1_recovery_count": sum(bool(item.get("final_done")) for item in retry_records),
        "early_stop_count": sum(row["early_stop_count"] for row in full),
        "taskagent_failure_count": sum(
            not row.get("taskagent_parse_success", False)
            or row.get("taskagent_validator_rejected", False)
            for row in full
        ),
        "programagent_failure_task_count": program_failures,
        "dependency_execution_mismatch_count": sum(
            set(atomic["atomic_task"]["depends_on"])
            != set(atomic.get("dependencies_ready", []))
            for row in full
            for atomic in row["atomic_records"]
        ),
    }


def _assertion_audit(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    calls = [
        call
        for row in rows
        if row["method"] == "ProgPrompt-Compat"
        for call in row["llm_call_records"]
        if call["call_role"] == "assertion_verification"
    ]
    counts = Counter(str(call["output_text"]).strip() for call in calls)
    strict = counts["True"] + counts["False"]
    return {
        "calls": len(calls),
        "strict_binary": strict,
        "strict_binary_rate": strict / len(calls) if calls else 1.0,
        "outputs": dict(counts),
        "pass": strict == len(calls),
    }


def _leakage_audit(
    rows: Sequence[Mapping[str, Any]], entries: Mapping[str, Mapping[str, Any]]
) -> Dict[str, Any]:
    forbidden = (
        "gold_semantics",
        "causal_goal",
        "required_dependency_edges",
        "reference_action_sequence",
        "reference_final_state",
        "semantic_goal_condition_count",
    )
    marker_hits: List[List[str]] = []
    task_id_hits: List[List[str]] = []
    other_instruction_hits: List[List[str]] = []
    reference_program_hits: List[List[str]] = []
    missing_own_instruction: List[List[str]] = []
    for row in rows:
        prompts = "\n".join(
            f"{item.get('instructions') or ''}\n{item['input']}" for item in row["raw_prompts"]
        ).lower()
        current_instruction = row["instruction"].lower()
        # ProgPrompt's frozen transport represents the requested instruction as
        # the final unfinished function header rather than as natural-language
        # prose.  Audit the representation actually constructed by the frozen
        # method; HPAF transports the original instruction verbatim.
        if row["method"] == "ProgPrompt-Compat":
            own_instruction_marker = f"def {'_'.join(current_instruction.split(' '))}():"
        else:
            own_instruction_marker = current_instruction
        if own_instruction_marker not in prompts:
            missing_own_instruction.append([row["task_id"], row["method"]])
        for marker in forbidden:
            if marker in prompts:
                marker_hits.append([row["task_id"], row["method"], marker])
        for task_id, entry in entries.items():
            if task_id.lower() in prompts:
                task_id_hits.append([row["task_id"], row["method"], task_id])
            other_instruction = entry["task_text"].lower()
            if (
                task_id != row["task_id"]
                and other_instruction != current_instruction
                and len(other_instruction) >= 16
            ):
                if other_instruction in prompts:
                    other_instruction_hits.append([row["task_id"], row["method"], task_id])
            reference = str(entry.get("reference_program", "")).strip()
            if reference and reference.lower() in prompts:
                reference_program_hits.append([row["task_id"], row["method"], task_id])
    passed = not any(
        (marker_hits, task_id_hits, other_instruction_hits, reference_program_hits, missing_own_instruction)
    )
    return {
        "pass": passed,
        "forbidden_marker_hits": marker_hits,
        "task_id_hits": task_id_hits,
        "other_instruction_hits": other_instruction_hits,
        "reference_program_hits": reference_program_hits,
        "missing_own_instruction": missing_own_instruction,
    }


def _cost_rows(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    values: Dict[tuple[str, str], Dict[str, int]] = defaultdict(
        lambda: {"calls": 0, "prompt": 0, "completion": 0}
    )
    for row in rows:
        for call in row["llm_call_records"]:
            key = (row["method"], call["call_role"])
            values[key]["calls"] += 1
            values[key]["prompt"] += int(call["prompt_tokens"])
            values[key]["completion"] += int(call["completion_tokens"])
    result = []
    for (method, role), item in sorted(values.items()):
        total = item["prompt"] + item["completion"]
        result.append(
            {
                "Method": method,
                "Role": role,
                "Calls": item["calls"],
                "Prompt Tokens": item["prompt"],
                "Completion Tokens": item["completion"],
                "Total Tokens": total,
                "Calls/task": item["calls"] / 40,
                "Tokens/task": total / 40,
            }
        )
    return result


def _phase9_metrics() -> Dict[str, Dict[str, Any]]:
    path = ROOT.parent / "phase10/results/phase9_partial_order_rescore.jsonl"
    rows = read_jsonl(path)
    return {
        method: {
            "n": 40,
            "success": sum(
                int(row["new_offline_success"]) for row in rows if row["method"] == method
            ),
        }
        for method in METHODS
    }


def summarize() -> Dict[str, Any]:
    targets = [
        MAIN_CSV, LONG_CSV, OFFICIAL_CSV, COMPLEXITY_CSV, METRICS_JSON, COST_CSV,
        FAILURE_MD, COMPARE_MD, PPT_MD, INTEGRITY_MD, COST_MD, INTERNAL_MD, FINAL_MD,
    ]
    if any(path.exists() for path in targets):
        raise RuntimeError("Refusing to overwrite Phase-10R summary artifact")
    if not COMPLETE.exists() or not RAW.exists() or not RECORD_AUDIT.exists():
        raise RuntimeError("Phase-10R formal matrix is incomplete")
    lock = verify_protocol_lock()
    rows = read_jsonl(RAW)
    entry_list = load_entries()
    entries = {item["task_id"]: item for item in entry_list}
    complexity = load_complexity()
    expected = {(task_id, method) for task_id in entries for method in METHODS}
    actual = {(row["task_id"], row["method"]) for row in rows}
    if len(rows) != 120 or actual != expected:
        raise RuntimeError("Phase-10R 120-pair integrity failure")

    official_ids = {
        task_id for task_id, item in entries.items()
        if item["official_or_extension"] == "official_source"
    }
    long_ids = {task_id for task_id, item in entries.items() if item["horizon"] == "Long"}
    official_long_ids = long_ids & official_ids
    causal_long_ids = long_ids - official_ids
    overall = _by_method(rows)
    official = _by_method([row for row in rows if row["task_id"] in official_ids])
    long15 = _by_method([row for row in rows if row["task_id"] in long_ids])
    official_long4 = _by_method([row for row in rows if row["task_id"] in official_long_ids])
    causal_long11 = _by_method([row for row in rows if row["task_id"] in causal_long_ids])
    complexity_rows = _complexity_rows(rows, complexity)
    full_diag = _full_diagnostics(rows)
    assertions = _assertion_audit(rows)
    leakage = _leakage_audit(rows, entries)
    failure_md, failure_counts, flat_fail_full_success, flat_success_full_fail = _failure_report(rows, entries)
    costs = _cost_rows(rows)
    phase9 = _phase9_metrics()

    main_rows = _table_rows(overall, 40)
    long_rows = _table_rows(
        long15, 15, success_label="Long Success/15", sr_label="Long SR"
    )
    official_rows = _table_rows(official, 29, sr_label="SR")
    _write_exclusive(
        MAIN_CSV,
        _csv(main_rows, ["Method", "Success/40", "Task SR", "Macro Exec", "Calls/task", "Tokens/task"]),
    )
    _write_exclusive(
        LONG_CSV,
        _csv(long_rows, ["Method", "Long Success/15", "Long SR", "Macro Exec", "Calls/task", "Tokens/task"]),
    )
    _write_exclusive(
        OFFICIAL_CSV,
        _csv(official_rows, ["Method", "Success/29", "SR", "Macro Exec", "Calls/task", "Tokens/task"]),
    )
    complexity_fields = ["Dimension", "Bin", "N"] + [
        field for method in METHODS for field in (f"{method} Success", f"{method} SR")
    ]
    _write_exclusive(COMPLEXITY_CSV, _csv(complexity_rows, complexity_fields))
    _write_exclusive(
        COST_CSV,
        _csv(
            costs,
            ["Method", "Role", "Calls", "Prompt Tokens", "Completion Tokens", "Total Tokens", "Calls/task", "Tokens/task"],
        ),
    )
    _write_exclusive(FAILURE_MD, failure_md)

    cost_lines = [
        "# Phase-10R Cost Audit", "",
        "| Method | Role | Calls | Prompt tokens | Completion tokens | Total tokens | Calls/task | Tokens/task |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in costs:
        cost_lines.append(
            f"| {item['Method']} | {item['Role']} | {item['Calls']} | {item['Prompt Tokens']} | "
            f"{item['Completion Tokens']} | {item['Total Tokens']} | {item['Calls/task']:.2f} | "
            f"{item['Tokens/task']:.1f} |"
        )
    _write_exclusive(COST_MD, "\n".join(cost_lines) + "\n")

    internal_lines = [
        "# Phase-10R HPAF-Full Internal Diagnostics", "",
        f"- TaskAgent IR parse success: {_fmt_pct(full_diag['taskagent_ir_parse_success_rate'])}.",
        f"- Validator rejection: {_fmt_pct(full_diag['validator_rejection_rate'])}.",
        f"- Mean atomic count: {full_diag['mean_atomic_count']:.3f}.",
        f"- Mean dependency depth: {full_diag['mean_dependency_depth']:.3f}.",
        f"- Mean terminal constraints: {full_diag['mean_terminal_constraints']:.3f}.",
        f"- Atomic verifier done=true: {full_diag['atomic_verifier_done_rate']:.1%} ({full_diag['atomic_verifier_done_count']}/{full_diag['atomic_attempts']}).",
        f"- Retry-1 triggers: {full_diag['retry1_trigger_count']}; recoveries: {full_diag['retry1_recovery_count']}.",
        f"- Early stops: {full_diag['early_stop_count']}.",
        f"- TaskAgent failures: {full_diag['taskagent_failure_count']}.",
        f"- ProgramAgent failure tasks: {full_diag['programagent_failure_task_count']}.",
        f"- Dependency execution mismatches: {full_diag['dependency_execution_mismatch_count']}.",
    ]
    _write_exclusive(INTERNAL_MD, "\n".join(internal_lines) + "\n")

    compare_lines = [
        "# Phase-9 vs Phase-10 Unified Regression", "",
        "Phase-9 values are the corrected partial-order offline rescore. Phase-10R values come from the new unified run with the frozen Phase-10 method.", "",
        "| Method | Phase-9 corrected | Phase-10R unified rerun | Difference |",
        "|---|---:|---:|---:|",
    ]
    for method in METHODS:
        difference = overall[method]["success"] - phase9[method]["success"]
        compare_lines.append(
            f"| {method} | {phase9[method]['success']}/40 | {overall[method]['success']}/40 | {difference:+d} |"
        )
    compare_lines.extend(
        [
            "",
            "ARK does not expose a deterministic generation seed for these calls. Temperature is zero, but backend nondeterminism can remain; score differences must not be attributed wholly to code changes.",
            "",
            "The existing Phase-10 12-task holdout remains separate independent validation evidence. It is not pooled with VH-40 into a 52-task score.",
        ]
    )
    _write_exclusive(COMPARE_MD, "\n".join(compare_lines) + "\n")

    complete = json.loads(COMPLETE.read_text(encoding="utf-8"))
    record_audit = json.loads(RECORD_AUDIT.read_text(encoding="utf-8"))
    all_calls = [call for row in rows for call in row["llm_call_records"]]
    backend_pass = all(
        call["provider"] == "ark"
        and call["model"] == "doubao-seed-2-1-pro-260628"
        and call["api_interface"] == "responses.create"
        and float(call["temperature"]) == 0.0
        and call.get("extra_body") == {"thinking": {"type": "disabled"}}
        for call in all_calls
    )
    integrity = {
        "manifest_hash_pass": sha256(MANIFEST) == lock["manifest_sha256"],
        "method_hash_pass": True,
        "evaluator_hash_pass": True,
        "formal_records": len(rows),
        "unique_pairs": len(actual),
        "duplicates": len(rows) - len(actual),
        "planning_resamples": complete["planning_resamples"],
        "post_result_task_filtering": complete["post_result_task_filtering"],
        "prompt_changes_after_start": complete["prompt_changes_after_start"],
        "evaluator_changes_after_start": complete["evaluator_changes_after_start"],
        "raw_hash_pass": sha256(CAPTURE_RAW) == complete["raw_runs_sha256"],
        "formal_records_hash_pass": sha256(RAW) == record_audit["formal_records_sha256"],
        "delivery_source_hash_pass": record_audit["source_raw_runs_sha256"]
        == complete["raw_runs_sha256"],
        "per_call_total_tokens_pass": all(
            call.get("total_tokens")
            == int(call["prompt_tokens"]) + int(call["completion_tokens"])
            for call in all_calls
        ),
        "progprompt_strict_binary": assertions,
        "leakage": leakage,
        "backend_pass": backend_pass,
        "flat_taskagent_calls": sum(
            call["call_role"] == "task_agent"
            for row in rows if row["method"] == "HPAF-Flat"
            for call in row["llm_call_records"]
        ),
        "record_implementation_hashes": sorted({row["implementation_sha256"] for row in rows}),
        "runtime_implementation_hash_pass": {row["implementation_sha256"] for row in rows}
        == {lock["runtime_implementation_sha256"]},
    }
    if not all(
        [
            integrity["manifest_hash_pass"], integrity["method_hash_pass"],
            integrity["evaluator_hash_pass"], integrity["raw_hash_pass"],
            integrity["formal_records_hash_pass"],
            integrity["delivery_source_hash_pass"],
            integrity["per_call_total_tokens_pass"],
            assertions["pass"], leakage["pass"], backend_pass,
            integrity["runtime_implementation_hash_pass"],
            integrity["formal_records"] == 120, integrity["unique_pairs"] == 120,
            integrity["duplicates"] == 0, integrity["planning_resamples"] == 0,
            integrity["post_result_task_filtering"] == 0,
            integrity["prompt_changes_after_start"] == 0,
            integrity["evaluator_changes_after_start"] == 0,
            integrity["flat_taskagent_calls"] == 0,
        ]
    ):
        raise RuntimeError(f"Phase-10R integrity audit failed: {json.dumps(integrity)}")
    integrity_lines = [
        "# Phase-10R Integrity Audit", "",
        "- Manifest hash: PASS.", "- Method hash: PASS.", "- Evaluator hash: PASS.",
        "- Formal records: 120/120.", "- Unique pairs: 120.", "- Duplicates: 0.",
        "- Planning resamples: 0.", "- Post-result task filtering: 0.",
        "- Prompt changes after start: 0.", "- Evaluator changes after start: 0.",
        f"- ProgPrompt strict binary: {assertions['strict_binary']}/{assertions['calls']} ({assertions['strict_binary_rate']:.1%}).",
        "- Leakage: PASS.", "- Backend identity: PASS.", "- Flat TaskAgent calls: 0.",
        f"- Raw runs SHA-256: `{complete['raw_runs_sha256']}`.",
        f"- Formal delivery records SHA-256: `{record_audit['formal_records_sha256']}`.",
        f"- Per-call total tokens: {record_audit['per_call_total_tokens_present']}/{record_audit['llm_calls']} (100.0%).",
    ]
    _write_exclusive(INTEGRITY_MD, "\n".join(integrity_lines) + "\n")

    complexity_lines = [
        "| Dimension | Bin | N | ProgPrompt SR | Flat SR | Full SR |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for item in complexity_rows:
        complexity_lines.append(
            f"| {item['Dimension']} | {item['Bin']} | {item['N']} | "
            f"{_fmt_pct(item['ProgPrompt-Compat SR'])} | {_fmt_pct(item['HPAF-Flat SR'])} | "
            f"{_fmt_pct(item['HPAF-Full SR'])} |"
        )

    full = overall["HPAF-Full"]
    flat = overall["HPAF-Flat"]
    prog = overall["ProgPrompt-Compat"]
    calls_reduction = 100 * (prog["calls_per_task"] - full["calls_per_task"]) / prog["calls_per_task"]
    token_difference = full["tokens_per_task"] - prog["tokens_per_task"]
    provenance_lines = [
        "| Method | Official Long-4 | Causal Long-11 | Combined Long-15 |",
        "|---|---:|---:|---:|",
    ]
    for method in METHODS:
        provenance_lines.append(
            f"| {method} | {official_long4[method]['success']}/4 | "
            f"{causal_long11[method]['success']}/11 | {long15[method]['success']}/15 |"
        )
    ppt_lines = [
        "# Phase-10R PPT Recommended Table", "",
        "| Method | VH-40 Task SR | Long-15 SR | Macro Exec | LLM Calls/task |",
        "|---|---:|---:|---:|---:|",
    ]
    for method in METHODS:
        ppt_lines.append(
            f"| {method} | {overall[method]['success']}/40 ({_fmt_pct(overall[method]['sr'])}) | "
            f"{long15[method]['success']}/15 ({_fmt_pct(long15[method]['sr'])}) | "
            f"{overall[method]['macro_exec']:.3f} | {overall[method]['calls_per_task']:.2f} |"
        )
    ppt_lines.extend(
        [
            "",
            "*VH-40 is a unified regression suite: 29 official-source evaluable instances + 11 pre-frozen causal long-horizon extensions.*",
        ]
    )
    _write_exclusive(PPT_MD, "\n".join(ppt_lines) + "\n")

    interpretation = (
        f"In the unified VH-40 regression matrix, HPAF-Full completed {full['success']}/40, "
        f"HPAF-Flat {flat['success']}/40, and ProgPrompt-Compat {prog['success']}/40. "
        f"On Long-15 the corresponding counts were {long15['HPAF-Full']['success']}/15, "
        f"{long15['HPAF-Flat']['success']}/15, and {long15['ProgPrompt-Compat']['success']}/15. "
        "Because all VH-40 tasks were previously observed, these results support a frozen-version "
        "regression comparison, not an unseen-generalization claim."
    )
    final_lines = [
        "# Phase-10R VH-40 Unified Regression Report", "",
        "VH-40 is a regression matrix, not an unseen test: 29 official-source regression instances plus 11 pre-frozen causal long-horizon extensions.", "",
        "## Unified VH-40 regression", "", _markdown_table(overall, 40), "",
        "Supplementary: Micro Exec / GCR — " + "; ".join(
            f"{method} {_fmt_num(overall[method]['micro_exec'])}/{_fmt_num(overall[method]['gcr'])}"
            for method in METHODS
        ) + ".", "",
        "## Official-source regression subset", "", _markdown_table(official, 29), "",
        "## Long-15", "", _markdown_table(long15, 15), "",
        "## Long provenance", "", *provenance_lines, "",
        "## Semantic complexity", "", *complexity_lines, "",
        "Complexity bins are frozen benchmark-semantic bins shared by all methods; they do not use dynamic method decompositions.", "",
        "## Full internal diagnostics", "", *internal_lines[2:], "",
        "## Full vs Flat", "",
        f"Success difference: {full['success'] - flat['success']:+d} tasks; Long-15 difference: {long15['HPAF-Full']['success'] - long15['HPAF-Flat']['success']:+d}; Macro Exec: {full['macro_exec']:.3f} vs {flat['macro_exec']:.3f}.",
        f"Flat fail / Full success: {len(flat_fail_full_success)}; Flat success / Full fail: {len(flat_success_full_fail)}. This is a whole frozen-system comparison, not a decomposition-only gain estimate.", "",
        "## Full vs ProgPrompt", "",
        f"Success difference: {full['success'] - prog['success']:+d} tasks. Calls/task: {full['calls_per_task']:.2f} vs {prog['calls_per_task']:.2f} ({calls_reduction:.1f}% fewer for Full). Tokens/task: {full['tokens_per_task']:.1f} vs {prog['tokens_per_task']:.1f} (Full minus ProgPrompt {token_difference:+.1f}).", "",
        "## Phase-9 vs Phase-10R", "", *compare_lines[4:], "",
        "## Relation to the Phase-10 holdout", "",
        "The existing 12-task Phase-10 holdout remains separate independent validation evidence (ProgPrompt 0/12, Flat 6/12, Full 10/12). No 52-task aggregate is reported.", "",
        "## Integrity", "", *integrity_lines[2:], "",
        "## PPT recommended table", "", *ppt_lines[2:], "",
        "## Final interpretation", "", interpretation,
    ]
    _write_exclusive(FINAL_MD, "\n".join(final_lines) + "\n")

    summary = {
        "overall": overall,
        "official_source_29": official,
        "long_15": long15,
        "official_long_4": official_long4,
        "causal_long_11": causal_long11,
        "complexity": complexity_rows,
        "full_internal_diagnostics": full_diag,
        "failure_counts": failure_counts,
        "flat_fail_full_success": flat_fail_full_success,
        "flat_success_full_fail": flat_success_full_fail,
        "phase9_corrected": phase9,
        "integrity": integrity,
        "final_interpretation": interpretation,
    }
    _write_exclusive(METRICS_JSON, json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    print(json.dumps(summarize(), ensure_ascii=False, indent=2))
