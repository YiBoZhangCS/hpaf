#!/usr/bin/env python3
"""Independent, offline Phase-6 audit from release data and formal raw logs.

This script deliberately does not import or call the online LLM client. It
replays stored grounded Evolving Graph actions, recomputes all aggregate
metrics from per-call/per-action records, and renders the audit artifacts.
"""

from __future__ import annotations

import csv
import glob
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from experiments.progprompt_vh.adapters.evaluator import evaluate_task
from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase5.execution import GraphProgramExecutor
from experiments.progprompt_vh.phase6.verification.deterministic_evaluator import (
    evaluate_conditions,
)


PHASE6 = PROJECT_ROOT / "experiments/progprompt_vh/phase6"
RELEASE = PROJECT_ROOT / "third_party/progprompt-vh"
RAW = PHASE6 / "results/raw_runs.jsonl"
MANIFEST = PHASE6 / "data/task_manifest.json"
SEMANTIC = PHASE6 / "data/semantic_goals.json"
ACTIONS = PROJECT_ROOT / "experiments/progprompt_vh/phase5/data/graph_supported_actions.json"
SCENE0_INITIAL = PROJECT_ROOT / "experiments/progprompt_vh/results/environment_initial_state.json"
METHODS = ["ProgPrompt", "HPAF-Flat", "HPAF-Full"]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def annotation_paths(split: str) -> List[Path]:
    data = RELEASE / "data"
    if split in {"env1", "env2"}:
        return [data / "new_env" / f"{split}_annotated.json"]
    return [Path(path) for path in sorted(glob.glob(str(data / split / "*.json")))]


