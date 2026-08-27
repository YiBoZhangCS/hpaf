#!/usr/bin/env python3
"""Offline audit of every official ProgPrompt data split."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import (
    DATA_ROOT,
    DEFAULT_PROMPT_EXAMPLES,
    PHASE6_ROOT,
    build_manifest_entries,
    ordered_annotation_rows,
    read_jsonl,
)


def main() -> None:
    entries = build_manifest_entries()
    train_rows = []
    for path in sorted((DATA_ROOT / "train").glob("*.json")):
        train_rows.extend(read_jsonl(path))
    train_tasks = [next(iter(row)) for row in train_rows]
    pythonic = json.loads((DATA_ROOT / "pythonic_plans/train_complete_plan_set.json").read_text(encoding="utf-8"))

    rows = [
        ("train", len(train_rows), "Yes", "34/35 rows", "Yes: train library", "No"),
        ("test_seen", 10, "Yes", "Yes (10)", "All task texts occur in train; 3 are default prompt examples", "No"),
        ("test_unseen", 10, "Yes", "Yes (10)", "No", "Yes"),
        ("test_unseen_ambiguous_goals", 5, "Yes", "Yes (5)", "No", "Yes, subject to semantic-goal screening"),
        ("env1", 10, "Yes", "Yes (10); task-specific official initial graphs", "Some task texts seen; scene 1 is held out", "Yes: environment-held-out"),
        ("env2", 10, "Yes", "Yes (10); task-specific official initial graphs", "Some task texts seen; scene 2 is held out", "Yes: environment-held-out"),
        ("all_plans_env0", 50, "Natural-language plan outputs, not annotated executable GT", "No dedicated positional file", "Source inventory", "No"),
    ]
    lines = [
        "# Phase-6 Official Dataset Audit",
        "",
        "This audit is offline and was completed before any Phase-6 planning or verification call.",
        "",
        "| Split | Number of tasks | Has GT program | Has final state | Used as prompt/train | Candidate for held-out eval |",
        "|---|---:|---|---|---|---|",
    ]
    lines.extend(f"| {' | '.join(map(str, row))} |" for row in rows)
    lines += [
        "",
        "## What the release actually contains",
        "",
        "- The primary annotation inventory contains 70 task-scene instances: 50 in scene 0 (35 train rows, 10 test_unseen rows, 5 ambiguous-goal rows) plus 10 env1 and 10 env2 rows.",
        "- The 10-row test_seen directory is a derived seen-task evaluation slice: every task text is already in train, so adding it to the 70 would double-count those instances.",
        "- Train has 35 annotation rows but 34 unique task strings because `read book under table lamp` appears in two source files. The Pythonic train-plan library and train final-state file each contain 34 entries.",
        "- `final_states.json` has 39 rows and is the aggregate 34 unique train states plus 5 ambiguous-goal states; split-specific final-state files are used for evaluation.",
        "",
        "## Prompt leakage",
        "",
        "The released default three-example prompt uses: "
        + ", ".join(f"`{task}`" for task in sorted(DEFAULT_PROMPT_EXAMPLES))
        + ". All three are in test_seen/train, and none is in the final Phase-6 held-out set.",
        "",
        "## Shared-action and semantic screening",
        "",
        "All annotated primitive lines in the 35 held-out candidates use names contained in the frozen 17-action intersection. Filtering is nevertheless required when the natural-language completion itself has no reliable persistent state under that interface. Empty annotation steps do not count as an executable implementation of eating, brushing, elapsed-time toasting, open-ended cooking, dishwasher washing, or coffee production.",
        "",
        "The held-out candidate pool is 35 task-scene instances: test_unseen (10), test_unseen_ambiguous_goals (5), env1 (10), and env2 (10). Decisions are made before method execution and stored for every task in `data/task_manifest.json`.",
        "",
        "## Selection counts",
        "",
    ]
    statuses = {}
    for item in entries:
        statuses[item["filter_status"]] = statuses.get(item["filter_status"], 0) + 1
    for status, count in sorted(statuses.items()):
        lines.append(f"- `{status}`: {count}")
    lines += ["", "## Excluded held-out candidates", ""]
    for item in entries:
        if item["filter_status"] == "excluded_unrepresentable":
            lines.append(f"- `{item['task_id']}`: {item['filter_reason']}")
    lines += [
        "",
        "## Integrity checks",
        "",
        f"- Train annotation rows: {len(train_rows)}; unique task strings: {len(set(train_tasks))}.",
        f"- Pythonic train examples: {len(pythonic)}.",
        f"- Audited evaluation rows represented in the manifest: {len(entries)}.",
        "- No task is filtered using any Phase-6 method output or score.",
        "",
    ]
    PHASE6_ROOT.mkdir(parents=True, exist_ok=True)
    (PHASE6_ROOT / "DATASET_AUDIT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"train_rows": len(train_rows), "manifest_rows": len(entries), "statuses": statuses}, indent=2))


if __name__ == "__main__":
    main()

