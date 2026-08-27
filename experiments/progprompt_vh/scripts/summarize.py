#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from experiments.progprompt_vh.adapters.dataset import TASK_ORDERS
from experiments.progprompt_vh.adapters.paths import EXPERIMENT_ROOT, RESULTS_ROOT


METHODS = [
    "ProgPrompt-Full",
    "HPAF-Decomp-Static",
    "HPAF-Decomp-ClosedLoop",
]
HORIZONS = ["Short", "Medium", "Long"]
COLORS = ["#4472C4", "#ED7D31", "#70AD47"]


def load_and_validate(path: Path) -> pd.DataFrame:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    expected_tasks = TASK_ORDERS["test_unseen"]
    expected_pairs = {(task, method) for task in expected_tasks for method in METHODS}
    actual_pairs = {(row["task"], row["method"]) for row in rows}
    if len(rows) != 30 or len(actual_pairs) != 30 or actual_pairs != expected_pairs:
        raise RuntimeError(
            f"Expected exactly 30 audited pairs; rows={len(rows)}, "
            f"unique_pairs={len(actual_pairs)}"
        )
    providers = {row["provider"] for row in rows}
    models = {row["model"] for row in rows}
    graph_hashes = {row["initial_state_sha256"] for row in rows}
    if len(providers) != 1 or len(models) != 1 or len(graph_hashes) != 1:
        raise RuntimeError(
            f"Comparison drift: providers={providers}, models={models}, "
            f"initial_graph_hashes={graph_hashes}"
        )
    for row in rows:
        if row.get("prompt_tokens") is None or row.get("completion_tokens") is None:
            raise RuntimeError(f'Missing token usage for {row["task"]} / {row["method"]}')
        row["total_tokens"] = row["prompt_tokens"] + row["completion_tokens"]
    frame = pd.DataFrame(rows)
    frame["method"] = pd.Categorical(frame["method"], METHODS, ordered=True)
    frame["difficulty_bucket"] = pd.Categorical(
        frame["difficulty_bucket"], HORIZONS, ordered=True
    )
    task_order = {task: index for index, task in enumerate(expected_tasks)}
    frame["task_order"] = frame["task"].map(task_order)
    return frame.sort_values(["task_order", "method"]).reset_index(drop=True)


def write_csvs(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    task_columns = [
        "run_id",
        "timestamp",
        "task",
        "method",
        "provider",
        "model",
        "scene",
        "initial_state_sha256",
        "ground_truth_action_length",
        "difficulty_bucket",
        "goal_condition_count",
        "number_of_atomic_tasks",
        "SR",
        "GCR",
        "PSR",
        "Precision",
        "Exec",
        "program_length",
        "llm_calls",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "planning_latency",
        "wall_clock_total_s",
        "error_type",
        "error_message",
    ]
    frame[task_columns].to_csv(RESULTS_ROOT / "task_results.csv", index=False)

    overall = (
        frame.groupby("method", observed=True)
        .agg(
            tasks=("task", "count"),
            SR=("SR", "mean"),
            GCR=("GCR", "mean"),
            Exec=("Exec", "mean"),
            Avg_Program_Length=("program_length", "mean"),
            Avg_LLM_Calls=("llm_calls", "mean"),
            Avg_Prompt_Tokens=("prompt_tokens", "mean"),
            Avg_Completion_Tokens=("completion_tokens", "mean"),
            Avg_Total_Tokens=("total_tokens", "mean"),
            Avg_Planning_Latency_s=("planning_latency", "mean"),
        )
        .reset_index()
    )
    overall.to_csv(RESULTS_ROOT / "summary_overall.csv", index=False)

    by_horizon = (
        frame.groupby(["difficulty_bucket", "method"], observed=True)
        .agg(
            tasks=("task", "count"),
            SR=("SR", "mean"),
            GCR=("GCR", "mean"),
            Exec=("Exec", "mean"),
            Avg_LLM_Calls=("llm_calls", "mean"),
            Avg_Total_Tokens=("total_tokens", "mean"),
        )
        .reset_index()
        .sort_values(["difficulty_bucket", "method"])
    )
    by_horizon.to_csv(RESULTS_ROOT / "summary_by_horizon.csv", index=False)
    return overall, by_horizon


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] + ["---:"] * (len(headers) - 1)) + "|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def write_markdown(overall: pd.DataFrame, by_horizon: pd.DataFrame) -> None:
    overall_rows = [
        [
            str(row.method),
            f"{row.SR:.3f}",
            f"{row.GCR:.3f}",
            f"{row.Exec:.3f}",
            f"{row.Avg_LLM_Calls:.2f}",
            f"{row.Avg_Total_Tokens:.1f}",
        ]
        for row in overall.itertuples()
    ]
    horizon_rows = [
        [
            str(row.difficulty_bucket),
            str(row.method),
            f"{row.SR:.3f}",
            f"{row.GCR:.3f}",
            f"{row.Exec:.3f}",
        ]
        for row in by_horizon.itertuples()
    ]
    content = """# Phase-4 result tables

`GCR` is the display name for the released evaluator's raw `PSR` field.

## Overall

{overall}

## By horizon

{horizon}
""".format(
        overall=markdown_table(
            ["Method", "SR", "GCR", "Exec", "Avg LLM Calls", "Avg Tokens"],
            overall_rows,
        ),
        horizon=markdown_table(
            ["Horizon", "Method", "SR", "GCR", "Exec"], horizon_rows
        ),
    )
    (RESULTS_ROOT / "RESULTS_TABLES.md").write_text(content, encoding="utf-8")


