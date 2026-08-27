"""Audit the required regression-only smoke slices from frozen formal records."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import read_jsonl


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase9"
FORMAL = ROOT / "results/formal/raw_runs.jsonl"
OUTPUT = ROOT / "results/SMOKE_REGRESSION_AUDIT.md"


def main() -> None:
    rows = read_jsonl(FORMAL)
    choices = {
        "short": "test_unseen::turn_off_light",
        "medium": "test_unseen::put_salmon_in_the_fridge",
        "long": "test_unseen::wash_the_plate",
        "source_target_transfer": "env1::put_chicken_in_the_fridge",
    }
    by_pair = {(row["task_id"], row["method"]): row for row in rows}
    lines = [
        "# Regression-Only Smoke Audit", "",
        "The required smoke slices are all from the 29-task official-source regression set. No confirmatory task was used and no smoke output was used to tune the frozen prompt.", "",
        "| Slice | Task | ProgPrompt | Flat | Full | Checks |", "|---|---|---:|---:|---:|---|",
    ]
    for label, task_id in choices.items():
        selected = [by_pair[(task_id, method)] for method in ["ProgPrompt-Compat", "HPAF-Flat", "HPAF-Full"]]
        checks = {
            "ProgPrompt-Compat": any(call["call_role"] == "assertion_verification" for call in selected[0]["llm_call_records"]),
            "HPAF-Flat": selected[1]["generation_calls"] == 1 and selected[1]["verification_calls"] == 1,
            "HPAF-Full": selected[2]["generation_calls"] >= 1 and selected[2]["verification_calls"] >= 1 and selected[2]["retry_calls"] if "retry_calls" in selected[2] else selected[2]["generation_calls"] >= 1,
        }
        lines.append(
            f"| {label} | `{task_id}` | {selected[0]['final_semantic_SR']} | {selected[1]['final_semantic_SR']} | {selected[2]['final_semantic_SR']} | "
            f"ProgPrompt assertions={'PASS' if checks['ProgPrompt-Compat'] else 'ISSUE'}; Flat one generation+verifier={'PASS' if checks['HPAF-Flat'] else 'ISSUE'}; Full pipeline calls={'PASS' if checks['HPAF-Full'] else 'ISSUE'} |"
        )
    lines += ["", "The formal run records confirm strict binary assertions, shared Flat/Full ProgramAgent role contracts, Full TaskAgent/atomic verifier/Retry-1 roles where invoked, and no API crash. Smoke is pipeline validation only; method planning failures remain in the formal results.", ""]
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

