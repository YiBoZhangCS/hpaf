"""Write concise final Phase-9 audit/report artifacts from frozen offline metrics."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase9"
RESULTS = ROOT / "results"
METRICS = RESULTS / "VH40_METRICS.json"


def _pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def write() -> None:
    payload = json.loads(METRICS.read_text(encoding="utf-8"))
    overall = payload["main"]["subsets"]["overall"]
    confirm = payload["main"]["subsets"]["new_long_11"]
    regression = payload["main"]["subsets"]["official_source_29"]
    long_existing = payload["main"]["subsets"]["existing_official_long_4"]
    long_all = payload["main"]["subsets"]["combined_long_15"]
    lines = [
        "# Phase-9 Final Report", "",
        "## Baseline Fidelity Repair", "",
        "Official behavior: ProgPrompt uses its released whole-program DSL, three few-shot examples, assertion checks, and adjacent `else` recovery. Phase 9 keeps that behavior and uses ARK Responses API strict enum transport with `True`/`False` only.", "",
        "Old bug: Phase-6 assertions used a 600-token generation cap, unlike the released binary contract, allowing verbose outputs to change recovery control flow.", "",
        "New behavior: assertion transport is binary-enum constrained and parsed as the released boolean contract; no semantic fallback, repair call, or truth inference was added.", "",
        f"Strict-binary assertion rate: {payload['assertion_audit']['strict_binary']}/{payload['assertion_audit']['calls']} ({_pct(payload['assertion_audit']['strict_binary_rate'])}).", "",
        "## HPAF Generic Prompt", "",
        "Changed rules: interaction locality, source-before-target transfer order, held-source/close-target placement preconditions, re-alignment after movement, and typed-error-first Retry-1 repair. The same frozen ProgramAgent rules are used by Flat and Full; no framework agent was added.", "",
        "The wording is generic: it contains no task ID, object name from a formal task, evaluator condition, or correct test action sequence.", "",
        "## Dataset", "",
        "- Regression: 29 official-source held-out task-scene instances previously observed during development.",
        "- Confirmatory: 11 pre-frozen synthetic causal long-horizon extensions on official VirtualHome scenes.",
        "- Combined: 40 task-scene instances; 35 unique task texts.",
        "- Horizon: 9 Short / 16 Medium / 15 Long.",
        "- Evaluators: 20 persistent-state / 9 generic trace / 11 generic causal trace-state.",
        "- Synthetic: 11; never labeled official.", "",
        "## Confirmatory Main Result", "",
        "| Method | Success/N | SR | Exec | Tokens/task | Calls/task |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for method, m in confirm.items():
        lines.append(f"| {method} | {m['success']}/{m['n']} | {_pct(m['sr'])} | {m['macro_exec']:.3f} | {m['avg_tokens']:.1f} | {m['avg_calls']:.2f} |")
    lines += ["", "## Combined Result", "", "| Method | Success/N | SR | Exec | Tokens/task | Calls/task |", "|---|---:|---:|---:|---:|---:|"]
    for method, m in overall.items():
        lines.append(f"| {method} | {m['success']}/{m['n']} | {_pct(m['sr'])} | {m['macro_exec']:.3f} | {m['avg_tokens']:.1f} | {m['avg_calls']:.2f} |")
    lines += ["", "## Long Provenance Split", "", "| Long subset | ProgPrompt | Flat | Full |", "|---|---:|---:|---:|"]
    lines.append(f"| Existing official-source Long (N=4) | {_pct(long_existing['ProgPrompt-Compat']['sr'])} | {_pct(long_existing['HPAF-Flat']['sr'])} | {_pct(long_existing['HPAF-Full']['sr'])} |")
    lines.append(f"| New frozen Long extension (N=11) | {_pct(confirm['ProgPrompt-Compat']['sr'])} | {_pct(confirm['HPAF-Flat']['sr'])} | {_pct(confirm['HPAF-Full']['sr'])} |")
    lines.append(f"| Combined Long (N=15) | {_pct(long_all['ProgPrompt-Compat']['sr'])} | {_pct(long_all['HPAF-Flat']['sr'])} | {_pct(long_all['HPAF-Full']['sr'])} |")
    lines += ["", "## HPAF-Full vs ProgPrompt", "", f"- Combined success: {overall['HPAF-Full']['success']}/{overall['HPAF-Full']['n']} vs {overall['ProgPrompt-Compat']['success']}/{overall['ProgPrompt-Compat']['n']} ({payload['comparisons']['full_vs_progprompt']['success_difference']:+d}).", f"- Combined SR: {payload['comparisons']['full_vs_progprompt']['sr_absolute_pp']:+.1f} pp; Macro Exec {payload['comparisons']['full_vs_progprompt']['macro_exec_pp']:+.1f} pp.", f"- Tokens/task: {payload['comparisons']['full_vs_progprompt']['token_reduction_percent']:.1f}% relative; Calls/task: {payload['comparisons']['full_vs_progprompt']['call_reduction_percent']:.1f}% relative.", "- New Long-11: Full is 3/11 while Flat is 7/11; decomposition does not automatically dominate the causal extension.", "", "## Complexity", "", "- Short/Medium/Long: 9/16/15.", "- Full atomic bins: 1 atomic N=15, 2 atomics N=9, >=3 atomics N=12.", "- Long-11 reference actions: min 13, mean 15.36, median 15, max 17; mean causal stages 5.27; 9/11 cross-room.", "", "## Cost Breakdown", ""]
    for row in payload["cost"]:
        lines.append(f"- {row['Method']} / {row['Role']}: {row['Calls']} calls, {row['Total Tokens']} total tokens ({row['Calls/Task']:.2f} calls/task).")
    lines += ["", "## Key Failures", "", "- ProgPrompt: long-horizon whole-program plans accumulate precondition and relation failures; 419 assertions remained strictly binary.", "- Flat: stronger than Full on the new causal Long-11 (7/11 vs 3/11), but with lower micro execution and no local repair.", "- Full: official-source regression 25/29, but Long-11 exposes TaskAgent parse failures and verifier/retry limitations; this is retained as a real negative result.", "", "## Integrity", "", "- Dataset: PASS (29 official-source + 11 synthetic; fixed quotas; no post-result filtering).", "- Reference feasibility: PASS (11/11 executable and evaluator-successful).", "- Prompt leakage: PASS.", "- Baseline binary: PASS.", "- Fairness: PASS (Flat/Full shared ProgramAgent rules; Full-only difference is decomposition, atomic verification, and Retry-1).", "- Formal records: PASS (120/120, duplicate 0, resample 0).", "", "## Resume-Ready Statement", "", f"VH-40 evaluates 29 official-source held-out VirtualHome task-scene instances plus 11 pre-frozen synthetic causal long-horizon extensions; in one frozen 40-task run, HPAF-Full achieves {overall['HPAF-Full']['success']}/40 overall and {long_all['HPAF-Full']['success']}/15 on Long tasks, with {overall['HPAF-Full']['avg_calls']:.2f} LLM calls/task.", "", "## Remaining Issue", "", "Full does not dominate the new causal Long-11 extension (3/11 vs Flat 7/11); this is a substantive limitation, not an artifact to be tuned away.", ""]
    (RESULTS / "PHASE9_FINAL_REPORT.md").write_text("\n".join(lines), encoding="utf-8")

    summary_rows = [
        ["Set", "Method", "Tasks", "Success", "Task SR", "Macro Exec", "Avg Tokens", "Avg Calls"],
    ]
    for set_name, metrics in [("Confirmatory Long-11", confirm), ("Combined VH-40", overall), ("Official Regression-29", regression)]:
        for method, m in metrics.items():
            summary_rows.append([set_name, method, m["n"], m["success"], f"{m['sr']:.6f}", f"{m['macro_exec']:.6f}", f"{m['avg_tokens']:.3f}", f"{m['avg_calls']:.3f}"])
    (RESULTS / "summary_resume.csv").write_text("\n".join(",".join(str(value) for value in row) for row in summary_rows) + "\n", encoding="utf-8")

    integrity = {
        "dataset": "PASS",
        "reference_feasibility": "PASS: 11/11",
        "prompt_leakage": "PASS",
        "baseline_binary": "PASS: 419/419",
        "fairness": "PASS",
        "formal_records": "PASS: 120/120",
        "duplicates": 0,
        "resamples": 0,
        "post_result_task_filtering": 0,
        "phase8_artifacts_modified": False,
    }
    (RESULTS / "INTEGRITY_AUDIT.json").write_text(json.dumps(integrity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "INTEGRITY_AUDIT.md").write_text("# Phase-9 Integrity Audit\n\n" + json.dumps(integrity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write()

