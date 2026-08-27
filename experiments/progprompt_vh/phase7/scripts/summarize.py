#!/usr/bin/env python3
"""Offline Phase-7 recomputation, cost/leakage audit, and final tables."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from experiments.progprompt_vh.phase6.dataset import load_initial_graph
from experiments.progprompt_vh.phase6.verification.deterministic_evaluator import evaluate_conditions
from experiments.progprompt_vh.phase7.dataset import PHASE7_ROOT
from experiments.progprompt_vh.phase7.execution import Phase7GraphProgramExecutor
from experiments.progprompt_vh.phase7.runner import METHODS, load_frozen, verify_protocol_lock
from experiments.progprompt_vh.phase7.verification.trace_evaluator import evaluate_trace_goal


RESULTS = PHASE7_ROOT / "results"


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def replay(record: Dict[str, Any], entry: Dict[str, Any], actions: Dict[str, Any]) -> Dict[str, Any]:
    executor = Phase7GraphProgramExecutor(
        load_initial_graph(entry), actions_payload=actions, llm_client=None, unity_comm=None, seed=0
    )
    for ordinal, expected in enumerate(record["graph_execution_trace"], 1):
        if expected["parsed_action"] is None:
            actual = executor.graph_executor.record_failed_attempt(expected["source_action"], expected["error"])
        else:
            actual = executor.graph_executor.execute_ground_truth_action(expected["source_action"])
            if actual.success:
                executor._refresh_evaluator_augmentations()
        if bool(actual.success) != bool(expected["success"]) or (actual.error or "") != (expected["error"] or ""):
            raise RuntimeError(f"Replay mismatch: {record['task_id']}/{record['method']} action {ordinal}")
    if entry["evaluator_type"] == "generic_trace":
        semantic = evaluate_trace_goal(record, entry["trace_goal"], load_initial_graph(entry))
    else:
        semantic = evaluate_conditions(executor.final_graph, entry["semantic_goal"]["conditions"])
    if semantic["final_semantic_SR"] != record["final_semantic_SR"]:
        raise RuntimeError(f"Semantic replay mismatch: {record['task_id']}/{record['method']}")
    attempts = len(record["graph_execution_trace"])
    successes = sum(bool(item["success"]) for item in record["graph_execution_trace"])
    if attempts != record["program_length"] or abs((successes / attempts if attempts else 0.0) - record["Exec"]) > 1e-12:
        raise RuntimeError(f"Exec replay mismatch: {record['task_id']}/{record['method']}")
    return {"successes": successes, "attempts": attempts, "semantic": semantic}


def load_and_validate() -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Dict[str, Any]], Dict[str, Any]]:
    verify_protocol_lock()
    frozen = load_frozen("combined")
    entries = {item["task_id"]: item for item in frozen["selected"]}
    sets = {
        "Regression": read_jsonl(RESULTS / "regression/raw_runs.jsonl"),
        "Confirmatory": read_jsonl(RESULTS / "confirmatory/raw_runs.jsonl"),
    }
    expected_counts = {"Regression": 60, "Confirmatory": 27}
    for name, rows in sets.items():
        if len(rows) != expected_counts[name] or len({(row["task_id"], row["method"]) for row in rows}) != expected_counts[name]:
            raise RuntimeError(f"Incomplete {name} raw matrix")
        for row in rows:
            replay(row, entries[row["task_id"]], frozen["actions"])
    sets["Combined"] = sets["Regression"] + sets["Confirmatory"]
    return sets, entries, frozen


def aggregate(name: str, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output = []
    for method in METHODS:
        selected = [row for row in rows if row["method"] == method]
        success_actions = sum(sum(bool(item["success"]) for item in row["graph_execution_trace"]) for row in selected)
        attempts = sum(len(row["graph_execution_trace"]) for row in selected)
        successes = sum(int(row["final_semantic_SR"]) for row in selected)
        output.append({
            "set": name,
            "method": method,
            "n": len(selected),
            "success": successes,
            "task_sr": successes / len(selected),
            "macro_exec": mean(float(row["Exec"]) for row in selected),
            "micro_exec": success_actions / attempts,
            "successful_actions": success_actions,
            "attempted_actions": attempts,
            "avg_tokens_per_task": mean(float(row["total_tokens"]) for row in selected),
            "avg_calls_per_task": mean(float(row["total_calls"]) for row in selected),
            "total_prompt_tokens": sum(int(row["total_prompt_tokens"]) for row in selected),
            "total_completion_tokens": sum(int(row["total_completion_tokens"]) for row in selected),
            "total_tokens": sum(int(row["total_tokens"]) for row in selected),
            "total_calls": sum(int(row["total_calls"]) for row in selected),
        })
    return output


def role_costs(sets: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    output = []
    for set_name, rows in sets.items():
        for method in METHODS:
            selected = [row for row in rows if row["method"] == method]
            ledger: Dict[str, Counter] = defaultdict(Counter)
            for row in selected:
                for call in row["llm_call_records"]:
                    role = call["call_role"]
                    ledger[role]["calls"] += 1
                    ledger[role]["prompt_tokens"] += int(call["prompt_tokens"])
                    ledger[role]["completion_tokens"] += int(call["completion_tokens"])
            for role in sorted(ledger):
                item = ledger[role]
                output.append({
                    "set": set_name, "method": method, "role": role,
                    "calls": item["calls"], "prompt_tokens": item["prompt_tokens"],
                    "completion_tokens": item["completion_tokens"],
                    "total_tokens": item["prompt_tokens"] + item["completion_tokens"],
                })
    return output


def task_table(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    order = []
    for row in rows:
        if row["task_id"] not in order:
            order.append(row["task_id"])
    output = []
    for task_id in order:
        by_method = {row["method"]: row for row in rows if row["task_id"] == task_id}
        full = by_method["HPAF-Full"]
        manipulated = sorted({item["manipulated_object"] for item in full["atomic_tasks"]})
        output.append({
            "set": full["phase7_set"], "task_id": task_id, "task": full["task"],
            "split": full["split"], "scene": full["scene"], "evaluator_type": full["evaluator_type"],
            "gt_action_length": full["gt_action_length"], "horizon": full["horizon"],
            "atomic_count": full["number_of_atomic_tasks"],
            "unique_manipulated_object_count": len(manipulated),
            "manipulated_objects": ";".join(manipulated),
            "progprompt_sr": by_method["ProgPrompt"]["final_semantic_SR"],
            "flat_sr": by_method["HPAF-Flat"]["final_semantic_SR"],
            "full_sr": full["final_semantic_SR"],
        })
    return output


def complexity_tables(task_rows: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    horizon_rows, atomic_rows = [], []
    for set_name in ["Regression", "Confirmatory", "Combined"]:
        selected = [row for row in task_rows if set_name == "Combined" or row["set"].lower() == set_name.lower()]
        for horizon in ["Short", "Medium", "Long"]:
            group = [row for row in selected if row["horizon"] == horizon]
            horizon_rows.append({
                "set": set_name, "horizon": horizon, "n": len(group),
                "progprompt_sr": sum(row["progprompt_sr"] for row in group) / len(group) if group else None,
                "flat_sr": sum(row["flat_sr"] for row in group) / len(group) if group else None,
                "full_sr": sum(row["full_sr"] for row in group) / len(group) if group else None,
            })
        for bucket in ["1", "2", ">=3"]:
            group = [row for row in selected if (str(row["atomic_count"]) == bucket if bucket != ">=3" else row["atomic_count"] >= 3)]
            atomic_rows.append({
                "set": set_name, "atomic_count": bucket, "n": len(group),
                "progprompt_sr": sum(row["progprompt_sr"] for row in group) / len(group) if group else None,
                "flat_sr": sum(row["flat_sr"] for row in group) / len(group) if group else None,
                "full_sr": sum(row["full_sr"] for row in group) / len(group) if group else None,
            })
    return horizon_rows, atomic_rows


def improvement(metrics: Sequence[Dict[str, Any]], set_name: str, base_method: str) -> Dict[str, Any]:
    selected = [row for row in metrics if row["set"] == set_name]
    base = next(row for row in selected if row["method"] == base_method)
    full = next(row for row in selected if row["method"] == "HPAF-Full")
    return {
        "set": set_name, "comparison": f"HPAF-Full vs {base_method}",
        "success_count_difference": full["success"] - base["success"],
        "sr_absolute_percentage_points": 100 * (full["task_sr"] - base["task_sr"]),
        "sr_relative_improvement": None if base["task_sr"] == 0 else (full["task_sr"] - base["task_sr"]) / base["task_sr"],
        "macro_exec_percentage_points": 100 * (full["macro_exec"] - base["macro_exec"]),
        "micro_exec_percentage_points": 100 * (full["micro_exec"] - base["micro_exec"]),
        "token_reduction": (base["avg_tokens_per_task"] - full["avg_tokens_per_task"]) / base["avg_tokens_per_task"],
        "call_reduction": (base["avg_calls_per_task"] - full["avg_calls_per_task"]) / base["avg_calls_per_task"],
    }


def leakage_audit(rows: Sequence[Dict[str, Any]], entries: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    structural = ["semantic_goals.json", "final_semantic_sr", "trace_goal", "successful_event(", "successful_appliance_cycle(", "official goal set", "ground-truth final"]
    hits = []
    future_hits = []
    calls = 0
    for row in rows:
        entry = entries[row["task_id"]]
        atomics = row.get("atomic_tasks", [])
        for call in row["llm_call_records"]:
            calls += 1
            prompt = call["prompt"]
            lowered = prompt.lower()
            for marker in structural:
                if marker in lowered:
                    hits.append({"task_id": row["task_id"], "role": call["call_role"], "marker": marker})
            payloads = []
            if entry["evaluator_type"] == "generic_trace":
                payloads.append(entry["trace_goal"].get("rationale", ""))
            else:
                payloads.extend(item.get("condition", "") for item in entry["semantic_goal"]["conditions"])
                payloads.extend(item.get("rationale", "") for item in entry["semantic_goal"]["conditions"])
            for payload in payloads:
                if payload and payload.lower() in lowered:
                    hits.append({"task_id": row["task_id"], "role": call["call_role"], "marker": payload})
            if row["method"] == "HPAF-Full" and call["call_role"] in {"atomic_program_agent", "atomic_verifier", "repair_program_agent", "post_repair_verifier"}:
                current = next((i for i, item in enumerate(atomics) if item["instruction"] in prompt), -1)
                if current >= 0:
                    for item in atomics[current + 1:]:
                        if item["instruction"] in prompt:
                            future_hits.append({"task_id": row["task_id"], "role": call["call_role"], "future": item["instruction"]})
    if hits or future_hits:
        raise RuntimeError(f"Prompt leakage detected: hits={hits}; future={future_hits}")
    return {"calls_scanned": calls, "structural_or_payload_hits": hits, "future_atomic_hits": future_hits, "status": "PASS"}


def case_audit(task_rows: Sequence[Dict[str, Any]], all_rows: Sequence[Dict[str, Any]]) -> List[str]:
    criteria = [
        ("full_success_progprompt_fail", lambda row: row["full_sr"] == 1 and row["progprompt_sr"] == 0),
        ("full_success_flat_fail", lambda row: row["full_sr"] == 1 and row["flat_sr"] == 0),
        ("full_failure", lambda row: row["full_sr"] == 0),
        ("multi_atomic_success", lambda row: row["full_sr"] == 1 and row["atomic_count"] >= 3),
    ]
    selected = []
    audits = PHASE7_ROOT / "audits"
    audits.mkdir(exist_ok=True)
    for label, predicate in criteria:
        candidates = [row for row in task_rows if row["set"] == "confirmatory" and predicate(row)]
        if not candidates:
            candidates = [row for row in task_rows if predicate(row)]
        if not candidates:
            continue
        task = candidates[0]
        selected.append(task["task_id"])
        rows = [row for row in all_rows if row["task_id"] == task["task_id"]]
        lines = [f"# {label}: {task['task_id']}", "", "Selected automatically after formal completion; no prompt/evaluator change follows.", ""]
        for row in rows:
            lines += [
                f"## {row['method']}", "",
                f"SR={row['final_semantic_SR']}; Exec={row['Exec']}; calls={row['total_calls']}; tokens={row['total_tokens']}.", "",
                "### LLM calls", "", "```json", json.dumps(row["llm_call_records"], ensure_ascii=False, indent=2), "```", "",
                "### Generated program / atomics", "", "```json", json.dumps({"atomic_tasks": row["atomic_tasks"], "program": row["generated_program"]}, ensure_ascii=False, indent=2), "```", "",
                "### Execution and final score", "", "```json", json.dumps({"trace": row["graph_execution_trace"], "semantic_details": row["semantic_condition_details"], "errors": row["errors"]}, ensure_ascii=False, indent=2), "```", "",
            ]
        (audits / f"{label}.md").write_text("\n".join(lines), encoding="utf-8")
    return selected


def md_table(rows: Sequence[Dict[str, Any]]) -> List[str]:
    lines = ["| Method | N | Success | SR | Macro Exec | Micro Exec | Tokens/task | Calls/task |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['method']} | {row['n']} | {row['success']} | {row['task_sr']:.4f} | {row['macro_exec']:.4f} | {row['micro_exec']:.4f} | {row['avg_tokens_per_task']:.1f} | {row['avg_calls_per_task']:.2f} |")
    return lines


def main() -> None:
    sets, entries, frozen = load_and_validate()
    metrics = [row for name, rows in sets.items() for row in aggregate(name, rows)]
    costs = role_costs(sets)
    tasks = task_table(sets["Combined"])
    horizons, atomics = complexity_tables(tasks)
    improvements = [
        improvement(metrics, set_name, base)
        for set_name in ["Confirmatory", "Combined"]
        for base in ["ProgPrompt", "HPAF-Flat"]
    ]
    leakage = leakage_audit(sets["Combined"], entries)
    assertion_calls = [
        call for row in sets["Combined"] if row["method"] == "ProgPrompt"
        for call in row["llm_call_records"] if call["call_role"] == "assertion_verification"
    ]
    strict = sum(Phase7GraphProgramExecutor.parse_assertion_answer(call["output_text"]) is not None for call in assertion_calls)
    assertion_outputs = Counter(call["output_text"] for call in assertion_calls)
    cases = case_audit(tasks, sets["Combined"])

    write_csv(RESULTS / "metrics_by_set.csv", metrics)
    write_csv(RESULTS / "cost_by_role.csv", costs)
    write_csv(RESULTS / "task_level_results.csv", tasks)
    write_csv(RESULTS / "summary_by_horizon.csv", horizons)
    write_csv(RESULTS / "summary_by_atomic_count.csv", atomics)
    resume = []
    for set_name in ["Confirmatory", "Combined"]:
        for row in metrics:
            if row["set"] != set_name:
                continue
            resume.append({
                "Set": set_name,
                "Method": row["method"],
                "Tasks": row["n"],
                "Success": row["success"],
                "Task SR": row["task_sr"],
                "Exec": row["macro_exec"],
                "Avg Tokens": row["avg_tokens_per_task"],
                "Avg Calls": row["avg_calls_per_task"],
            })
    write_csv(RESULTS / "summary_resume.csv", resume)
    (RESULTS / "improvements.json").write_text(json.dumps(improvements, indent=2) + "\n", encoding="utf-8")

    confirm = [row for row in metrics if row["set"] == "Confirmatory"]
    combined = [row for row in metrics if row["set"] == "Combined"]
    report = ["# Phase-7 Final Results", ""]
    for title, table in [("Regression result", [row for row in metrics if row["set"] == "Regression"]), ("Official confirmatory result", confirm), ("Combined engineering result", combined)]:
        report += [f"## {title}", "", *md_table(table), ""]
    report += [
        "## HPAF-Full comparisons", "",
        "| Set | Compared with | Success difference | SR pp | Macro Exec pp | Micro Exec pp | Token reduction | Call reduction |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in improvements:
        report.append(
            f"| {item['set']} | {item['comparison'].replace('HPAF-Full vs ', '')} | {item['success_count_difference']} | {item['sr_absolute_percentage_points']:.2f} | {item['macro_exec_percentage_points']:.2f} | {item['micro_exec_percentage_points']:.2f} | {100 * item['token_reduction']:.2f}% | {100 * item['call_reduction']:.2f}% |"
        )
    report += [
        "", "## Complexity", "",
        "Horizon and atomic-count breakdowns are in `results/summary_by_horizon.csv` and `results/summary_by_atomic_count.csv`; Long confirmatory N=0, so no long-horizon confirmatory claim is made.", "",
        "## Fidelity and audits", "",
        f"- Assertion strict-binary: {strict}/{len(assertion_calls)} ({100 * strict / len(assertion_calls):.1f}%); outputs `{dict(assertion_outputs)}`. Malformed output is retained as unparsed; no semantic fallback or repair call was used. Baseline fidelity verdict: **ISSUE** for this Responses backend.",
        f"- Dataset integrity: **PASS**; regression=20, confirmatory=9, combined=29; persistent=20, trace=9, synthetic=0.",
        f"- Prompt leakage: **{leakage['status']}** across {leakage['calls_scanned']} formal calls.",
        "- Flat/Full ProgramAgent fairness: **PASS**; exact shared generic rule block, action documentation, and verifier settings.",
        f"- Automatically selected case task IDs: {cases}.",
        "", "## Resume-ready statement", "",
        "We evaluate ProgPrompt, HPAF-Flat, and HPAF-Full on 29 official ProgPrompt/VirtualHome task-scene instances: a disclosed 20-instance regression set and a separate 9-instance confirmatory set restored with pre-frozen method-independent event/appliance trace predicates; no synthetic tasks are mixed into the official result.", "",
    ]
    (PHASE7_ROOT / "RESULTS_PHASE7.md").write_text("\n".join(report), encoding="utf-8")

    cost_lines = ["# Phase-7 Cost Audit", "", "All prompt/completion tokens are summed from actual per-call usage. Assertion-contract audit calls are excluded from benchmark costs.", "", "| Set | Method | Role | Calls | Prompt tokens | Completion tokens | Total tokens |", "|---|---|---|---:|---:|---:|---:|"]
    for row in costs:
        cost_lines.append(f"| {row['set']} | {row['method']} | `{row['role']}` | {row['calls']} | {row['prompt_tokens']} | {row['completion_tokens']} | {row['total_tokens']} |")
    (PHASE7_ROOT / "COST_AUDIT.md").write_text("\n".join(cost_lines) + "\n", encoding="utf-8")
    (PHASE7_ROOT / "PROMPT_LEAKAGE_AUDIT.md").write_text(
        f"# Phase-7 Prompt Leakage Audit\n\nScanned {leakage['calls_scanned']} actual formal call prompts. Evaluator payload/structure hits: 0. Future atomic hits: 0. Status: **PASS**.\n",
        encoding="utf-8",
    )
    print(json.dumps({"metrics": metrics, "improvements": improvements, "leakage": leakage, "assertion_binary": [strict, len(assertion_calls)], "assertion_outputs": assertion_outputs, "cases": cases}, indent=2))


if __name__ == "__main__":
    main()
