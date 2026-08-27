"""Offline partial-order rescoring of frozen Phase-9 raw traces."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import read_jsonl
from experiments.progprompt_vh.phase10.verification.partial_order_evaluator import (
    evaluate_partial_order_goal,
    phase9_goal_to_partial_order,
)


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase10"
RAW = PROJECT_ROOT / "experiments/progprompt_vh/phase9/results/formal/raw_runs.jsonl"
MANIFEST = PROJECT_ROOT / "experiments/progprompt_vh/phase9/data/vh40_manifest.json"
REPORT = ROOT / "PHASE9_PARTIAL_ORDER_RESCORE.md"
DETAIL = ROOT / "results/phase9_partial_order_rescore.jsonl"
METHODS = ["ProgPrompt-Compat", "HPAF-Flat", "HPAF-Full"]


def _precomputed(row: Mapping[str, Any]) -> Dict[str, Tuple[bool, Any]]:
    result = {}
    for item in row.get("semantic_condition_details", []):
        if item.get("kind") != "final_state_condition":
            continue
        condition = item.get("condition", {})
        result[str(condition.get("condition", ""))] = (
            bool(item.get("satisfied")),
            item.get("evidence"),
        )
    return result


def build() -> List[Dict[str, Any]]:
    entries = {
        item["task_id"]: item
        for item in json.loads(MANIFEST.read_text(encoding="utf-8"))["entries"]
    }
    rows = read_jsonl(RAW)
    if len(rows) != 120:
        raise RuntimeError(f"Expected 120 Phase-9 records, found {len(rows)}")
    rescored: List[Dict[str, Any]] = []
    for row in rows:
        entry = entries[row["task_id"]]
        old = int(row["final_semantic_SR"])
        if entry.get("evaluator_type") != "generic_causal_trace_state":
            new = old
            score = None
            rejection = False
        else:
            goal = phase9_goal_to_partial_order(entry["causal_goal"], entry["category"])
            successful = [item for item in row.get("graph_execution_trace", []) if item.get("success")]
            rejection = row.get("error_type") == "taskagent_parse_failure" or (
                row["method"] == "HPAF-Full" and not successful and not row.get("atomic_tasks")
            )
            score = evaluate_partial_order_goal(
                {"graph_execution_trace": row["graph_execution_trace"]},
                goal,
                None,
                precomputed_final_conditions=_precomputed(row),
                implementation_rejection=rejection,
            )
            new = int(score["final_semantic_SR"])
        final_items = [
            item for item in row.get("semantic_condition_details", [])
            if item.get("kind") == "final_state_condition"
        ]
        rescored.append(
            {
                "task_id": row["task_id"],
                "task": row["task"],
                "method": row["method"],
                "old_success": old,
                "new_offline_success": new,
                "changed": old != new,
                "Exec": row["Exec"],
                "old_semantic_GCR": row["semantic_GCR"],
                "new_semantic_GCR": score["semantic_GCR"] if score else row["semantic_GCR"],
                "final_conditions_satisfied": bool(final_items) and all(
                    item.get("satisfied") for item in final_items
                ),
                "implementation_rejection": rejection,
                "error_type": row.get("error_type", ""),
                "partial_order_score": score,
            }
        )
    return rescored


def _aggregate(rows: List[Dict[str, Any]], field: str) -> Dict[str, Tuple[int, int]]:
    result: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    for item in rows:
        result[item["method"]][0] += int(item[field])
        result[item["method"]][1] += 1
    return {method: (values[0], values[1]) for method, values in result.items()}


def markdown(rows: List[Dict[str, Any]]) -> str:
    overall_old = _aggregate(rows, "old_success")
    overall_new = _aggregate(rows, "new_offline_success")
    long_rows = [item for item in rows if item["task_id"].startswith("vh40_long_")]
    long_old = _aggregate(long_rows, "old_success")
    long_new = _aggregate(long_rows, "new_offline_success")
    changed = [item for item in rows if item["changed"]]
    lines = [
        "# Phase-9 Partial-Order Offline Rescore",
        "",
        "No API/LLM call was made and no action was regenerated. The frozen Phase-9 traces are reinterpreted with semantic events, required dependency edges, terminal constraints, and final persistent goals. Reference program order is not task semantics.",
        "",
        "## VH-40",
        "",
        "| Method | Old VH40 SR | New offline SR |",
        "|---|---:|---:|",
    ]
    for method in METHODS:
        old_s, n = overall_old[method]
        new_s, _ = overall_new[method]
        lines.append(f"| {method} | {old_s}/{n} ({old_s/n:.1%}) | {new_s}/{n} ({new_s/n:.1%}) |")
    lines.extend(
        [
            "",
            "## Long-11",
            "",
            "| Method | Old Success | New Offline Success |",
            "|---|---:|---:|",
        ]
    )
    for method in METHODS:
        old_s, n = long_old[method]
        new_s, _ = long_new[method]
        lines.append(f"| {method} | {old_s}/{n} | {new_s}/{n} |")
    lines.extend(
        [
            "",
            "## Changed decisions",
            "",
            "| Task | Method | Exec | Final conditions | Old | New | Reason |",
            "|---|---|---:|---|---:|---:|---|",
        ]
    )
    for item in changed:
        reason = (
            "All required semantic events and DAG edges occurred; terminal close occurred after delivery, which is legal."
            if item["new_offline_success"]
            else "Partial-order semantic requirements failed."
        )
        lines.append(
            f"| `{item['task_id']}` | {item['method']} | {item['Exec']:.3f} | "
            f"{'yes' if item['final_conditions_satisfied'] else 'no'} | {item['old_success']} | "
            f"{item['new_offline_success']} | {reason} |"
        )
    rejections = [item for item in long_rows if item["implementation_rejection"]]
    lines.extend(
        [
            "",
            "## Implementation rejections remain failures",
            "",
            f"The {len(rejections)} TaskAgent parse/validation rejection records executed zero actions. They remain `FAIL` under offline rescoring and are labeled `implementation_rejection`; fixing the validator cannot counterfactually supply an execution trace.",
            "",
            "## Interpretation",
            "",
            "The score changes are evaluator corrections only. They do not claim that a new Phase-10 TaskAgent would have repaired any Phase-9 run. Unrelated legal operations may commute; required predecessor relationships still cannot be violated, and terminal/final conditions must still hold at task end.",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def main() -> Dict[str, Any]:
    if REPORT.exists() or DETAIL.exists():
        raise RuntimeError("Refusing to overwrite Phase-10 rescore artifacts")
    rows = build()
    _write_exclusive(
        DETAIL,
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows),
    )
    _write_exclusive(REPORT, markdown(rows))
    return {
        "records": len(rows),
        "changed": sum(item["changed"] for item in rows),
        "llm_calls": 0,
    }


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))

