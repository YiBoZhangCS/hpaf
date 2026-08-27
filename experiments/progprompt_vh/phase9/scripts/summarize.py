"""Offline VH-40 metric, cost, leakage, failure, provenance, and case reports."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import read_jsonl, sha256
from experiments.progprompt_vh.phase9 import runner


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase9"
DATA = ROOT / "data"
RESULTS = ROOT / "results"
FORMAL = RESULTS / "formal/raw_runs.jsonl"
MANIFEST = DATA / "vh40_manifest.json"
LOCK = DATA / "VH40_PROTOCOL_LOCK.json"
SUMMARY_JSON = RESULTS / "VH40_METRICS.json"


def _load() -> tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    rows = read_jsonl(FORMAL)
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["entries"]
    by_id = {item["task_id"]: item for item in entries}
    if len(rows) != 120 or len({(r["task_id"], r["method"]) for r in rows}) != 120:
        raise RuntimeError("Formal raw runs are not 120 unique pairs")
    return rows, by_id


def _metric(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"n": 0, "success": 0, "sr": None, "macro_exec": None, "micro_exec": None, "avg_tokens": None, "avg_calls": None}
    successful_steps = sum(sum(int(item.get("success", False)) for item in r["graph_execution_trace"]) for r in rows)
    total_steps = sum(len(r["graph_execution_trace"]) for r in rows)
    return {
        "n": len(rows),
        "success": sum(int(r["final_semantic_SR"]) for r in rows),
        "sr": mean(float(r["final_semantic_SR"]) for r in rows),
        "macro_exec": mean(float(r["Exec"]) for r in rows),
        "micro_exec": successful_steps / total_steps if total_steps else 0.0,
        "avg_tokens": mean(float(r["total_tokens"]) for r in rows),
        "avg_calls": mean(float(r["total_calls"]) for r in rows),
    }


def _write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _method_metrics(rows: Sequence[Dict[str, Any]], ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    selected = set(ids)
    return {method: _metric([r for r in rows if r["method"] == method and r["task_id"] in selected]) for method in runner.METHODS}


def _fmt(value: Any, digits: int = 3) -> str:
    return "NA" if value is None else f"{float(value):.{digits}f}"


def _main_tables(rows: Sequence[Dict[str, Any]], by_id: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    all_ids = set(by_id)
    official_ids = {tid for tid, e in by_id.items() if e["official_or_extension"] == "official_source"}
    long_ids = {tid for tid, e in by_id.items() if e["horizon"] == "Long"}
    extension_ids = {tid for tid, e in by_id.items() if e["official_or_extension"] != "official_source"}
    existing_long = long_ids - extension_ids
    subsets = {
        "overall": all_ids,
        "official_source_29": official_ids,
        "new_long_11": extension_ids,
        "existing_official_long_4": existing_long,
        "combined_long_15": long_ids,
    }
    payload = {name: _method_metrics(rows, ids) for name, ids in subsets.items()}
    main_rows = []
    for method in runner.METHODS:
        overall = payload["overall"][method]
        long = payload["combined_long_15"][method]
        main_rows.append({
            "Method": method,
            "Success / 40": f"{overall['success']}/{overall['n']}",
            "Overall SR": overall["sr"],
            "Long Success / 15": f"{long['success']}/{long['n']}",
            "Long SR": long["sr"],
            "Macro Exec": overall["macro_exec"],
            "Calls/task": overall["avg_calls"],
            "Tokens/task": overall["avg_tokens"],
        })
    _write_csv(RESULTS / "VH40_MAIN_TABLE.csv", list(main_rows[0]), main_rows)

    subset_rows = []
    for subset, metrics in payload.items():
        for method, metric in metrics.items():
            subset_rows.append({"Subset": subset, "Method": method, **metric})
    _write_csv(RESULTS / "VH40_SUBSET_METRICS.csv", list(subset_rows[0]), subset_rows)
    return {"subsets": payload, "main": main_rows}


def _horizon_and_categories(rows: Sequence[Dict[str, Any]], by_id: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    horizon_rows = []
    for horizon in ["Short", "Medium", "Long"]:
        ids = {tid for tid, e in by_id.items() if e["horizon"] == horizon}
        metrics = _method_metrics(rows, ids)
        horizon_rows.append({"Horizon": horizon, "N": len(ids), **{method: metrics[method]["sr"] for method in runner.METHODS}})
    _write_csv(RESULTS / "VH40_HORIZON_TABLE.csv", list(horizon_rows[0]), horizon_rows)

    atomic_rows = []
    full_rows = {r["task_id"]: r for r in rows if r["method"] == "HPAF-Full"}
    atomic_bins = {"1": lambda n: n == 1, "2": lambda n: n == 2, ">=3": lambda n: n >= 3}
    for label, pred in atomic_bins.items():
        ids = {tid for tid, row in full_rows.items() if pred(int(row.get("number_of_atomic_tasks") or 0))}
        metrics = _method_metrics(rows, ids)
        atomic_rows.append({"Atomic count": label, "N": len(ids), **{method: metrics[method]["sr"] for method in runner.METHODS}})
    _write_csv(RESULTS / "VH40_ATOMIC_TABLE.csv", list(atomic_rows[0]), atomic_rows)
    return {"horizon": horizon_rows, "atomic": atomic_rows}


def _cost(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[tuple[str, str], Dict[str, int]] = defaultdict(lambda: {"calls": 0, "prompt": 0, "completion": 0})
    for row in rows:
        for call in row["llm_call_records"]:
            key = (row["method"], call["call_role"])
            values = grouped[key]
            values["calls"] += 1
            values["prompt"] += int(call.get("prompt_tokens") or 0)
            values["completion"] += int(call.get("completion_tokens") or 0)
    out = []
    for (method, role), values in sorted(grouped.items()):
        out.append({
            "Method": method, "Role": role, "Calls": values["calls"],
            "Prompt Tokens": values["prompt"], "Completion Tokens": values["completion"],
            "Total Tokens": values["prompt"] + values["completion"],
            "Calls/Task": values["calls"] / 40, "Tokens/Task": (values["prompt"] + values["completion"]) / 40,
        })
    _write_csv(RESULTS / "VH40_COST_BY_ROLE.csv", list(out[0]), out)
    return out


def _assertion_audit(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    calls = [call for row in rows if row["method"] == "ProgPrompt-Compat" for call in row["llm_call_records"] if call["call_role"] == "assertion_verification"]
    counts = Counter(str(call.get("output_text", "")).strip() for call in calls)
    strict = sum(counts[key] for key in ["True", "False"])
    return {
        "calls": len(calls), "strict_binary": strict,
        "strict_binary_rate": strict / len(calls) if calls else 0,
        "normalized_counts": dict(counts),
        "avg_completion_tokens": mean(int(call.get("completion_tokens") or 0) for call in calls) if calls else 0,
        "pass": strict == len(calls),
    }


def _leakage(rows: Sequence[Dict[str, Any]], by_id: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    own_instruction_missing = []
    cross_instruction_hits = []
    reference_hits = []
    evaluator_hits = []
    task_id_hits = []
    for row in rows:
        prompts = "\n".join((p.get("instructions") or "") + "\n" + p.get("input", "") for p in row.get("raw_prompts", [])).lower()
        entry = by_id[row["task_id"]]
        # ProgPrompt's released contract encodes the task in the unfinished
        # DSL function name, while HPAF carries the natural-language task field.
        # Both are valid task conditioning; absence of a literal task sentence
        # is not leakage or a failure.
        if row["method"] != "ProgPrompt-Compat" and entry["task_text"].lower() not in prompts:
            own_instruction_missing.append([row["task_id"], row["method"]])
        for other_id, other in by_id.items():
            if (
                other_id != row["task_id"]
                and other["task_text"].strip().lower() != entry["task_text"].strip().lower()
                and other["task_text"].lower() in prompts
            ):
                cross_instruction_hits.append([row["task_id"], row["method"], other_id])
        for marker in ["reference_program", "reference_action_sequence", "causal_goal", "goal_predicates", "reference_final_state"]:
            if marker in prompts:
                reference_hits.append([row["task_id"], row["method"], marker])
        reference_program = str(entry.get("reference_program", "")).strip().lower()
        if reference_program and reference_program in prompts:
            reference_hits.append([row["task_id"], row["method"], "reference_program_text"])
        causal_goal_text = json.dumps(entry.get("causal_goal", {}), ensure_ascii=False).lower()
        if causal_goal_text and causal_goal_text != "{}" and causal_goal_text in prompts:
            evaluator_hits.append([row["task_id"], row["method"], "causal_goal_payload"])
        for key in ["task_id"]:
            if str(entry.get(key, "")).lower() in prompts:
                task_id_hits.append([row["task_id"], row["method"], entry[key]])
        for condition in entry.get("semantic_goal", {}).get("conditions", []):
            if condition.get("condition", "").lower() in prompts:
                evaluator_hits.append([row["task_id"], row["method"], condition["condition"]])
        for condition in entry.get("causal_goal", {}).get("final_conditions", []):
            if condition.get("condition", "").lower() in prompts:
                evaluator_hits.append([row["task_id"], row["method"], condition["condition"]])
    result = {
        "own_instruction_missing": own_instruction_missing,
        "cross_instruction_hits": cross_instruction_hits,
        "task_id_hits": task_id_hits,
        "reference_marker_hits": reference_hits,
        "evaluator_condition_hits": evaluator_hits,
        "pass": not any([own_instruction_missing, cross_instruction_hits, task_id_hits, reference_hits, evaluator_hits]),
    }
    (RESULTS / "VH40_LEAKAGE_AUDIT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _failure_taxonomy(rows: Sequence[Dict[str, Any]], by_id: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    categories = ["goal_omission", "wrong_relation", "precondition_failure", "object_grounding", "state_staleness", "process_lifecycle_incomplete", "alignment_sequencing", "verification_retry_failure", "taskagent_parse_failure", "other"]
    counts: Dict[str, Counter] = {method: Counter() for method in runner.METHODS}
    examples: Dict[str, Dict[str, List[str]]] = {method: defaultdict(list) for method in runner.METHODS}
    for row in rows:
        if row["final_semantic_SR"]:
            continue
        errors = " ".join(str(item).lower() for item in row.get("errors", []))
        missing = json.dumps(row.get("semantic_missing_conditions", []), ensure_ascii=False).lower()
        if "taskagent_parse_failure" in errors or row.get("error_type") == "taskagent_parse_failure":
            category = "taskagent_parse_failure"
        elif "verifier" in errors or "parse_failure" in errors and row.get("method") == "HPAF-Full":
            category = "verification_retry_failure"
        elif "alignment" in errors or "close" in errors and "held" in errors:
            category = "alignment_sequencing"
        elif "precondition" in errors or "not in hand" in errors or "close" in errors:
            category = "precondition_failure"
        elif "inside(" in missing or "on(" in missing:
            category = "wrong_relation"
        elif "state(" in missing:
            category = "process_lifecycle_incomplete"
        elif row.get("atomic_tasks_attempted", 0) < row.get("number_of_atomic_tasks", 0):
            category = "goal_omission"
        else:
            category = "other"
        counts[row["method"]][category] += 1
        if len(examples[row["method"]][category]) < 5:
            examples[row["method"]][category].append(row["task_id"])
    output = {method: {"counts": dict(counts[method]), "examples": dict(examples[method])} for method in runner.METHODS}
    (RESULTS / "FAILURE_TAXONOMY.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Failure Taxonomy", "", "Offline categories are assigned from typed execution errors, missing frozen semantic conditions, and atomic accounting. No result was used to alter the frozen benchmark.", ""]
    for method in runner.METHODS:
        lines += [f"## {method}", ""]
        for category, count in counts[method].most_common():
            lines.append(f"- {category}: {count} ({', '.join(examples[method][category])})")
        lines.append("")
    (RESULTS / "FAILURE_TAXONOMY.md").write_text("\n".join(lines), encoding="utf-8")
    return output


def _comparison(metrics: Dict[str, Dict[str, Any]], first: str, second: str) -> Dict[str, Any]:
    a, b = metrics[first], metrics[second]
    return {
        "success_difference": a["success"] - b["success"],
        "sr_absolute_pp": 100 * (a["sr"] - b["sr"]),
        "sr_relative_percent": 100 * (a["sr"] - b["sr"]) / b["sr"] if b["sr"] else None,
        "macro_exec_pp": 100 * (a["macro_exec"] - b["macro_exec"]),
        "micro_exec_pp": 100 * (a["micro_exec"] - b["micro_exec"]),
        "token_reduction_percent": 100 * (b["avg_tokens"] - a["avg_tokens"]) / b["avg_tokens"] if b["avg_tokens"] else None,
        "call_reduction_percent": 100 * (b["avg_calls"] - a["avg_calls"]) / b["avg_calls"] if b["avg_calls"] else None,
    }


def _case_studies(rows: Sequence[Dict[str, Any]], by_id: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    grouped: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        grouped[row["task_id"]][row["method"]] = row
    predicates = {
        "01_full_success_progprompt_fail": lambda g: g["HPAF-Full"]["final_semantic_SR"] and not g["ProgPrompt-Compat"]["final_semantic_SR"],
        "02_full_success_flat_fail": lambda g: g["HPAF-Full"]["final_semantic_SR"] and not g["HPAF-Flat"]["final_semantic_SR"],
        "03_full_failure": lambda g: not g["HPAF-Full"]["final_semantic_SR"],
        "04_full_success_ge3_atomic": lambda g: g["HPAF-Full"]["final_semantic_SR"] and g["HPAF-Full"]["number_of_atomic_tasks"] >= 3,
    }
    selected: Dict[str, Any] = {}
    case_dir = ROOT / "case_studies"
    case_dir.mkdir(parents=True, exist_ok=True)
    for label, pred in predicates.items():
        matches = sorted(tid for tid, group in grouped.items() if pred(group))
        if not matches:
            selected[label] = None
            continue
        tid = matches[0]
        selected[label] = tid
        payload = {"case": label, "task": by_id[tid], "records": [grouped[tid][method] for method in runner.METHODS]}
        (case_dir / f"{label}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines = [f"# {label}", "", f"- Task: `{tid}`", f"- Instruction: {by_id[tid]['task_text']}", f"- Scene: {by_id[tid]['scene']}", ""]
        for method in runner.METHODS:
            row = grouped[tid][method]
            lines += [f"## {method}", "", f"- Success: {row['final_semantic_SR']}", f"- Exec: {row['Exec']:.3f}", f"- Tokens / calls: {row['total_tokens']} / {row['total_calls']}", f"- Error: {row.get('error_type') or 'none'}", "", "### Timeline", ""]
            for index, event in enumerate(row["execution_trace"], 1):
                lines.append(f"{index}. {'PASS' if event.get('success') else 'FAIL'} `{event.get('event')}` `{event.get('line', '')}` {event.get('detail') or ''}")
            lines.append("")
        (case_dir / f"{label}.md").write_text("\n".join(lines), encoding="utf-8")
    return selected


def _quality(by_id: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    long_entries = [e for e in by_id.values() if e["official_or_extension"] != "official_source"]
    lengths = [int(e["reference_horizon"]) for e in long_entries]
    categories = Counter(e.get("category") for e in long_entries)
    scenes = Counter(str(e["scene"]) for e in long_entries)
    quality = {
        "n": len(long_entries), "mean_reference_actions": mean(lengths), "median_reference_actions": median(lengths), "min": min(lengths), "max": max(lengths),
        "mean_causal_stages": mean(e["causal_stage_count"] for e in long_entries), "category_counts": dict(categories), "scene_counts": dict(scenes),
        "cross_room": sum(len(e.get("rooms_involved", [])) >= 2 for e in long_entries), "instructions": [e["task_text"] for e in long_entries],
    }
    (RESULTS / "LONG_HORIZON_QUALITY.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Long Horizon Quality", "", f"- N: {quality['n']}", f"- Reference actions: min {quality['min']}, mean {quality['mean_reference_actions']:.2f}, median {quality['median_reference_actions']:.1f}, max {quality['max']}", f"- Mean causal stages: {quality['mean_causal_stages']:.2f}", f"- Cross-room tasks: {quality['cross_room']}", f"- Categories: {dict(categories)}", "", "## Instructions", ""] + [f"- {item}" for item in quality["instructions"]]
    (RESULTS / "LONG_HORIZON_QUALITY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return quality


def _provenance(by_id: Mapping[str, Dict[str, Any]]) -> str:
    official = [e for e in by_id.values() if e["official_or_extension"] == "official_source"]
    extension = [e for e in by_id.values() if e["official_or_extension"] != "official_source"]
    train_rows = [row[0].strip().lower() for row in __import__("experiments.progprompt_vh.phase6.dataset", fromlist=["ordered_annotation_rows"]).ordered_annotation_rows("train")]
    task_unseen = sum(e["task_text"].strip().lower() not in train_rows for e in official)
    env_held = sum(e["official_split"] in {"env1", "env2"} for e in official)
    return f"""# VH-40 Provenance

