#!/usr/bin/env python3
"""Validate and summarize the immutable 30-record Phase-5 formal first run."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from experiments.progprompt_vh.phase5.runner import (
    METHODS,
    PHASE5_ROOT,
    load_config,
    validate_complete_records,
    verify_protocol_lock,
)


RESULTS = PHASE5_ROOT / "results"
RAW = RESULTS / "raw_runs.jsonl"
PLOTS = PHASE5_ROOT / "plots"
HORIZONS = ["Short", "Medium", "Long"]
COLORS = {
    "ProgPrompt-GraphCompatible": "#4C78A8",
    "HPAF-Flat": "#F58518",
    "HPAF-Hierarchical": "#54A24B",
}


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def average(rows: Sequence[Dict[str, Any]], field: str) -> float:
    values = [row[field] for row in rows]
    if any(value is None for value in values):
        raise RuntimeError(f"Missing {field} in formal records")
    return mean(float(value) for value in values)


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty CSV: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def validate_formal(rows: List[Dict[str, Any]], frozen: Dict[str, Any]) -> None:
    tasks = [item["task"] for item in frozen["semantic"]["tasks"]]
    validate_complete_records(rows, tasks)
    if len(rows) != 30 or len({(row["task"], row["method"]) for row in rows}) != 30:
        raise RuntimeError("Formal raw results are not exactly 30 unique pairs")
    expected_settings = {
        ("ark", "doubao-seed-2-1-pro-260628", 0.0, 600, "disabled")
    }
    settings = {
        (
            row["provider"], row["model"], float(row["temperature"]),
            int(row["max_tokens"]), row["thinking"],
        )
        for row in rows
    }
    if settings != expected_settings:
        raise RuntimeError(f"Formal settings mismatch: {settings}")
    for row in rows:
        if row.get("phase") != "formal":
            raise RuntimeError("Non-formal record found in formal raw results")
        for key in ["action_set_sha256", "semantic_goal_sha256", "decomposition_sha256"]:
            if row[key] != frozen["lock"][key]:
                raise RuntimeError(f'{row["task"]}/{row["method"]}: {key} mismatch')
        if any(call.get("error_type") for call in row["llm_call_records"]):
            raise RuntimeError(f'{row["task"]}/{row["method"]}: LLM call error')
    hierarchical = [row for row in rows if row["method"] == "HPAF-Hierarchical"]
    if sum(row["verified_but_stopped_count"] for row in hierarchical) != 0:
        raise RuntimeError("Controller invariant failed: verified-but-stopped is nonzero")


def task_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "task": row["task"],
            "method": row["method"],
            "difficulty_bucket": row["difficulty_bucket"],
            "ground_truth_action_length": row["ground_truth_action_length"],
            "official_sr": row["SR"],
            "official_gcr": row["GCR"],
            "exec": row["Exec"],
            "semantic_sr": row["Semantic_SR"],
            "semantic_gcr": row["Semantic_GCR"],
            "llm_calls": row["llm_calls"],
            "prompt_tokens": row["prompt_tokens"],
            "completion_tokens": row["completion_tokens"],
            "total_tokens": row["total_tokens"],
            "planning_latency_s": row["planning_latency"],
            "program_length": row["program_length"],
            "number_of_atomic_tasks": row["number_of_atomic_tasks"],
            "atomic_tasks_attempted": row["atomic_tasks_attempted"],
            "retry_count": row["retry_count"],
            "early_stop_count": row["early_stop_count"],
            "verified_but_stopped_count": row["verified_but_stopped_count"],
            "error_type": row["error_type"],
        }
        for row in rows
    ]


def official_summary(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for method in METHODS:
        selected = [row for row in rows if row["method"] == method]
        result.append(
            {
                "method": method,
                "n_tasks": len(selected),
                "official_sr": average(selected, "SR"),
                "official_gcr": average(selected, "GCR"),
                "exec": average(selected, "Exec"),
                "avg_llm_calls": average(selected, "llm_calls"),
                "avg_tokens": average(selected, "total_tokens"),
                "avg_planning_latency_s": average(selected, "planning_latency"),
            }
        )
    return result


def semantic_summary(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for method in METHODS:
        selected = [row for row in rows if row["method"] == method]
        result.append(
            {
                "method": method,
                "n_tasks": len(selected),
                "semantic_sr": average(selected, "Semantic_SR"),
                "semantic_gcr": average(selected, "Semantic_GCR"),
            }
        )
    return result


def horizon_summary(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for horizon in HORIZONS:
        for method in METHODS:
            selected = [
                row
                for row in rows
                if row["method"] == method and row["difficulty_bucket"] == horizon
            ]
            if not selected:
                raise RuntimeError(f"No rows for {horizon}/{method}")
            result.append(
                {
                    "horizon": horizon,
                    "method": method,
                    "n_tasks": len(selected),
                    "official_sr": average(selected, "SR"),
                    "official_gcr": average(selected, "GCR"),
                    "exec": average(selected, "Exec"),
                    "semantic_sr": average(selected, "Semantic_SR"),
                    "semantic_gcr": average(selected, "Semantic_GCR"),
                    "avg_llm_calls": average(selected, "llm_calls"),
                    "avg_tokens": average(selected, "total_tokens"),
                    "avg_planning_latency_s": average(selected, "planning_latency"),
                }
            )
    return result


def hierarchy_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    selected = [row for row in rows if row["method"] == "HPAF-Hierarchical"]
    verifications = [item for row in selected for item in row["atomic_verifications"]]
    attempted = len(verifications)
    first_pass = sum(int(item["first_verified"]) for item in verifications)
    retried = sum(int(item["retry_used"]) for item in verifications)
    final_success = sum(int(item["final_verified"]) for item in verifications)
    repair_success = sum(
        int(item["repair_verified"] is True)
        for item in verifications
        if item["retry_used"]
    )
    return {
        "method": "HPAF-Hierarchical",
        "formal_tasks": len(selected),
        "frozen_atomic_tasks": sum(row["number_of_atomic_tasks"] for row in selected),
        "atomic_tasks_attempted": attempted,
        "avg_atomic_tasks": average(selected, "number_of_atomic_tasks"),
        "first_pass_atomic_success": first_pass / attempted,
        "retry_count": retried,
        "retry_rate": retried / attempted,
        "post_repair_atomic_success": final_success / attempted,
        "repair_recovery_success": repair_success / retried if retried else 0.0,
        "early_stop_count": sum(row["early_stop_count"] for row in selected),
        "verified_but_stopped_count": sum(
            row["verified_but_stopped_count"] for row in selected
        ),
    }


def grouped_rate_plot(
    summary: List[Dict[str, Any]], field: str, title: str, ylabel: str, stem: str
) -> None:
    x = np.arange(len(HORIZONS))
    width = 0.24
    fig, ax = plt.subplots(figsize=(8.4, 5.2))
    for index, method in enumerate(METHODS):
        values = [
            next(
                row[field]
                for row in summary
                if row["horizon"] == horizon and row["method"] == method
            )
            for horizon in HORIZONS
        ]
        ax.bar(
            x + (index - 1) * width,
            values,
            width,
            label=method,
            color=COLORS[method],
        )
    ax.set_xticks(x, HORIZONS)
    ax.set_ylim(0, 1)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(PLOTS / f"{stem}.png", dpi=300)
    fig.savefig(PLOTS / f"{stem}.pdf")
    plt.close(fig)


def token_plot(summary: List[Dict[str, Any]]) -> None:
    values = [next(row["avg_tokens"] for row in summary if row["method"] == method) for method in METHODS]
    fig, ax = plt.subplots(figsize=(8.4, 5.2))
    x = np.arange(len(METHODS))
    ax.bar(x, values, color=[COLORS[method] for method in METHODS], width=0.62)
    ax.set_xticks(x, ["ProgPrompt-GC", "HPAF-Flat", "HPAF-Hierarchical"])
    ax.set_ylim(0, max(values) * 1.15)
    ax.set_ylabel("Average prompt + completion tokens per task")
    ax.set_title("Formal planning token cost")
    ax.grid(axis="y", alpha=0.25)
    for position, value in zip(x, values):
        ax.text(position, value, f"{value:.0f}", ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(PLOTS / "token_cost.png", dpi=300)
    fig.savefig(PLOTS / "token_cost.pdf")
    plt.close(fig)


def retry_plot(stats: Dict[str, Any]) -> None:
    labels = ["First-pass\natomic success", "Retry rate", "Post-repair\natomic success", "Recovery among\nretried atomics"]
    values = [
        stats["first_pass_atomic_success"], stats["retry_rate"],
        stats["post_repair_atomic_success"], stats["repair_recovery_success"],
    ]
    fig, ax = plt.subplots(figsize=(8.4, 5.2))
    x = np.arange(len(labels))
    ax.bar(x, values, color=["#72B7B2", "#E45756", "#54A24B", "#B279A2"], width=0.62)
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Rate")
    ax.set_title("HPAF-Hierarchical Retry-1 statistics")
    ax.grid(axis="y", alpha=0.25)
    for position, value in zip(x, values):
        ax.text(position, min(value + 0.025, 0.97), f"{value:.2f}", ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(PLOTS / "hierarchical_retry_statistics.png", dpi=300)
    fig.savefig(PLOTS / "hierarchical_retry_statistics.pdf")
    plt.close(fig)


def fmt(value: float) -> str:
    return f"{value:.3f}"


def render_markdown(
    official: List[Dict[str, Any]],
    semantic: List[Dict[str, Any]],
    horizons: List[Dict[str, Any]],
    hierarchy: Dict[str, Any],
    raw_sha: str,
) -> str:
    official_by = {row["method"]: row for row in official}
    semantic_by = {row["method"]: row for row in semantic}
    lines = [
        "# Phase-5 Results",
        "",
        "This report uses exactly one formal run for each of 10 test_unseen tasks × "
        "three frozen methods. No repeats or task selection were performed.",
        "",
        "## Integrity",
        "",
        f"- Formal records: 30 unique task/method pairs; raw SHA-256 `{raw_sha}`.",
        "- Backend: ARK `doubao-seed-2-1-pro-260628`, Responses API, temperature 0, thinking disabled, max output 600.",
        "- `verified_but_stopped_count`: 0.",
        "- Frozen action/semantic/decomposition hashes match `PROTOCOL.md` in every record.",
        "",
        "## Official",
        "",
        "| Method | SR | GCR | Exec | Calls | Tokens |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for method in METHODS:
        row = official_by[method]
        lines.append(
            f"| {method} | {fmt(row['official_sr'])} | {fmt(row['official_gcr'])} | "
            f"{fmt(row['exec'])} | {row['avg_llm_calls']:.1f} | {row['avg_tokens']:.1f} |"
        )
    lines += [
        "",
        "Planning latency means (seconds/task): "
        + ", ".join(
            f"{method}={official_by[method]['avg_planning_latency_s']:.2f}"
            for method in METHODS
        )
        + ".",
        "",
        "## Semantic",
        "",
        "| Method | Semantic SR | Semantic GCR |",
        "|---|---:|---:|",
    ]
    for method in METHODS:
        row = semantic_by[method]
        lines.append(
            f"| {method} | {fmt(row['semantic_sr'])} | {fmt(row['semantic_gcr'])} |"
        )
    lines += [
        "",
        "## By horizon",
        "",
        "Each cell is Semantic SR (Official SR). Long contains only two tasks and is descriptive, not a significance claim.",
        "",
        "| Horizon | ProgPrompt-GraphCompatible | HPAF-Flat | HPAF-Hierarchical |",
        "|---|---:|---:|---:|",
    ]
    for horizon in HORIZONS:
        cells = []
        for method in METHODS:
            row = next(
                item for item in horizons if item["horizon"] == horizon and item["method"] == method
            )
            cells.append(f"{fmt(row['semantic_sr'])} ({fmt(row['official_sr'])})")
        lines.append(f"| {horizon} | {' | '.join(cells)} |")
    lines += [
        "",
        "## Repair",
        "",
        "| Method | First-pass atomic success | Retry rate | Post-repair atomic success |",
        "|---|---:|---:|---:|",
        f"| HPAF-Hierarchical | {fmt(hierarchy['first_pass_atomic_success'])} | "
        f"{fmt(hierarchy['retry_rate'])} | {fmt(hierarchy['post_repair_atomic_success'])} |",
        "",
        f"The hierarchy executed {hierarchy['atomic_tasks_attempted']} atomics from "
        f"{hierarchy['frozen_atomic_tasks']} frozen atomics, used Retry-1 "
        f"{hierarchy['retry_count']} time(s), recovered {fmt(hierarchy['repair_recovery_success'])} "
        "of retried atomics, and had "
        f"{hierarchy['early_stop_count']} early stops.",
        "",
        "## Interpretation",
        "",
        "- RQ1 — **NOT SUPPORTED in this single-run controlled set.** Flat and Hierarchical both reached Semantic SR=1.000 overall and in every horizon, so explicit decomposition showed no completion-rate gain. This does not establish equivalence and the Long group has only two tasks.",
        "- RQ2 — **SUPPORTED within the observed run.** One failed first pass was localized to the second atomic of the dual-object task; Retry-1 repaired it, execution continued, all 13 atomics finished, and verified-but-stopped stayed zero.",
        "- Official and semantic metrics materially disagree. All methods reached Semantic SR=1.000 on Long while Official SR was 0.000; both views are retained. The frozen make-toast proxy also reverses the official/semantic outcome for ProgPrompt versus both HPAF variants, as disclosed before execution.",
        "- ProgPrompt is much more expensive in calls/tokens because its assertion recovery performs additional state-check calls. HPAF-Hierarchical used more tokens than Flat when a task had multiple atomics or repair, but not enough to improve Semantic SR here.",
        "",
        "## Plots",
        "",
        "The `plots/` directory contains PNG and PDF versions of semantic SR/GCR, official SR, Exec by horizon, token cost, and hierarchical retry statistics. Rate plots use the full 0–1 y-axis.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    config = load_config()
    frozen = verify_protocol_lock(config)
    rows = read_jsonl(RAW)
    validate_formal(rows, frozen)
    task = task_rows(rows)
    official = official_summary(rows)
    semantic = semantic_summary(rows)
    horizons = horizon_summary(rows)
    hierarchy = hierarchy_stats(rows)
    write_csv(RESULTS / "task_results.csv", task)
    write_csv(RESULTS / "summary_official.csv", official)
    write_csv(RESULTS / "summary_semantic.csv", semantic)
    write_csv(RESULTS / "summary_by_horizon.csv", horizons)
    write_csv(RESULTS / "summary_hierarchical.csv", [hierarchy])

    PLOTS.mkdir(parents=True, exist_ok=True)
    grouped_rate_plot(horizons, "semantic_sr", "Semantic success rate by task horizon", "Semantic SR", "semantic_sr_vs_horizon")
    grouped_rate_plot(horizons, "semantic_gcr", "Semantic goal completion by task horizon", "Semantic GCR", "semantic_gcr_vs_horizon")
    grouped_rate_plot(horizons, "official_sr", "Official success rate by task horizon", "Official SR", "official_sr_vs_horizon")
    grouped_rate_plot(horizons, "exec", "Program executability by task horizon", "Exec", "exec_vs_horizon")
    token_plot(official)
    retry_plot(hierarchy)

    raw_sha = hashlib.sha256(RAW.read_bytes()).hexdigest()
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "formal_raw_runs_sha256": raw_sha,
        "record_count": len(rows),
        "unique_task_method_pairs": len({(row["task"], row["method"]) for row in rows}),
        "method_counts": {method: sum(row["method"] == method for row in rows) for method in METHODS},
        "verified_but_stopped_count": hierarchy["verified_but_stopped_count"],
        "frozen_hashes": frozen["lock"],
    }
    (RESULTS / "formal_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (PHASE5_ROOT / "RESULTS_PHASE5.md").write_text(
        render_markdown(official, semantic, horizons, hierarchy, raw_sha),
        encoding="utf-8",
    )
    print(json.dumps({"official": official, "semantic": semantic, "hierarchy": hierarchy}, indent=2))
    print(f"formal_raw_runs_sha256={raw_sha}")
    print("wrote summaries, RESULTS_PHASE5.md, and 12 plot files")


if __name__ == "__main__":
    main()

