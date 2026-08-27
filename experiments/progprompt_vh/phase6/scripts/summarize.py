#!/usr/bin/env python3
"""Validate and summarize the immutable Phase-6 formal first run."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from experiments.progprompt_vh.phase6.runner import (
    METHODS,
    PHASE6_ROOT,
    implementation_sha256,
    load_config,
    validate_complete_records,
    verify_protocol_lock,
)


RESULTS = PHASE6_ROOT / "results"
RAW = RESULTS / "raw_runs.jsonl"
PLOTS = PHASE6_ROOT / "plots"
HORIZONS = ["Short", "Medium", "Long"]
COLORS = {"ProgPrompt": "#4C78A8", "HPAF-Flat": "#F58518", "HPAF-Full": "#54A24B"}


def read_rows() -> List[Dict[str, Any]]:
    return [json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines() if line.strip()]


def avg(rows: Sequence[Dict[str, Any]], field: str) -> float:
    values = [row[field] for row in rows]
    if not rows or any(value is None for value in values):
        raise RuntimeError(f"Cannot average missing {field}")
    return mean(float(value) for value in values)


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def task_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "task_id": row["task_id"],
            "task": row["task"],
            "split": row["split"],
            "scene": row["scene"],
            "gt_action_length": row["gt_action_length"],
            "horizon": row["horizon"],
            "method": row["method"],
            "semantic_sr": row["final_semantic_SR"],
            "semantic_gcr": row["semantic_GCR"],
            "official_sr": row["official_SR"],
            "official_gcr": row["official_GCR"],
            "exec": row["Exec"],
            "generation_calls": row["generation_calls"],
            "verification_calls": row["verification_calls"],
            "repair_calls": row["repair_calls"],
            "total_calls": row["total_calls"],
            "prompt_tokens": row["prompt_tokens"],
            "completion_tokens": row["completion_tokens"],
            "total_tokens": row["total_tokens"],
            "planning_latency": row["planning_latency"],
            "verification_latency": row["verification_latency"],
            "total_llm_latency": row["total_llm_latency"],
            "number_of_atomic_tasks": row["number_of_atomic_tasks"],
            "atomic_tasks_attempted": row["atomic_tasks_attempted"],
            "retry_count": row["retry_count"],
            "early_stop_count": row["early_stop_count"],
            "online_done": row["final_online_done"],
            "error_type": row["error_type"],
        }
        for row in rows
    ]


def main_summary(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for method in METHODS:
        selected = [row for row in rows if row["method"] == method]
        long_rows = [row for row in selected if row["horizon"] == "Long"]
        result.append({
            "method": method,
            "overall_sr": avg(selected, "final_semantic_SR"),
            "long_sr": avg(long_rows, "final_semantic_SR"),
            "exec": avg(selected, "Exec"),
            "avg_tokens_per_task": avg(selected, "total_tokens"),
            "avg_calls_per_task": avg(selected, "total_calls"),
        })
    return result


def _role_stats(selected: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    role_counts: Counter = Counter()
    role_tokens: Counter = Counter()
    for row in selected:
        for call in row["llm_call_records"]:
            role_counts[call["call_role"]] += 1
            if call["prompt_tokens"] is None or call["completion_tokens"] is None:
                raise RuntimeError("Missing per-call token usage")
            role_tokens[call["call_role"]] += call["prompt_tokens"] + call["completion_tokens"]
    n = len(selected)
    return {
        **{f"avg_{role}_calls": role_counts[role] / n for role in sorted(role_counts)},
        **{f"avg_{role}_tokens": role_tokens[role] / n for role in sorted(role_tokens)},
    }


def supplementary(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for method in METHODS:
        selected = [row for row in rows if row["method"] == method]
        atomics = [item for row in selected for item in row["atomic_records"]]
        first_pass = sum(int(item["first_done"]) for item in atomics) / len(atomics) if atomics else 0.0
        result.append({
            "method": method,
            "n_tasks": len(selected),
            "semantic_gcr": avg(selected, "semantic_GCR"),
            "official_sr": avg(selected, "official_SR"),
            "official_gcr": avg(selected, "official_GCR"),
            "avg_planning_latency": avg(selected, "planning_latency"),
            "avg_verification_latency": avg(selected, "verification_latency"),
            "avg_total_llm_latency": avg(selected, "total_llm_latency"),
            "avg_generation_calls": avg(selected, "generation_calls"),
            "avg_verification_calls": avg(selected, "verification_calls"),
            "avg_repair_calls": avg(selected, "repair_calls"),
            "avg_atomic_tasks": avg(selected, "number_of_atomic_tasks"),
            "retry_rate_per_attempted_atomic": sum(row["retry_count"] for row in selected) / sum(row["atomic_tasks_attempted"] for row in selected) if sum(row["atomic_tasks_attempted"] for row in selected) else 0.0,
            "first_pass_atomic_success": first_pass,
            "early_stop_count": sum(row["early_stop_count"] for row in selected),
            **_role_stats(selected),
        })
    # DictWriter requires a common schema because methods have different roles.
    fields = []
    for row in result:
        for key in row:
            if key not in fields:
                fields.append(key)
    return [{key: row.get(key, 0.0) for key in fields} for row in result]


def horizon_summary(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for horizon in HORIZONS:
        by_method = {method: [row for row in rows if row["method"] == method and row["horizon"] == horizon] for method in METHODS}
        counts = {len(value) for value in by_method.values()}
        if len(counts) != 1 or not counts:
            raise RuntimeError(f"Horizon task-count mismatch: {horizon}")
        result.append({
            "horizon": horizon,
            "n_tasks": next(iter(counts)),
            "progprompt_sr": avg(by_method["ProgPrompt"], "final_semantic_SR"),
            "hpaf_flat_sr": avg(by_method["HPAF-Flat"], "final_semantic_SR"),
            "hpaf_full_sr": avg(by_method["HPAF-Full"], "final_semantic_SR"),
        })
    return result


def pivot_tasks(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    ids = []
    for row in rows:
        if row["task_id"] not in ids:
            ids.append(row["task_id"])
    for task_id in ids:
        selected = {row["method"]: row for row in rows if row["task_id"] == task_id}
        first = selected[METHODS[0]]
        out = {"task_id": task_id, "task": first["task"], "split": first["split"], "horizon": first["horizon"], "gt_action_length": first["gt_action_length"]}
        for method, prefix in [("ProgPrompt", "progprompt"), ("HPAF-Flat", "flat"), ("HPAF-Full", "full")]:
            row = selected[method]
            out.update({f"{prefix}_sr": row["final_semantic_SR"], f"{prefix}_exec": row["Exec"], f"{prefix}_tokens": row["total_tokens"], f"{prefix}_calls": row["total_calls"]})
        result.append(out)
    return result


def improvement(main: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    base = next(row for row in main if row["method"] == "ProgPrompt")
    full = next(row for row in main if row["method"] == "HPAF-Full")
    def relative(new: float, old: float) -> Any:
        return None if old == 0 else (new - old) / old
    return {
        "overall_sr_absolute_percentage_points": 100 * (full["overall_sr"] - base["overall_sr"]),
        "overall_sr_relative": relative(full["overall_sr"], base["overall_sr"]),
        "long_sr_absolute_percentage_points": 100 * (full["long_sr"] - base["long_sr"]),
        "long_sr_relative": relative(full["long_sr"], base["long_sr"]),
        "exec_absolute_percentage_points": 100 * (full["exec"] - base["exec"]),
        "token_reduction": (base["avg_tokens_per_task"] - full["avg_tokens_per_task"]) / base["avg_tokens_per_task"],
        "call_reduction": (base["avg_calls_per_task"] - full["avg_calls_per_task"]) / base["avg_calls_per_task"],
    }


def plot_success(main: Sequence[Dict[str, Any]]) -> None:
    x = np.arange(len(METHODS))
    width = 0.34
    overall = [next(row["overall_sr"] for row in main if row["method"] == method) for method in METHODS]
    long = [next(row["long_sr"] for row in main if row["method"] == method) for method in METHODS]
    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    ax.bar(x - width / 2, overall, width, label="Overall")
    ax.bar(x + width / 2, long, width, label="Long horizon")
    ax.set_xticks(x, METHODS)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Semantic task success rate")
    ax.set_title("Phase-6 task success rate")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    for xpos, value in list(zip(x - width / 2, overall)) + list(zip(x + width / 2, long)):
        ax.text(xpos, min(value + 0.025, 0.97), f"{value:.2f}", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(PLOTS / "task_success_rate.png", dpi=300)
    fig.savefig(PLOTS / "task_success_rate.pdf")
    plt.close(fig)


def plot_cost(main: Sequence[Dict[str, Any]]) -> None:
    tokens = [next(row["avg_tokens_per_task"] for row in main if row["method"] == method) for method in METHODS]
    calls = [next(row["avg_calls_per_task"] for row in main if row["method"] == method) for method in METHODS]
    x = np.arange(len(METHODS))
    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    ax.bar(x, tokens, color=[COLORS[method] for method in METHODS], width=0.62)
    ax.set_xticks(x, METHODS)
    ax.set_ylim(0, max(tokens) * 1.18)
    ax.set_ylabel("Average total tokens per task")
    ax.set_title("Phase-6 LLM cost")
    ax.grid(axis="y", alpha=0.25)
    for xpos, token, call in zip(x, tokens, calls):
        ax.text(xpos, token, f"{token:.0f}\n({call:.1f} calls)", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(PLOTS / "llm_cost.png", dpi=300)
    fig.savefig(PLOTS / "llm_cost.pdf")
    plt.close(fig)


def taskset_markdown(frozen: Dict[str, Any]) -> str:
    selected = frozen["selected"]
    entries = frozen["manifest"]["entries"]
    lengths = [item["gt_action_length"] for item in selected]
    split_counts = Counter(item["official_split"] for item in selected)
    horizon_counts = Counter(item["horizon"] for item in selected)
    lines = [
        "# Phase-6 Task-Set Summary", "",
        "Official dataset source: ProgPrompt / VirtualHome pinned release.", "",
        f"Final held-out tasks: {len(selected)} task-scene instances.", "",
        "Split composition: " + ", ".join(f"{key}={value}" for key, value in split_counts.items()) + ".", "",
        f"GT action length: min {min(lengths)} / mean {mean(lengths):.2f} / median {float(np.median(lengths)):.1f} / max {max(lengths)}.", "",
        f"Short count: {horizon_counts['Short']}", "",
        f"Medium count: {horizon_counts['Medium']}", "",
        f"Long count: {horizon_counts['Long']}", "",
        "## Filtered held-out candidates", "",
    ]
    for item in entries:
        if item["filter_status"] == "excluded_unrepresentable":
            lines.append(f"- `{item['task_id']}`: {item['filter_reason']}")
    lines += [
        "", "## Seen-task exclusion", "",
        "All 10 test_seen entries are excluded before held-out candidacy because their exact task texts occur in train; the three released default prompt examples are also in this slice.", "",
        "## Resume/interview setting sentence", "",
        f'“Evaluated on {len(selected)} official held-out VirtualHome household task-scene instances from ProgPrompt, with ground-truth action horizons ranging from {min(lengths)} to {max(lengths)}; all methods use the same LLM backbone and shared executable action interface.”', "",
    ]
    return "\n".join(lines)


def render_results(main: Sequence[Dict[str, Any]], supp: Sequence[Dict[str, Any]], horizons: Sequence[Dict[str, Any]], imp: Dict[str, Any], raw_sha: str) -> str:
    lines = [
        "# Phase-6 Results", "",
        f"Exactly 20 frozen held-out task-scene instances × 3 methods × one formal run; 60 unique records. Raw SHA-256 `{raw_sha}`.", "",
        "## Resume-oriented main table", "",
        "| Method | Overall SR ↑ | Long SR ↑ | Exec ↑ | Avg Tokens / Task ↓ | Avg Calls / Task |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in main:
        lines.append(f"| {row['method']} | {row['overall_sr']:.3f} | {row['long_sr']:.3f} | {row['exec']:.3f} | {row['avg_tokens_per_task']:.1f} | {row['avg_calls_per_task']:.2f} |")
    lines += ["", "## HPAF-Full relative to ProgPrompt", ""]
    for key, value in imp.items():
        lines.append(f"- {key}: {'undefined (zero baseline)' if value is None else f'{value:.6f}'}")
    lines += ["", "## Horizon", "", "| Horizon | #Tasks | ProgPrompt SR | HPAF-Flat SR | HPAF-Full SR |", "|---|---:|---:|---:|---:|"]
    for row in horizons:
        lines.append(f"| {row['horizon']} | {row['n_tasks']} | {row['progprompt_sr']:.3f} | {row['hpaf_flat_sr']:.3f} | {row['hpaf_full_sr']:.3f} |")
    lines += ["", "## Supplementary", "", "The complete official metrics, semantic GCR, latency, repair, atomic, and per-role cost breakdown is in `results/summary_supplementary.csv`.", ""]
    return "\n".join(lines)


def main() -> None:
    config = load_config()
    frozen = verify_protocol_lock(config)
    rows = read_rows()
    task_ids = [item["task_id"] for item in frozen["selected"]]
    validate_complete_records(rows, task_ids, "formal")
    if len(rows) != 60 or len({(row["task_id"], row["method"]) for row in rows}) != 60:
        raise RuntimeError("Formal raw result must contain exactly 60 unique pairs")
    expected_settings = {("ark", "doubao-seed-2-1-pro-260628", 0.0, 600, "disabled")}
    settings = {(row["provider"], row["model"], float(row["temperature"]), int(row["max_tokens"]), row["thinking"]) for row in rows}
    if settings != expected_settings:
        raise RuntimeError(f"Formal settings mismatch: {settings}")
    if any(row["total_calls"] != row["generation_calls"] + row["verification_calls"] + row["repair_calls"] for row in rows):
        raise RuntimeError("LLM call categories do not sum to total")
    if any(any(call["error_type"] for call in row["llm_call_records"]) for row in rows):
        raise RuntimeError("Formal raw result contains an LLM call error")

    tasks = task_rows(rows)
    main_rows = main_summary(rows)
    supp = supplementary(rows)
    horizons = horizon_summary(rows)
    pivots = pivot_tasks(rows)
    imp = improvement(main_rows)
    write_csv(RESULTS / "task_results.csv", tasks)
    write_csv(RESULTS / "summary_main.csv", main_rows)
    write_csv(RESULTS / "summary_supplementary.csv", supp)
    write_csv(RESULTS / "summary_by_horizon.csv", horizons)
    write_csv(RESULTS / "task_level_results.csv", pivots)
    (RESULTS / "TASKSET_SUMMARY.md").write_text(taskset_markdown(frozen), encoding="utf-8")
    (RESULTS / "improvements.json").write_text(json.dumps(imp, indent=2) + "\n", encoding="utf-8")
    PLOTS.mkdir(parents=True, exist_ok=True)
    plot_success(main_rows)
    plot_cost(main_rows)
    raw_sha = hashlib.sha256(RAW.read_bytes()).hexdigest()
    (PHASE6_ROOT / "RESULTS_PHASE6.md").write_text(render_results(main_rows, supp, horizons, imp, raw_sha), encoding="utf-8")
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "formal_raw_runs_sha256": raw_sha,
        "record_count": len(rows),
        "unique_task_method_pairs": len({(row["task_id"], row["method"]) for row in rows}),
        "method_counts": {method: sum(row["method"] == method for row in rows) for method in METHODS},
        "implementation_sha256": implementation_sha256(),
        "frozen_hashes": frozen["lock"],
    }
    (RESULTS / "formal_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"main": main_rows, "improvement": imp}, indent=2))
    print(f"formal_raw_runs_sha256={raw_sha}")


if __name__ == "__main__":
    main()

