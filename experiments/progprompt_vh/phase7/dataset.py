"""Phase-7 frozen regression/confirmatory manifests and provenance."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import ordered_annotation_rows


PHASE7_ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase7"
PHASE6_ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase6"
P6_MANIFEST = PHASE6_ROOT / "data/task_manifest.json"
RELEASE = PROJECT_ROOT / "third_party/progprompt-vh"

RESTORED_IDS = [
    "test_unseen::watch_tv",
    "test_unseen::make_toast",
    "env1::watch_tv",
    "env1::make_toast",
    "env1::wash_the_dishbowl_in_dishwasher",
    "env2::make_toast",
    "env2::wash_the_cutlery_in_dishwasher",
    "env2::make_coffee_in_coffeemaker",
    "env2::heat_salmon_on_the_stove",
]

TRACE_GOALS: Dict[str, Dict[str, Any]] = {
    "test_unseen::watch_tv": {
        "kind": "SUCCESSFUL_EVENT", "object": "tv", "actions": ["watch"],
        "rationale": "Natural-language completion requires a successful WATCH event; switching the TV on alone is insufficient and the graph has no WATCHED state.",
    },
    "test_unseen::make_toast": {
        "kind": "SUCCESSFUL_APPLIANCE_CYCLE", "item": "breadslice", "appliance": "toaster",
        "controller": "toaster", "load_required": True,
        "rationale": "A generic loaded-appliance ON->OFF cycle is the only stable simulator event surrogate.",
    },
    "env1::watch_tv": {
        "kind": "SUCCESSFUL_EVENT", "object": "tv", "actions": ["watch"],
        "rationale": "Natural-language completion requires a successful WATCH event; switching the TV on alone is insufficient and the graph has no WATCHED state.",
    },
    "env1::make_toast": {
        "kind": "SUCCESSFUL_APPLIANCE_CYCLE", "item": "breadslice", "appliance": "toaster",
        "controller": "toaster", "load_required": True,
        "rationale": "A generic loaded-appliance ON->OFF cycle is the only stable simulator event surrogate.",
    },
    "env1::wash_the_dishbowl_in_dishwasher": {
        "kind": "SUCCESSFUL_APPLIANCE_CYCLE", "item": "dishbowl", "appliance": "dishwasher",
        "controller": "dishwasher", "load_required": True,
        "rationale": "The released path has a loaded dishwasher ON->OFF cycle but no persistent WASHED rule.",
    },
    "env2::make_toast": {
        "kind": "SUCCESSFUL_APPLIANCE_CYCLE", "item": "breadslice", "appliance": "toaster",
        "controller": "toaster", "load_required": True,
        "rationale": "A generic loaded-appliance ON->OFF cycle is the only stable simulator event surrogate.",
    },
    "env2::wash_the_cutlery_in_dishwasher": {
        "kind": "SUCCESSFUL_APPLIANCE_CYCLE", "item": "cutleryfork", "appliance": "dishwasher",
        "controller": "dishwasher", "load_required": True,
        "rationale": "The released path has a loaded dishwasher ON->OFF cycle but no persistent WASHED rule.",
    },
    "env2::make_coffee_in_coffeemaker": {
        "kind": "SUCCESSFUL_APPLIANCE_CYCLE", "item": "coffeepot", "appliance": "coffeemaker",
        "controller": "coffeemaker", "load_required": False, "require_initial_association": True,
        "output_object": "coffeepot",
        "rationale": "The released path exposes a coffeemaker ON->OFF cycle and a post-cycle coffeepot interaction.",
    },
    "env2::heat_salmon_on_the_stove": {
        "kind": "SUCCESSFUL_APPLIANCE_CYCLE", "item": "salmon", "appliance": "fryingpan",
        "controller": "stove", "load_required": True,
        "rationale": "The released path exposes source loading into a pan followed by a stove ON->OFF cycle.",
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _proxy_goal(task_id: str) -> Dict[str, Any]:
    # The Phase-6 runner expects a condition while constructing its record. The
    # Phase-7 post-run scorer replaces this proxy with TRACE_GOALS and never
    # exposes it to an online prompt.
    return {
        "conditions": [{
            "condition": "STATE(character, PHASE7_TRACE_PROXY)",
            "predicate": "STATE", "object": "character", "value": "PHASE7_TRACE_PROXY",
            "rationale": "Internal runner placeholder; final Phase-7 score is the frozen trace predicate.",
        }],
        "ambiguity": "Trace-evaluated task; proxy is never used as the reported score.",
    }


def build_manifests() -> Dict[str, Any]:
    p6 = json.loads(P6_MANIFEST.read_text(encoding="utf-8"))
    entries_by_id = {item["task_id"]: item for item in p6["entries"]}
    regression_ids = [item["task_id"] for item in p6["entries"] if item["filter_status"] == "included"]
    if len(regression_ids) != 20:
        raise RuntimeError("Phase-6 regression set is not exactly 20 tasks")
    if set(RESTORED_IDS) & set(regression_ids):
        raise RuntimeError("Confirmatory task overlaps regression task-scene instance")

    train_text = {task for task, _source, _subgoals in ordered_annotation_rows("train")}
    candidates = []
    for task_id in RESTORED_IDS:
        if task_id not in entries_by_id or entries_by_id[task_id]["filter_status"] != "excluded_unrepresentable":
            raise RuntimeError(f"Restored candidate not present in Phase-6 excluded inventory: {task_id}")
        source = entries_by_id[task_id]
        if source["task_text"] in train_text:
            raise RuntimeError(f"Restored task text is train-seen: {task_id}")
        item = dict(source)
        item.update({
            "set": "confirmatory",
            "evaluator_type": "generic_trace",
            "trace_goal": TRACE_GOALS[task_id],
            "semantic_goal": _proxy_goal(task_id),
            "include_reason": "Pre-frozen official held-out candidate classified SAFE_TO_INCLUDE_WITH_GENERIC_TRACE_EVALUATOR in Phase-6 audit; restored before any Phase-7 method run.",
        })
        candidates.append(item)

    regression = []
    for task_id in regression_ids:
        item = dict(entries_by_id[task_id])
        item.update({
            "set": "regression",
            "evaluator_type": "persistent_state",
            "include_reason": "Original Phase-6 selected task; regression/development set because its outputs informed Phase-7 prompt design.",
        })
        regression.append(item)
    combined = regression + candidates

    for name, rows in [("regression", regression), ("confirmatory", candidates), ("combined", combined)]:
        path = PHASE7_ROOT / "data" / f"{name}_manifest.json"
        payload = {
            "schema_version": 1,
            "set": name,
            "frozen_before_formal_execution": True,
            "source": "ProgPrompt/VirtualHome pinned release plus Phase-6 frozen manifest",
            "entries": rows,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    all_tasks = [*regression, *candidates]
    task_texts = {item["task_text"] for item in all_tasks}
    task_unseen_instances = [item for item in all_tasks if item["task_text"] not in train_text]
    env_instances = [item for item in all_tasks if item["official_split"] in {"env1", "env2"}]
    stats = {
        "regression_n": len(regression),
        "confirmatory_n": len(candidates),
        "combined_n": len(combined),
        "combined_unique_task_texts": len(task_texts),
        "task_unseen_instances": len(task_unseen_instances),
        "task_unseen_unique_texts": len({item["task_text"] for item in task_unseen_instances}),
        "environment_held_out_instances": len(env_instances),
        "persistent_state_evaluated": sum(item["evaluator_type"] == "persistent_state" for item in all_tasks),
        "trace_evaluated": sum(item["evaluator_type"] == "generic_trace" for item in all_tasks),
        "synthetic": 0,
        "horizons": dict(Counter(item["horizon"] for item in all_tasks)),
        "sources": dict(Counter(item["official_split"] for item in all_tasks)),
    }
    (PHASE7_ROOT / "data" / "dataset_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"regression": regression, "confirmatory": candidates, "combined": combined, "stats": stats}


def write_expansion_audit(data: Dict[str, Any]) -> None:
    lines = [
        "# Phase-7 Dataset Expansion Audit", "",
        "Task selection was frozen from the Phase-6 independent audit before any Phase-7 method execution. No task was selected using Phase-7 output.", "",
        "## Restored official trace-evaluable candidates", "",
        "| Source file | Official split/source | Task text | Scene | GT length | Evaluator | Inclusion reason |", "|---|---|---|---:|---:|---|---|",
    ]
    for item in data["confirmatory"]:
        lines.append(
            f"| `{item['source_annotation']}` | `{item['official_split']}` | {item['task_text']} | {item['scene']} | {item['gt_action_length']} | `generic_trace/{item['trace_goal']['kind']}` | {item['include_reason']} |"
        )
    lines += [
        "", "## Rejected official candidates", "",
        "The other six Phase-6 excluded candidates remain out of the confirmatory set: `brush teeth`, `eat chips on the sofa`, `make dinner`, `make breakfast`, `bring some breakfast to the coffeetable`, and `cook lunch`. They lack a unique method-independent persistent or generic trace endpoint under the pinned action/state ontology. No synthetic tasks were added.",
        "", "## Set accounting", "",
        f"- Regression: {data['stats']['regression_n']} task-scene instances.",
        f"- Confirmatory: {data['stats']['confirmatory_n']} task-scene instances.",
        f"- Combined: {data['stats']['combined_n']} task-scene instances / {data['stats']['combined_unique_task_texts']} unique task texts.",
        f"- Persistent-state evaluated: {data['stats']['persistent_state_evaluated']}; generic trace evaluated: {data['stats']['trace_evaluated']}; synthetic: 0.",
    ]
    (PHASE7_ROOT / "DATASET_EXPANSION_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_expansion_audit(build_manifests())