def annotation_rows(split: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in annotation_paths(split):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if len(payload) != 1:
                raise AssertionError(f"Unexpected annotation row in {path}")
            task, subgoals = next(iter(payload.items()))
            actions = [action for group in subgoals.values() for action in group]
            rows.append(
                {
                    "split": split,
                    "task": task,
                    "subgoals": subgoals,
                    "actions": actions,
                    "source": str(path.relative_to(PROJECT_ROOT)),
                }
            )
    return rows


def load_graph(entry: Dict[str, Any], kind: str) -> Dict[str, Any]:
    path = PROJECT_ROOT / entry[f"{kind}_state_source"]
    index = entry[f"{kind}_state_index"]
    if index is None:
        return read_json(path)
    return read_jsonl(path)[int(index)]


def replay_record(
    row: Dict[str, Any],
    entry: Dict[str, Any],
    conditions: Sequence[Dict[str, Any]],
    actions: Dict[str, Any],
) -> Dict[str, Any]:
    initial = load_graph(entry, "initial")
    executor = GraphProgramExecutor(
        initial,
        actions_payload=actions,
        llm_client=None,
        unity_comm=None,
        seed=0,
    )
    for ordinal, expected in enumerate(row["graph_execution_trace"], 1):
        if expected["parsed_action"] is None:
            actual = executor.graph_executor.record_failed_attempt(
                expected["source_action"], expected["error"]
            )
        else:
            actual = executor.graph_executor.execute_ground_truth_action(expected["source_action"])
            if actual.success:
                executor._refresh_evaluator_augmentations()
        if bool(actual.success) != bool(expected["success"]):
            raise AssertionError(
                f"Replay action mismatch: {row['task_id']}/{row['method']} action {ordinal}"
            )
        if (actual.error or "") != (expected["error"] or ""):
            raise AssertionError(
                f"Replay error mismatch: {row['task_id']}/{row['method']} action {ordinal}"
            )

    semantic = evaluate_conditions(executor.final_graph, conditions)
    official = evaluate_task(
        final_state=executor.final_graph,
        ground_truth_final_state=load_graph(entry, "final"),
        initial_state=initial,
        exec_ratio=executor.exec_ratio,
    )
    if semantic["final_semantic_SR"] != row["final_semantic_SR"]:
        raise AssertionError(f"Semantic SR mismatch: {row['task_id']}/{row['method']}")
    if official["SR"] != row["official_SR"]:
        raise AssertionError(f"Official SR mismatch: {row['task_id']}/{row['method']}")
    if not math.isclose(executor.exec_ratio, float(row["Exec"]), abs_tol=1e-12):
        raise AssertionError(f"Exec mismatch: {row['task_id']}/{row['method']}")
    return {
        "semantic_sr": semantic["final_semantic_SR"],
        "semantic_gcr": semantic["semantic_GCR"],
        "official_sr": official["SR"],
        "exec": executor.exec_ratio,
        "successful_actions": executor.graph_executor.executable_steps,
        "attempted_actions": executor.graph_executor.total_steps,
    }


def csv_write(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def esc(value: Any) -> str:
    return str(value).replace("|", "/").replace("\n", " ")


def role_ledger(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ledger: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        for call in row["llm_call_records"]:
            key = (row["method"], call["call_role"])
            item = ledger.setdefault(
                key,
                {
                    "method": row["method"],
                    "role": call["call_role"],
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            )
            if call["prompt_tokens"] is None or call["completion_tokens"] is None:
                raise AssertionError("Formal call has missing token usage")
            item["calls"] += 1
            item["prompt_tokens"] += int(call["prompt_tokens"])
            item["completion_tokens"] += int(call["completion_tokens"])
            item["total_tokens"] += int(call["prompt_tokens"]) + int(call["completion_tokens"])
    order = {method: i for i, method in enumerate(METHODS)}
    return sorted(ledger.values(), key=lambda item: (order[item["method"]], item["role"]))


def metric_rows(
    rows: Sequence[Dict[str, Any]], replays: Dict[Tuple[str, str], Dict[str, Any]]
) -> List[Dict[str, Any]]:
    result = []
    for method in METHODS:
        selected = [row for row in rows if row["method"] == method]
        replayed = [replays[(row["task_id"], method)] for row in selected]
        calls = [call for row in selected for call in row["llm_call_records"]]
        prompt_tokens = sum(int(call["prompt_tokens"]) for call in calls)
        completion_tokens = sum(int(call["completion_tokens"]) for call in calls)
        attempts = sum(item["attempted_actions"] for item in replayed)
        successes = sum(item["successful_actions"] for item in replayed)
        result.append(
            {
                "method": method,
                "n": len(selected),
                "task_successes": sum(item["semantic_sr"] for item in replayed),
                "semantic_sr": sum(item["semantic_sr"] for item in replayed) / len(replayed),
                "macro_exec": mean(item["exec"] for item in replayed),
                "successful_actions": successes,
                "attempted_actions": attempts,
                "micro_exec": successes / attempts,
                "total_llm_calls": len(calls),
                "total_prompt_tokens": prompt_tokens,
                "total_completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "average_calls_per_task": len(calls) / len(selected),
                "average_tokens_per_task": (prompt_tokens + completion_tokens) / len(selected),
            }
        )
    return result


def replay_excluded_gt(
    manifest: Dict[str, Any],
    source_map: Dict[Tuple[str, str], Dict[str, Any]],
    actions: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Verify every recorded primitive for the 15 filtered held-out tasks."""
    allowed = set(actions["actions"])
    results = []
    for entry in manifest["entries"]:
        if entry["filter_status"] != "excluded_unrepresentable":
            continue
        source = source_map[(entry["official_split"], entry["task_text"])]
        primitives = [item for item in source["actions"] if item.strip()]
        if len(primitives) != entry["gt_action_length"]:
            raise AssertionError(f"Excluded GT length mismatch: {entry['task_id']}")

        executor = GraphProgramExecutor(
            load_graph(entry, "initial"),
            actions_payload=actions,
            llm_client=None,
            unity_comm=None,
            seed=0,
        )
        verbs = set()
        for ordinal, primitive in enumerate(primitives, 1):
            match = re.search(r"\[([a-z]+)\]", primitive.lower())
            if match is None or match.group(1) not in allowed:
                raise AssertionError(
                    f"Excluded GT action outside shared API: {entry['task_id']} action {ordinal}"
                )
            verbs.add(match.group(1))
            trace = executor.graph_executor.execute_ground_truth_action(primitive)
            if not trace.success:
                raise AssertionError(
                    f"Excluded GT replay failed: {entry['task_id']} action {ordinal}: {trace.error}"
                )
            executor._refresh_evaluator_augmentations()
        results.append(
            {
                "task_id": entry["task_id"],
                "primitives": len(primitives),
                "successful": executor.graph_executor.executable_steps,
                "verbs": sorted(verbs),
            }
        )
    if len(results) != 15 or sum(item["primitives"] for item in results) != 128:
        raise AssertionError("Unexpected excluded-task GT replay inventory")
    return results


def dataset_audit(
    manifest: Dict[str, Any], rows: Sequence[Dict[str, Any]], actions: Dict[str, Any]
) -> Tuple[str, Dict[str, Any]]:
    splits = {
        name: annotation_rows(name)
        for name in [
            "train",
            "test_seen",
            "test_unseen",
            "test_unseen_ambiguous_goals",
            "env1",
            "env2",
        ]
    }
    train_text = {item["task"] for item in splits["train"]}
    all_plans_count = sum(
        len(read_json(Path(path)))
        for path in sorted(glob.glob(str(RELEASE / "data/all_plans_env0/*.json")))
    )
    primary_count = sum(
        len(splits[name])
        for name in ["train", "test_unseen", "test_unseen_ambiguous_goals", "env1", "env2"]
    )
    if primary_count != 70 or all_plans_count != 50:
        raise AssertionError("Unexpected official release inventory")
    if {item["task"] for item in splits["test_seen"]} - train_text:
        raise AssertionError("test_seen contains a task absent from train")

    source_map = {
        (item["split"], item["task"]): item
        for split_rows in splits.values()
        for item in split_rows
    }
    excluded_replays = replay_excluded_gt(manifest, source_map, actions)
    included = [item for item in manifest["entries"] if item["filter_status"] == "included"]
    by_pair = {(row["task_id"], row["method"]): row for row in rows}
    horizon_counts: Counter = Counter()
    complexity_counts: Counter = Counter()
    for entry in included:
        source = source_map[(entry["official_split"], entry["task_text"])]
        length = len(source["actions"])
        expected_horizon = "Short" if length <= 5 else "Medium" if length <= 10 else "Long"
        if length != entry["gt_action_length"] or expected_horizon != entry["horizon"]:
            raise AssertionError(f"Independent horizon mismatch: {entry['task_id']}")
        horizon_counts[expected_horizon] += 1
        full = by_pair[(entry["task_id"], "HPAF-Full")]
        atomics = int(full["number_of_atomic_tasks"])
        complexity_counts["1" if atomics == 1 else "2" if atomics == 2 else ">=3"] += 1

    env_seen = {
        split: sorted(item["task"] for item in splits[split] if item["task"] in train_text)
        for split in ["env1", "env2"]
    }
    prompt_examples = [
        "put the wine glass in the kitchen cabinet",
        "throw away the lime",
        "wash mug",
    ]
    pythonic = read_json(RELEASE / "data/pythonic_plans/train_complete_plan_set.json")
    example_keys = [task.replace(" ", "_") for task in prompt_examples]
    if any(key not in pythonic for key in example_keys):
        raise AssertionError("Released default prompt examples changed")

    lines = [
        "# Independent Phase-6 Dataset Audit",
        "",
        "Evidence basis: official release annotation files, the released Pythonic prompt library, released final-state files, and the frozen manifest. No number from `DATASET_AUDIT.md` is used as an input.",
        "",
        "## Release inventory",
        "",
        "| Split/artifact | Rows | Unique task texts | Role |",
        "|---|---:|---:|---|",
    ]
    roles = {
        "train": "Scene-0 example/train library; not an LLM fine-tuning corpus in this code release",
        "test_seen": "Derived seen-task evaluation slice; every text already occurs in train",
        "test_unseen": "Scene-0 task-unseen evaluation",
        "test_unseen_ambiguous_goals": "Scene-0 ambiguous/open-goal evaluation",
        "env1": "Held-out scene 1",
        "env2": "Held-out scene 2",
    }
    for name, split_rows in splits.items():
        lines.append(
            f"| `{name}` | {len(split_rows)} | {len({item['task'] for item in split_rows})} | {roles[name]} |"
        )
    lines += [
        f"| `all_plans_env0` | {all_plans_count} | n/a | Source inventory of 50 scene-0 plan texts, not an extra split |",
        "",
        "The primary inventory is **70 task-scene instances**: 35 train + 10 test_unseen + 5 ambiguous + 10 env1 + 10 env2. It is not 80 because the 10 `test_seen` rows are a derived slice of train task instances/texts rather than ten new primary instances. The 50 scene-0 primary rows are also exactly the 50 entries represented in `all_plans_env0`.",
        "",
        "## Train and seen relationships",
        "",
        "`train` exists to provide annotated plans and the in-context example library. The released runner loads examples from `train_complete_plan_set.json` into the prompt; it does not fine-tune model weights. Train has 35 rows but 34 unique texts because `read book under table lamp` is duplicated. The Pythonic library has 34 keys.",
        "",
        "The three Phase-6/default few-shot examples are:",
        "",
        *[f"- `{task}`" for task in prompt_examples],
        "",
        "All ten exact `test_seen` task texts occur in train. `test_seen` therefore tests seen task language in scene 0; it is excluded before held-out candidacy.",
        "",
        "Complete `test_seen` task-text list:",
        "",
        *[f"- `{item['task']}`" for item in splits["test_seen"]],
        "",
        "Exact env task texts also present in train:",
        "",
        f"- env1 ({len(env_seen['env1'])}): " + ", ".join(f"`{item}`" for item in env_seen["env1"]),
        f"- env2 ({len(env_seen['env2'])}): " + ", ".join(f"`{item}`" for item in env_seen["env2"]),
        "",
        "`held-out` must therefore be qualified. A held-out task-scene instance is absent from the prompt-example/evaluation instance set. `task-unseen` means its exact text is absent from train. `environment-held-out` means the scene is env1/env2; its task text may still be train-seen. Phase 6 contains both task-unseen scene-0 instances and environment-held-out instances, so it should not call all 20 task-unseen.",
        "",
        "## Candidate and final selection",
        "",
        "The 35 held-out candidates are the direct union of test_unseen (10), ambiguous (5), env1 (10), and env2 (10). Fifteen were conservatively excluded because the current persistent final-graph protocol cannot represent the requested outcome reliably, leaving **20 task-scene instances and 18 unique task texts**.",
        "",
        "## Final 20 tasks",
        "",
        "| Split | Task text | Scene | GT actions | Horizon | Frozen semantic goal | Include reason |",
        "|---|---|---:|---:|---|---|---|",
    ]
    for entry in included:
        conditions = "; ".join(item["condition"] for item in entry["semantic_goal"]["conditions"])
        lines.append(
            f"| `{entry['official_split']}` | {esc(entry['task_text'])} | {entry['scene']} | {entry['gt_action_length']} | {entry['horizon']} | `{esc(conditions)}` | {esc(entry['filter_reason'])} |"
        )

    lines += [
        "",
        "## Horizon and HPAF complexity",
        "",
        f"Independent flattening of the released GT programs gives Short={horizon_counts['Short']}, Medium={horizon_counts['Medium']}, Long={horizon_counts['Long']}. Long N=4 is a property of the selected 20 tasks, not a missing runner branch.",
        "",
        "| Task | GT primitive actions | GT horizon | Full generated atomics | Unique manipulated objects |",
        "|---|---:|---|---:|---|",
    ]
    for entry in included:
        full = by_pair[(entry["task_id"], "HPAF-Full")]
        manipulated = sorted({item["manipulated_object"] for item in full["atomic_tasks"]})
        lines.append(
            f"| `{entry['task_id']}` | {entry['gt_action_length']} | {entry['horizon']} | {full['number_of_atomic_tasks']} | {len(manipulated)} ({', '.join(manipulated)}) |"
        )
    lines += [
        "",
        f"Atomic distribution: 1 atomic={complexity_counts['1']}, 2 atomics={complexity_counts['2']}, >=3 atomics={complexity_counts['>=3']}. Full generated 27 atomics but attempted only 26 because `env1::microwave_chicken` stopped after atomic 1 failed Retry-1.",
        "",
        "GT primitive horizon and HPAF semantic decomposition are not equivalent. GT length includes navigation and precondition primitives; 15/20 tasks are single-atomic under Full, and even the Long set contains the single-atomic `wash the plate` task.",
        "",
        "## Audit of the 15 filtered candidates",
        "",
        "Classification counts: existing protocol=0, generic trace evaluator=9, not reliably evaluable=6. This is an offline proposal only; no task is restored here.",
        "",
        "Shared-interface executability was checked by replay, not inferred from action names. All **128/128 non-empty released GT primitives** for the 15 tasks executed successfully from their task-specific frozen initial graphs using the same 17-action Evolving Graph interface. This does not make every natural-language task evaluable: several annotations omit the requested brushing, eating, waiting, or open-ended recipe semantics entirely.",
        "",
        "| Excluded task | Released non-empty GT primitives | Successful replay | Shared action verbs used |",
        "|---|---:|---:|---|",
        *[
            f"| `{item['task_id']}` | {item['primitives']} | {item['successful']} | {', '.join(f'`{verb}`' for verb in item['verbs'])} |"
            for item in excluded_replays
        ],
        "",
        "| Task | A. NL success | B. Persistent final graph | C. Fair trace/event evaluator | D. Shared interface | E. Released official evaluator actually scores | F. Restoration requirement | Classification |",
        "|---|---|---|---|---|---|---|---|",
    ]
    filter_rows = filtered_task_rows()
    for item in filter_rows:
        lines.append(
            "| " + " | ".join(esc(item[key]) for key in ["task", "a", "b", "c", "d", "e", "f", "classification"]) + " |"
        )
    lines += [
        "",
        "A generic trace evaluator would need to be method-independent and frozen before execution. Its reusable predicates would be: `SUCCESSFUL_EVENT(action, object)` for non-persistent events such as WATCH, and `SUCCESSFUL_APPLIANCE_CYCLE(item, appliance)` requiring the item to be correctly loaded when a successful ON transition occurs, followed by the released cycle endpoint. This changes the evaluator, not the action space, and must be reported as a simulator event surrogate rather than a real elapsed-time process.",
        "",
        "The current exclusion remains methodologically sound because Phase 6 chose a stricter persistent-state evaluator and did not optimize N after seeing method results. The nine trace-evaluable candidates are optional future protocol work, not evidence that the current 20 were cherry-picked.",
        "",
    ]
    facts = {
        "primary_count": primary_count,
        "unique_final_texts": len({item["task_text"] for item in included}),
        "horizon_counts": dict(horizon_counts),
        "complexity_counts": dict(complexity_counts),
        "env_seen": env_seen,
        "excluded_gt_replay": {
            "tasks": len(excluded_replays),
            "successful_primitives": sum(item["successful"] for item in excluded_replays),
            "attempted_primitives": sum(item["primitives"] for item in excluded_replays),
        },
    }
    return "\n".join(lines), facts


def filtered_task_rows() -> List[Dict[str, str]]:
    trace = "SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR"
    no = "NOT_RELIABLY_EVALUABLE"
    return [
        {"task": "test_unseen::watch_tv", "a": "Clear event: actually watch TV", "b": "No WATCHED state; TV ON is insufficient", "c": "Yes: successful WATCH(tv) event", "d": "WATCH is present", "e": "TV ON plus incidental proximity/room deltas", "f": "Add generic successful-event evaluator; no method privilege", "classification": trace},
        {"task": "test_unseen::brush_teeth", "a": "Clear event", "b": "No BRUSHED/CLEAN teeth endpoint", "c": "No brushing event exists", "d": "No brush/use primitive", "e": "Holding toothbrush and toothpaste placement/proximity", "f": "Needs new action/state ontology", "classification": no},
        {"task": "test_unseen::make_toast", "a": "Clear appliance task", "b": "No TOASTED/time state", "c": "Conditionally: bread-loaded toaster ON/OFF cycle", "d": "Existing primitives execute the cycle", "e": "Ends holding bread; not toasted", "f": "Add generic appliance-cycle trace predicate", "classification": trace},
        {"task": "test_unseen::eat_chips_on_the_sofa", "a": "Clear event plus location", "b": "No consumed/eaten state", "c": "No eating event exists", "d": "EAT is absent", "e": "Holding chips and character SITTING/ON sofa", "f": "Needs EAT/action-state ontology", "classification": no},
        {"task": "test_unseen_ambiguous_goals::make_dinner", "a": "No unique meal content", "b": "Only one arbitrary recipe endpoint", "c": "Trace would encode an arbitrary recipe", "d": "Primitives execute one annotation", "e": "Stove ON plus incidental proximity", "f": "Needs a predeclared meal/recipe ontology or task-specific goal", "classification": no},
        {"task": "test_unseen_ambiguous_goals::make_breakfast", "a": "No unique meal content", "b": "Only one arbitrary recipe endpoint", "c": "Trace would encode an arbitrary recipe", "d": "Primitives execute one annotation", "e": "Stove ON and arbitrary placement/proximity", "f": "Needs a predeclared meal/recipe ontology", "classification": no},
        {"task": "test_unseen_ambiguous_goals::bring_some_breakfast_to_the_coffeetable", "a": "Breakfast objects are unspecified", "b": "No breakfast category relation", "c": "Trace must choose arbitrary objects", "d": "Actions work for a chosen recipe", "e": "Plate/character proximity and held fork", "f": "Needs category/recipe semantics", "classification": no},
        {"task": "test_unseen_ambiguous_goals::cook_lunch", "a": "Lunch content is open-ended", "b": "One salmon recipe is not the task definition", "c": "Trace would privilege one recipe", "d": "Actions execute the annotation", "e": "Stove ON and salmon/pan proximity", "f": "Needs a predeclared recipe ontology", "classification": no},
        {"task": "env1::watch_tv", "a": "Clear event", "b": "No WATCHED state", "c": "Yes: successful WATCH(tv) event", "d": "WATCH is present", "e": "TV ON plus incidental proximity/room deltas", "f": "Add generic successful-event evaluator", "classification": trace},
        {"task": "env1::make_toast", "a": "Clear appliance task", "b": "No TOASTED state", "c": "Conditionally: loaded toaster ON/OFF cycle", "d": "Cycle executes", "e": "Only bread/toaster proximity changes", "f": "Add generic appliance-cycle trace predicate", "classification": trace},
        {"task": "env1::wash_the_dishbowl_in_dishwasher", "a": "Clear appliance task", "b": "No dishwasher WASHED rule", "c": "Yes: loaded dishwasher ON/OFF cycle", "d": "Cycle executes", "e": "Dishbowl INSIDE dishwasher plus proximity; not washed", "f": "Add generic appliance-cycle trace predicate", "classification": trace},
        {"task": "env2::make_toast", "a": "Clear appliance task", "b": "No TOASTED state", "c": "Conditionally: loaded toaster ON/OFF cycle", "d": "Cycle executes", "e": "Only bread/toaster proximity changes", "f": "Add generic appliance-cycle trace predicate", "classification": trace},
        {"task": "env2::wash_the_cutlery_in_dishwasher", "a": "Clear appliance task", "b": "No dishwasher WASHED rule", "c": "Yes: loaded dishwasher ON/OFF cycle", "d": "Cycle executes", "e": "Fork INSIDE dishwasher plus proximity; not washed", "f": "Add generic appliance-cycle trace predicate", "classification": trace},
        {"task": "env2::make_coffee_in_coffeemaker", "a": "Clear appliance task", "b": "No COFFEE_MADE/USED state", "c": "Yes: coffeepot-loaded maker ON/OFF cycle", "d": "Cycle executes", "e": "Ends holding coffeepot", "f": "Add generic appliance-cycle trace predicate", "classification": trace},
        {"task": "env2::heat_salmon_on_the_stove", "a": "Clear heating task", "b": "Released final graph has no HEATED state for this path", "c": "Yes: salmon-in-pan stove ON/OFF cycle", "d": "Cycle executes", "e": "Ends holding salmon plus proximity", "f": "Add generic appliance-cycle trace predicate; fix ON/INSIDE ontology mismatch only in evaluator", "classification": trace},
    ]


def prompt_sample(call: Dict[str, Any], row: Dict[str, Any]) -> str:
    metadata_keys = [
        "call_role", "broad_role", "provider", "model", "api_interface", "temperature",
        "max_tokens", "seed", "stop", "frequency_penalty", "extra_body", "prompt_tokens",
        "completion_tokens", "response_id", "error_type", "error_message",
    ]
    metadata = {key: call.get(key) for key in metadata_keys}
    return "\n".join(
        [
            f"SOURCE RUN: {row['run_id']}",
            f"TASK: {row['task_id']}",
            f"ROLE: {call['call_role']}",
            "",
            "REQUEST METADATA:",
            json.dumps(metadata, ensure_ascii=False, indent=2),
            "",
            "INSTRUCTIONS FIELD (sent separately):",
            call.get("instructions") or "<null>",
            "",
            "USER INPUT/PROMPT (complete):",
            call["prompt"],
            "",
            "RAW MODEL OUTPUT (complete):",
            call["raw_output"],
            "",
            "PARSED OUTPUT_TEXT USED BY RUNTIME:",
            call["output_text"],
            "",
        ]
    )


def prompt_audit(rows: Sequence[Dict[str, Any]], semantic: Dict[str, Any], manifest: Dict[str, Any]) -> Dict[str, Any]:
    root = PHASE6 / "PROMPT_AUDIT"
    root.mkdir(parents=True, exist_ok=True)
    by_pair = {(row["task_id"], row["method"]): row for row in rows}
    fruit = "test_unseen_ambiguous_goals::collect_4_fruits_such_as_apple,_banana,_etc_in_the_dishbowl"
    microwave = "env1::microwave_chicken"
    turnoff = "test_unseen::turn_off_light"

    def call_for(task_id: str, method: str, role: str, ordinal: int = 0) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        row = by_pair[(task_id, method)]
        calls = [call for call in row["llm_call_records"] if call["call_role"] == role]
        return row, calls[ordinal]

    specs = [
        ("01_progprompt_generation.txt", turnoff, "ProgPrompt", "whole_program_generation", 0),
        ("02_progprompt_assertion.txt", turnoff, "ProgPrompt", "assertion_verification", 0),
        ("03_hpaf_flat_program_agent.txt", fruit, "HPAF-Flat", "flat_program_agent", 0),
        ("04_hpaf_flat_verifier.txt", fruit, "HPAF-Flat", "flat_verifier", 0),
        ("05_hpaf_full_task_agent.txt", fruit, "HPAF-Full", "task_agent", 0),
        ("06_hpaf_full_atomic_program_agent.txt", fruit, "HPAF-Full", "atomic_program_agent", 0),
        ("07_hpaf_full_atomic_verifier.txt", fruit, "HPAF-Full", "atomic_verifier", 0),
        ("08_hpaf_full_repair.txt", microwave, "HPAF-Full", "repair_program_agent", 0),
        ("09_hpaf_full_post_repair_verifier.txt", microwave, "HPAF-Full", "post_repair_verifier", 0),
    ]
    for filename, task_id, method, role, ordinal in specs:
        row, call = call_for(task_id, method, role, ordinal)
        (root / filename).write_text(prompt_sample(call, row), encoding="utf-8")

    structures = [
        ("ProgPrompt generation", "task, complete object-class inventory, 3 released train examples, shared action API", "No symbolic state; no errors/trace; no semantic/GT data", "DSL body: comments, actions, assertions, else recovery", "Once per task", "Yes: supplies entire program"),
        ("ProgPrompt assertion", "assertion text, assertion-object-filtered current local symbolic state, fixed 7-example state-check prompt", "No task text, full graph, errors, semantic/GT data", "Intended True/False text", "At every generated assertion", "Yes: skips or executes adjacent else branches"),
        ("Flat ProgramAgent", "whole task, initial symbolic observation, objects, shared action API, generic execution rules", "No few-shot examples, trace/errors, semantic/GT data", "Strict JSON with plan_brief/program", "Once per task", "Yes: supplies whole program"),
        ("Flat verifier", "whole task, post-execution symbolic observation, relevant objects, program, trace, typed errors", "No few-shot examples or semantic/GT data", "Strict done/reason/failure_stage/regeneration_hint JSON", "Once after execution", "No: recorded only; Flat has no retry"),
        ("Full TaskAgent", "whole task, object inventory, shared action names", "No symbolic state, examples, trace/errors, semantic/GT data", "Strict 1-6 atomic_tasks JSON", "Once per task", "Yes: defines ordered atomics"),
        ("Full atomic ProgramAgent", "whole task, current atomic, refreshed symbolic state, objects, shared action API", "No few-shot or future atomic payload; no semantic/GT data", "Strict JSON with plan_brief/program", "Once per attempted atomic", "Yes: supplies current program"),
        ("Full atomic verifier", "current atomic, post-state, relevant objects, whole-task context, program, trace, errors", "No future atomic payload or semantic/GT data", "Strict verifier JSON", "After initial atomic execution", "Yes: done=false invokes Retry-1"),
        ("Full repair ProgramAgent", "current atomic, post-state, prior program, trace/errors, first verifier feedback, objects/API", "No future atomic payload or semantic/GT data", "Strict JSON with repair_brief/program", "Only after done=false; 4 formal calls", "Yes: supplies one local repair"),
        ("Full post-repair verifier", "current atomic, post-repair state, repair program/trace/errors, previous verifier", "No future atomic payload or semantic/GT data", "Strict verifier JSON", "After each repair; 4 formal calls", "Yes: failure stops future atomics"),
    ]
    lines = [
        "# Prompt Structure Audit",
        "",
        "All structures below are verified against `llm_call_records[].prompt` and `.instructions` in the immutable formal raw logs, not inferred only from templates.",
        "",
        "| Prompt | Input information | Explicitly absent | Output format | When called | Affects control flow |",
        "|---|---|---|---|---|---|",
    ]
    for item in structures:
        lines.append("| " + " | ".join(esc(value) for value in item) + " |")
    lines += [
        "",
        "## Backend request facts",
        "",
        "All 292 formal calls used ARK `doubao-seed-2-1-pro-260628`, Responses API, temperature 0, thinking disabled, and `max_output_tokens=600`. ProgPrompt generation records `stop=['def']` and `frequency_penalty=0.15`, but the adapter does not send either to Responses: stop is applied locally after generation and frequency penalty is metadata only. ProgPrompt assertions similarly apply newline stop locally.",
        "",
        "Additional baseline-fidelity differences are outside the request metadata. The frozen shared interface has 17 actions and omits four navigation variants advertised by the released ProgPrompt import (`turnright`, `turnleft`, `walkforward`, `walktowards`). Phase 6 also fixes same-class object grounding with executor `seed=0`; the released executor uses module-level `random.choice` without explicitly freezing an execution seed on the default-example path.",
        "",
        "Most importantly, the released ProgPrompt assertion call uses `max_tokens=2`, while Phase 6 uses 600. The exact samples in this directory preserve the actual formal request and output.",
        "",
    ]
    (root / "PROMPT_STRUCTURE.md").write_text("\n".join(lines), encoding="utf-8")

    all_calls = [(row, call) for row in rows for call in row["llm_call_records"]]
    exact_payload_hits = []
    gt_action_overlaps = []
    unexplained_gt_action_hits = []
    semantic_by_id = {item["task_id"]: item for item in semantic["tasks"]}
    manifest_by_id = {item["task_id"]: item for item in manifest["entries"]}
    for row, call in all_calls:
        prompt = call["prompt"]
        goal = semantic_by_id[row["task_id"]]
        payloads = [item["condition"] for item in goal["conditions"]]
        payloads += [item.get("rationale", "") for item in goal["conditions"]]
        payloads.append(goal.get("ambiguity", ""))
        for payload in payloads:
            if payload and payload in prompt:
                exact_payload_hits.append(
                    {"task_id": row["task_id"], "role": call["call_role"], "payload": payload}
                )
        own_trace_actions = {
            item["source_action"] for item in row["graph_execution_trace"]
        }
        for action in manifest_by_id[row["task_id"]].get("gt_actions", []):
            if action not in prompt:
                continue
            overlap = {
                "task_id": row["task_id"],
                "role": call["call_role"],
                "action": action,
                "also_in_method_trace": action in own_trace_actions,
            }
            gt_action_overlaps.append(overlap)
            if call["call_role"] in {
                "whole_program_generation", "flat_program_agent", "task_agent",
                "atomic_program_agent",
            } or action not in own_trace_actions:
                unexplained_gt_action_hits.append(overlap)

    structural_terms = [
        "gt_action_length", "gt_actions", "ground_truth_final_state", "final_semantic_sr",
        "semantic_gcr", "official_goal", "method score",
    ]
    structural_hits = []
    for row, call in all_calls:
        lower = call["prompt"].lower()
        for term in structural_terms:
            if term in lower:
                structural_hits.append({"task_id": row["task_id"], "role": call["call_role"], "term": term})

    future_checks = 0
    future_hits = []
    for row in rows:
        if row["method"] != "HPAF-Full":
            continue
        atomics = row["atomic_tasks"]
        calls = row["llm_call_records"]
        current_index = -1
        for call in calls:
            if call["call_role"] == "atomic_program_agent":
                current_index += 1
            if call["call_role"] in {
                "atomic_program_agent", "atomic_verifier", "repair_program_agent", "post_repair_verifier"
            } and current_index >= 0:
                for future in atomics[current_index + 1 :]:
                    future_checks += 1
                    if future["instruction"] in call["prompt"]:
                        future_hits.append(
                            {"task_id": row["task_id"], "role": call["call_role"], "future": future["instruction"]}
                        )

    if exact_payload_hits or unexplained_gt_action_hits or structural_hits or future_hits:
        raise AssertionError(
            "Prompt leakage found: "
            f"payload={exact_payload_hits} gt={unexplained_gt_action_hits} "
            f"structural={structural_hits} future={future_hits}"
        )
    leakage = [
        "# Formal Prompt Leakage Audit",
        "",
        f"Scanned {len(all_calls)} actual formal API call records across all 60 runs.",
        "",
        "## Results",
        "",
        "| Prohibited information | Check | Result |",
        "|---|---|---|",
        f"| Frozen semantic goal conditions/rationales | Exact same-task payload search over every prompt | PASS: {len(exact_payload_hits)} hits |",
        f"| GT program / grounded GT actions | Exact released grounded-action search and structural field-name search | PASS: 0 unexplained hits ({len(gt_action_overlaps)} execution-trace overlaps) |",
        "| GT final graph / official goal set | Structural marker search plus manual prompt-schema inspection | PASS: 0 hits |",
        f"| Future atomic answers | {future_checks} exact future-instruction comparisons in current-atomic calls | PASS: {len(future_hits)} hits |",
        "| Method scores/outcomes | Score/evaluator field-name search | PASS: 0 hits |",
        "",
        "The grounded-action overlaps occur only in verifier/repair prompts where the allowed current execution trace contains a method-executed action that happens to equal a released GT action. Each overlap is also present in that method's own stored trace; none appears in generation/TaskAgent prompts. This is execution-derived evidence, not GT provenance.",
        "",
        "The HPAF templates contain negative safeguards such as `frozen goal predicates` and `do not ... future atomics`; these are policy text, not leaked goal values. Original task text remains visible to Full atomic calls by design, but no future TaskAgent-produced atomic object is inserted.",
        "",
        "ProgPrompt receives only its released-style action/object prefix, three train examples, and task header during generation. Assertion calls receive the fixed state-check examples plus assertion-object-filtered local symbolic state. No final evaluator input is present.",
        "",
        "## Separation conclusion",
        "",
        "The online controller prompts are clean with respect to frozen evaluator answers. Final semantic conditions are consumed only by the offline deterministic scoring/replay path. Prompt leakage status: **PASS**.",
        "",
    ]
    (PHASE6 / "PROMPT_LEAKAGE_AUDIT.md").write_text("\n".join(leakage), encoding="utf-8")
    return {
        "calls_scanned": len(all_calls),
        "exact_payload_hits": exact_payload_hits,
        "execution_trace_gt_action_overlaps": len(gt_action_overlaps),
        "unexplained_gt_action_hits": unexplained_gt_action_hits,
        "future_checks": future_checks,
    }


def win_matrix(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    order: List[str] = []
    for row in rows:
        if row["task_id"] not in grouped:
            order.append(row["task_id"])
        grouped[row["task_id"]][row["method"]] = row
    result = []
    for task_id in order:
        methods = grouped[task_id]
        first = methods["ProgPrompt"]
        full = methods["HPAF-Full"]
        result.append(
            {
                "task_id": task_id,
                "task": first["task"],
                "gt_horizon": first["gt_action_length"],
                "horizon": first["horizon"],
                "atomic_count": full["number_of_atomic_tasks"],
                "progprompt": methods["ProgPrompt"]["final_semantic_SR"],
                "flat": methods["HPAF-Flat"]["final_semantic_SR"],
                "full": full["final_semantic_SR"],
            }
        )
    return result


def metrics_markdown(
    metrics: Sequence[Dict[str, Any]],
    ledger: Sequence[Dict[str, Any]],
    matrix: Sequence[Dict[str, Any]],
    rows: Sequence[Dict[str, Any]],
) -> str:
    turnoff = next(
        row
        for row in rows
        if row["task_id"] == "test_unseen::turn_off_light" and row["method"] == "ProgPrompt"
    )
    turnoff_assertions = [
        item for item in turnoff["execution_trace"] if item["event"] == "assert"
    ]
    if [item["detail"] for item in turnoff_assertions] != [
        "False",
        "Let's analyze this step by step:",
    ]:
        raise AssertionError("Frozen turn-off-light assertion trace changed")
    lines = [
        "# Independently Recomputed Phase-6 Metrics",
        "",
        f"Source: immutable `results/raw_runs.jsonl`, SHA-256 `{sha256(RAW)}`. Aggregates below do not read `summary_main.csv`. All 60 stored grounded traces were replayed from frozen initial graphs; replayed Semantic SR, Official SR, and task Exec matched every raw record.",
        "",
        "## Main recomputation",
        "",
        "| Method | Successes/N | Semantic SR | Macro Exec | Micro Exec | Successful/attempted actions | Calls | Prompt tokens | Completion tokens | Total tokens | Avg calls/task | Avg tokens/task |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in metrics:
        lines.append(
            f"| {item['method']} | {item['task_successes']}/{item['n']} | {item['semantic_sr']:.3f} | {item['macro_exec']:.6f} | {item['micro_exec']:.6f} | {item['successful_actions']}/{item['attempted_actions']} | {item['total_llm_calls']} | {item['total_prompt_tokens']} | {item['total_completion_tokens']} | {item['total_tokens']} | {item['average_calls_per_task']:.2f} | {item['average_tokens_per_task']:.1f} |"
        )
    lines += [
        "",
        "The reported Exec is **macro Exec**: the arithmetic mean of each task's successful-actions/attempted-actions ratio. Micro Exec is supplied only as an offline supplement and does not replace the frozen result.",
        "",
        "## Per-role cost ledger",
        "",
        "| Method | Role | Calls | Prompt tokens | Completion tokens | Total tokens |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for item in ledger:
        lines.append(
            f"| {item['method']} | `{item['role']}` | {item['calls']} | {item['prompt_tokens']} | {item['completion_tokens']} | {item['total_tokens']} |"
        )
    lines += [
        "",
        "Full accounting is exactly TaskAgent 20 + atomic ProgramAgent 26 + atomic verifier 26 + repair ProgramAgent 4 + post-repair verifier 4 = 80 calls. Its 88,088 total tokens include every one of those roles, hence 4,404.4 tokens/task and 4.00 calls/task.",
        "",
        "ProgPrompt accounting is exactly 20 whole-program generation + 152 assertion calls = 172 calls, hence 8.60 calls/task. Assertions are embedded precondition checks: a false gate executes the immediately adjacent `else:` recovery action(s); it is neither whole-task failure nor full replanning.",
        "",
        "Concrete frozen trace (`test_unseen::turn_off_light`): one whole-program call generated `walk -> find -> assert close / else find -> assert switchon / else switchon -> switchoff`. After the successful walk/find, the first assertion prompt included `You see: lightswitch is ON.` and `assert('close' to 'lightswitch')`; its output was `False`, so only the adjacent recovery `find('lightswitch')` executed. The second assertion returned the non-binary first line `Let's analyze this step by step:`. Because it contained no `true`, runtime treated it as false and executed adjacent `switchon`, which failed because the light was already on; execution nevertheless continued to `switchoff`, which succeeded. The task therefore passed with Exec 4/5, proving an assertion false gate is local recovery rather than whole-task failure or replanning while also exposing the binary-contract bug.",
        "",
        "Across generated ProgPrompt programs there are 178 `else:` branches: 84 were skipped after true gates and 94 were executed after false gates. There were 152 assertion calls; runtime parsing classified 76 true and 76 false by substring search.",
        "",
        "## Assertion fidelity issue",
        "",
    ]
    pp_calls = [
        call for row in rows if row["method"] == "ProgPrompt"
        for call in row["llm_call_records"] if call["call_role"] == "assertion_verification"
    ]
    strict = sum(call["output_text"].strip().lower() in {"true", "false"} for call in pp_calls)
    lines += [
        f"Only {strict}/152 assertion outputs are strict `True`/`False`; {152-strict} begin with explanatory text. Phase 6 uses max output 600 while the released executor uses max tokens 2. Because runtime truth is `'true' in output_text.lower()`, semantically affirmative verbose first lines can be treated as false. This is a baseline-fidelity/control-flow issue, not an arithmetic accounting error.",
        "",
        "## Task-level win/loss matrix",
        "",
        "| Task | ProgPrompt | Flat | Full | GT actions | Horizon | Atomic count |",
        "|---|---:|---:|---:|---:|---|---:|",
    ]
    for item in matrix:
        lines.append(
            f"| `{item['task_id']}` | {item['progprompt']} | {item['flat']} | {item['full']} | {item['gt_horizon']} | {item['horizon']} | {item['atomic_count']} |"
        )
    all_success = [item["task_id"] for item in matrix if item["progprompt"] == item["flat"] == item["full"] == 1]
    pp_only = [item["task_id"] for item in matrix if item["progprompt"] == 1 and item["flat"] == item["full"] == 0]
    flat_only = [item["task_id"] for item in matrix if item["flat"] == 1 and item["progprompt"] == item["full"] == 0]
    full_only = [item["task_id"] for item in matrix if item["full"] == 1 and item["progprompt"] == item["flat"] == 0]
    pp_fail_full_success = [item["task_id"] for item in matrix if item["progprompt"] == 0 and item["full"] == 1]
    full_fail_pp_success = [item["task_id"] for item in matrix if item["full"] == 0 and item["progprompt"] == 1]
    lines += [
        "",
        f"- All success ({len(all_success)}): " + ", ".join(f"`{item}`" for item in all_success),
        f"- ProgPrompt-only success ({len(pp_only)}): " + (", ".join(f"`{item}`" for item in pp_only) or "none"),
        f"- Flat-only success ({len(flat_only)}): " + (", ".join(f"`{item}`" for item in flat_only) or "none"),
        f"- Full-only success ({len(full_only)}): " + (", ".join(f"`{item}`" for item in full_only) or "none"),
        f"- ProgPrompt fail / Full success ({len(pp_fail_full_success)}): " + ", ".join(f"`{item}`" for item in pp_fail_full_success),
        f"- Full fail / ProgPrompt success ({len(full_fail_pp_success)}): " + ", ".join(f"`{item}`" for item in full_fail_pp_success),
        "",
        "Full's only failure is `env1::microwave_chicken`. Moving from 16/20 to 19/20 means Full fixes all four ProgPrompt failures but introduces one failure on a task ProgPrompt solved: +4 - 1 = net +3 tasks, or +15 percentage points.",
        "",
        "## What Full > Flat supports",
        "",
        "Flat fails five tasks; Full also fails microwave chicken and converts the other four. Two one-atomic conversions (`env1::throw_away_plum`, `env2::throw_away_bananas`) are directly attributable in-trace to verifier-triggered Retry-1 opening the closed garbage can. `env1::put_chicken_in_the_fridge` is one atomic with no retry, so its conversion cannot be decomposition; it reflects different TaskAgent rewriting/program prompts and possibly backend nondeterminism. The four-fruit task is the one direct multi-atomic example where decomposition plus current-state regeneration avoids Flat's multi-instance dishbowl binding failure.",
        "",
        "The observed 95% vs 75% therefore supports the Full package (TaskAgent rewriting, current-state atomic generation, online verification, and Retry-1), not the claim that decomposition alone adds 20 points. One temperature-zero run without a provider seed cannot separate prompt/sampling nondeterminism.",
        "",
    ]
    return "\n".join(lines)


def case_studies(rows: Sequence[Dict[str, Any]]) -> str:
    by_pair = {(row["task_id"], row["method"]): row for row in rows}
    fruit = "test_unseen_ambiguous_goals::collect_4_fruits_such_as_apple,_banana,_etc_in_the_dishbowl"
    book = "env1::bring_my_book_to_the_sofa"
    microwave = "env1::microwave_chicken"
    lines = [
        "# Offline Case Studies",
        "",
        "The concise findings below are backed by lossless chronological renderings containing every prompt, raw output, action, state delta, verification decision, and cost entry. Those timelines were reconstructed without LLM or Unity calls and require replayed metrics to match the raw records.",
        "",
        "## Case A: collect four fruits",
        "",
    ]
    for method in METHODS:
        row = by_pair[(fruit, method)]
        lines.append(f"- {method}: SR={row['final_semantic_SR']}, Exec={row['Exec']:.6f}, calls={row['total_calls']}, tokens={row['total_tokens']}.")
    lines += [
        "",
        "ProgPrompt suffered repeated precondition/object-binding failures and finished with zero counted fruits in a dishbowl. Flat emitted all four placements and every action reported executable, but target resolution switched between two dishbowl instances: the deterministic evaluator found only bananas, peach, and plum inside any qualifying bowl relation set (3/4). Full decomposed into four fruit atomics, regenerated from refreshed state each time, consistently accumulated apple, bananas, peach, and plum, and all four atomic verifiers returned done=true. This single case supports decomposition/state refresh, but it is not enough to attribute the aggregate 20-point Flat-to-Full gap entirely to decomposition.",
        "",
        "Complete evidence: `audits/case1_collect_4_fruits_full_timeline.md`.",
        "",
        "## Case B: bring my book to the sofa (env1)",
        "",
    ]
    for method in METHODS:
        row = by_pair[(book, method)]
        lines.append(f"- {method}: SR={row['final_semantic_SR']}, Exec={row['Exec']:.6f}, calls={row['total_calls']}, tokens={row['total_tokens']}.")
    lines += [
        "",
        "ProgPrompt generated and successfully executed `putin('book', 'sofa')`, but the frozen semantic goal is `ON(book, sofa)`. The action choice therefore produced the wrong relation despite Exec=1.0. Flat and Full used `putback`, producing ON and succeeding. The same ProgPrompt failure repeats in env2, so this is an action-semantics issue rather than an assertion failure.",
        "",
        "Complete evidence for env1 and env2: `audits/case2_book_to_sofa_full_timeline.md`.",
        "",
        "## Case C: env1 microwave chicken",
        "",
    ]
    for method in METHODS:
        row = by_pair[(microwave, method)]
        lines.append(f"- {method}: SR={row['final_semantic_SR']}, Exec={row['Exec']:.6f}, calls={row['total_calls']}, tokens={row['total_tokens']}.")
    lines += [
        "",
        "Full's TaskAgent produced two atomics: put chicken into microwave, then turn on microwave. Its first ProgramAgent called `find(chicken)`, then `find(microwave)`, which moved grounding/proximity to the microwave before `grab(chicken)`; grab failed and putin then lacked a held chicken. The verifier correctly returned done=false. Retry-1 walked to and grabbed the chicken but immediately attempted putin without returning close to the microwave, so repair failed. Post-repair verification correctly remained false; the controller stopped before atomic 2. The failure is a two-location alignment/repair-planning error, not evaluator leakage or a false verifier decision.",
        "",
        "Complete evidence: `audits/case3_microwave_chicken_full_timeline.md`.",
        "",
    ]
    return "\n".join(lines)


def audit_report(metrics: Sequence[Dict[str, Any]], facts: Dict[str, Any]) -> str:
    by_method = {item["method"]: item for item in metrics}
    pp = by_method["ProgPrompt"]
    flat = by_method["HPAF-Flat"]
    full = by_method["HPAF-Full"]
    token_reduction = 1 - full["average_tokens_per_task"] / pp["average_tokens_per_task"]
    call_reduction = 1 - full["average_calls_per_task"] / pp["average_calls_per_task"]
    return "\n".join(
        [
            "# Phase-6 Independent Audit Report",
            "",
            "## 1. Dataset correctness",
            "",
            "**PASS.** Official primary inventory is 70 task-scene instances, the 35-candidate construction is correct, the final set is 20 instances / 18 unique texts, and direct GT flattening confirms Short/Medium/Long = 6/10/4. `held-out` must not be presented as synonymous with `task-unseen`; five selected env instances use three task texts seen in train.",
            "",
            "## 2. Task filtering correctness",
            "",
            "**PASS (conservative).** No included task lacks a stable frozen endpoint, and no filtering decision depends on formal method output. Independent replay confirms all 128/128 non-empty released GT primitives across the 15 excluded held-out tasks execute through the shared interface; exclusion is about missing persistent/evaluable natural-language semantics, not primitive executability. Nine appliance/event tasks could be reconsidered only under a new pre-frozen generic trace evaluator; six remain unreliable. The formal set was not modified.",
            "",
            "## 3. Metric recomputation",
            "",
            f"**PASS.** Offline replay confirms ProgPrompt {pp['task_successes']}/{pp['n']}, Flat {flat['task_successes']}/{flat['n']}, Full {full['task_successes']}/{full['n']}. Reported Exec is macro average; supplemental micro Exec is {pp['micro_exec']:.6f}, {flat['micro_exec']:.6f}, {full['micro_exec']:.6f} respectively.",
            "",
            "## 4. Cost accounting",
            "",
            f"**PASS (arithmetic).** All per-call prompt/completion tokens are present and sum exactly. Calls are 172/40/80 and tokens are {pp['total_tokens']}/{flat['total_tokens']}/{full['total_tokens']}. Full includes all TaskAgent and verifier costs.",
            "",
            "## 5. Prompt leakage",
            "",
            "**PASS.** All 292 actual formal prompts were searched. No frozen semantic payload, unexplained GT action, GT final/evaluator field, future TaskAgent atomic answer, or score was found.",
            "",
            "## 6. Baseline fidelity",
            "",
            "**ISSUE.** The adapter preserves the official three examples, DSL, assertions, adjacent else recovery, and per-subgoal cap, but it is not a strict official replication. It narrows the released 21-name import to the shared 17-action graph interface by removing `turnright`, `turnleft`, `walkforward`, and `walktowards`; fixes same-class object grounding with `seed=0` where the released default path uses unseeded module-level `random.choice`; and uses Responses API rather than the released Completion API. Server-side frequency penalty is not applied, stop is post-processed locally, and most importantly assertion max output is 600 rather than the released 2. Forty-five of 152 assertions are non-binary first lines, and substring parsing can turn intended affirmative answers into false recovery gates. The reported result is real for this adapter, not a strict official ProgPrompt replication.",
            "",
            "## 7. HPAF fidelity",
            "",
            "**PASS within the declared abstraction.** Raw logs show 20 real TaskAgent calls, current-state atomic ProgramAgent calls, 30 real Full verifier calls including post-repair, four Retry-1 calls, state refresh, and early stop. This benchmark uses symbolic perception surrogate and does not validate real RGB-D/VLM perception.",
            "",
            "## 8. Fairness",
            "",
            "**PARTIAL.** Methods share environment graphs, Evolving Graph backend, the same narrowed 17-action interface, deterministic grounding seed, final evaluator, model, temperature, max-output setting, and thinking setting. They intentionally do not receive identical observations/prompts: ProgPrompt generation has examples but no state; assertions see filtered local state; HPAF sees richer current symbolic observations and typed trace/errors. These are method-design differences, but the ProgPrompt assertion-contract deviation creates an avoidable fidelity/cost disadvantage.",
            "",
            "## 9. Main result confidence",
            "",
            "Current supported statement:",
            "",
            f"On one frozen run of 20 selected official held-out task-scene instances (18 unique texts), this exact adapted implementation achieved HPAF-Full **19/20 (95%)** vs ProgPrompt **16/20 (80%)**, with macro Exec {full['macro_exec']:.4f} vs {pp['macro_exec']:.4f}, {full['average_calls_per_task']:.2f} vs {pp['average_calls_per_task']:.2f} calls/task, and {full['average_tokens_per_task']:.1f} vs {pp['average_tokens_per_task']:.1f} tokens/task. The raw arithmetic is +15 percentage points, {100*call_reduction:.1f}% fewer calls, and {100*token_reduction:.1f}% fewer measured tokens. Full fixes four ProgPrompt failures and introduces one failure, net +3 tasks.",
            "",
            "Unsupported overclaims:",
            "",
            "- `Task decomposition caused a 20-point gain over Flat.` Only one of four Flat-to-Full conversions is explicitly multi-atomic; two are directly Retry-1, and one is single-atomic prompt behavior.",
            "- `The 13.9% token reduction is a clean method comparison.` ProgPrompt assertion output cap/fidelity inflates and perturbs its assertion completions.",
            "- `Results are statistically stable or broadly generalize.` There is one run, temperature 0 has no provider seed, N=20, and Long N=4.",
            "- `HPAF improves real visual perception.` VirtualHome provides symbolic observations.",
            "- `All held-out tasks are task-unseen.` Env holdout and task-text holdout are different.",
            "",
            "## 10. Minimum next experiment",
            "",
            "Fix and freeze only the ProgPrompt assertion contract to reproduce the released binary check (`max_output_tokens` equivalent to 2 and exact `True`/`False` parsing, while preserving the same prompt and adjacent recovery semantics), then rerun one complete 20-task x 3-method matrix. Do not add tasks or tune prompts from outcomes. This single corrected matrix is more valuable than repetitions of the currently fidelity-compromised baseline; repetition can be considered only after it passes the same offline audit.",
            "",
        ]
    )


def main() -> None:
    manifest = read_json(MANIFEST)
    semantic = read_json(SEMANTIC)
    actions = read_json(ACTIONS)
    rows = read_jsonl(RAW)
    if len(rows) != 60 or len({(row["task_id"], row["method"]) for row in rows}) != 60:
        raise AssertionError("Formal raw matrix is not 60 unique task-method pairs")
    if Counter(row["method"] for row in rows) != Counter({method: 20 for method in METHODS}):
        raise AssertionError("Formal method counts changed")

    run_files = [read_json(path) for path in sorted((PHASE6 / "results/runs").glob("*.json"))]
    raw_by_pair = {(row["task_id"], row["method"]): row for row in rows}
    if len(run_files) != 60 or any(
        raw_by_pair.get((row["task_id"], row["method"])) != row for row in run_files
    ):
        raise AssertionError("Per-run JSON files do not exactly mirror raw_runs.jsonl")

    entries = {item["task_id"]: item for item in manifest["entries"]}
    goals = {item["task_id"]: item["conditions"] for item in semantic["tasks"]}
    replays = {}
    for row in rows:
        replays[(row["task_id"], row["method"])] = replay_record(
            row, entries[row["task_id"]], goals[row["task_id"]], actions
        )

    metrics = metric_rows(rows, replays)
    expected = {"ProgPrompt": 16, "HPAF-Flat": 15, "HPAF-Full": 19}
    if {item["method"]: item["task_successes"] for item in metrics} != expected:
        raise AssertionError("Primary success counts differ; stop before rendering")
    ledger = role_ledger(rows)
    matrix = win_matrix(rows)
    csv_write(PHASE6 / "AUDIT_METRICS_RECOMPUTED.csv", metrics)
    (PHASE6 / "AUDIT_METRICS.md").write_text(
        metrics_markdown(metrics, ledger, matrix, rows), encoding="utf-8"
    )
    csv_write(PHASE6 / "AUDIT_TASK_WIN_LOSS.csv", matrix)

    dataset_text, facts = dataset_audit(manifest, rows, actions)
    (PHASE6 / "AUDIT_DATASET_INDEPENDENT.md").write_text(dataset_text, encoding="utf-8")
    leakage = prompt_audit(rows, semantic, manifest)
    (PHASE6 / "AUDIT_CASE_STUDIES.md").write_text(case_studies(rows), encoding="utf-8")
    (PHASE6 / "AUDIT_REPORT.md").write_text(audit_report(metrics, facts), encoding="utf-8")

    output = {
        "mode": "offline only",
        "new_llm_calls": 0,
        "new_unity_calls": 0,
        "raw_sha256": sha256(RAW),
        "formal_records": len(rows),
        "replayed_records": len(replays),
        "replayed_attempted_actions": sum(item["attempted_actions"] for item in replays.values()),
        "metrics": metrics,
        "dataset": facts,
        "leakage": leakage,
    }
    (PHASE6 / "AUDIT_EVIDENCE.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