VH-40 means the **VirtualHome 40-Task Evaluation Suite**, not an official 40-task ProgPrompt benchmark.

- Official-source component: {len(official)} held-out task-scene instances from the pinned ProgPrompt/VirtualHome release. The original primary inventory is 70 instances: 35 train/example and 35 held-out candidates. The protocol retains 29 candidates with method-independent persistent or generic trace evaluation; six ambiguous held-out candidates remain excluded.
- Synthetic component: {len(extension)} pre-frozen long-horizon extensions on official scene inventories, generated deterministically with seed `20260826`, fixed templates, category/scene quotas, reference replay, and no method output. They are not official tasks.
- Total task-scene instances: {len(by_id)}; unique task texts: {len({e['task_text'].strip().lower() for e in by_id.values()})}.
- Official task-unseen by exact train text: {task_unseen}/{len(official)}. Environment-held-out official instances: {env_held}/{len(official)}. Synthetic extensions are new instructions and separately labeled.
- Evaluators: 20 persistent-state, 9 frozen generic trace, 11 generic causal ordered-event plus final-state. All are method-independent and frozen before formal execution.

## Interview wording

“We evaluate on VH-40: 29 official-source held-out VirtualHome task-scene instances with method-independent scoring, plus 11 pre-frozen synthetic causal long-horizon extensions built on official VirtualHome scenes; all 40 are run once with three methods under a frozen evaluator.”
"""


def _ppt(main: Sequence[Mapping[str, Any]]) -> str:
    lines = ["# PPT Recommended Table", "", "| Method | Overall Task SR | Long Task SR | Exec | LLM Calls |", "|---|---:|---:|---:|---:|"]
    for row in main:
        lines.append(f"| {row['Method']} | {row['Success / 40']} ({100*float(row['Overall SR']):.1f}%) | {row['Long Success / 15']} ({100*float(row['Long SR']):.1f}%) | {float(row['Macro Exec']):.3f} | {float(row['Calls/task']):.2f} |")
    return "\n".join(lines) + "\n"


def summarize() -> Dict[str, Any]:
    rows, by_id = _load()
    RESULTS.mkdir(parents=True, exist_ok=True)
    main = _main_tables(rows, by_id)
    complexity = _horizon_and_categories(rows, by_id)
    costs = _cost(rows)
    assertions = _assertion_audit(rows)
    leakage = _leakage(rows, by_id)
    failures = _failure_taxonomy(rows, by_id)
    cases = _case_studies(rows, by_id)
    quality = _quality(by_id)
    overall = main["subsets"]["overall"]
    comparisons = {
        "full_vs_progprompt": _comparison(overall, "HPAF-Full", "ProgPrompt-Compat"),
        "full_vs_flat": _comparison(overall, "HPAF-Full", "HPAF-Flat"),
    }
    payload = {"main": main, "complexity": complexity, "cost": costs, "assertion_audit": assertions, "leakage": leakage, "failures": failures, "cases": cases, "quality": quality, "comparisons": comparisons}
    SUMMARY_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "PPT_RECOMMENDED_TABLE.md").write_text(_ppt(main["main"]), encoding="utf-8")
    (RESULTS / "VH40_PROVENANCE.md").write_text(_provenance(by_id), encoding="utf-8")
    (RESULTS / "PROMPT_LEAKAGE_AUDIT.md").write_text("# Prompt Leakage Audit\n\n" + json.dumps(leakage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "BINARY_ASSERTION_AUDIT.md").write_text("# ProgPrompt Binary Assertion Audit\n\n" + json.dumps(assertions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "COST_AUDIT.md").write_text("# Cost Audit\n\n" + json.dumps(costs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(summarize(), ensure_ascii=False, indent=2))