def plot_metric(by_horizon: pd.DataFrame, metric: str, title: str, ylabel: str) -> None:
    plot_dir = EXPERIMENT_ROOT / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    x = np.arange(len(HORIZONS))
    width = 0.24
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    for index, (method, color) in enumerate(zip(METHODS, COLORS)):
        subset = by_horizon[by_horizon["method"] == method].set_index(
            "difficulty_bucket"
        )
        values = [float(subset.loc[horizon, metric]) for horizon in HORIZONS]
        positions = x + (index - 1) * width
        bars = ax.bar(positions, values, width, label=method, color=color)
        ax.bar_label(
            bars,
            labels=[f"{value:.2f}" if metric != "Avg_Total_Tokens" else f"{value:.0f}" for value in values],
            padding=3,
            fontsize=8,
        )
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Ground-truth action horizon")
    ax.set_xticks(x, HORIZONS)
    ax.set_ylim(bottom=0)
    if metric in {"SR", "GCR", "Exec"}:
        ax.set_ylim(0, 1.08)
        ax.set_yticks(np.linspace(0, 1, 6))
    ax.grid(axis="y", alpha=0.25)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=3, frameon=False)
    fig.tight_layout()
    stem = {
        "SR": "sr_vs_task_horizon",
        "GCR": "gcr_vs_task_horizon",
        "Exec": "exec_vs_task_horizon",
        "Avg_Total_Tokens": "token_cost_vs_task_horizon",
    }[metric]
    fig.savefig(plot_dir / f"{stem}.png", dpi=200, bbox_inches="tight")
    fig.savefig(plot_dir / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    frame = load_and_validate(RESULTS_ROOT / "raw_runs.jsonl")
    overall, by_horizon = write_csvs(frame)
    write_markdown(overall, by_horizon)
    plot_metric(by_horizon, "SR", "Success Rate vs Task Horizon", "Success Rate")
    plot_metric(by_horizon, "GCR", "Goal Completion vs Task Horizon", "Goal Conditions Recall")
    plot_metric(by_horizon, "Exec", "Executability vs Task Horizon", "Executable Action Ratio")
    plot_metric(
        by_horizon,
        "Avg_Total_Tokens",
        "LLM Token Cost vs Task Horizon",
        "Average prompt + completion tokens",
    )
    print(overall.to_string(index=False))
    print()
    print(by_horizon.to_string(index=False))


if __name__ == "__main__":
    main()
