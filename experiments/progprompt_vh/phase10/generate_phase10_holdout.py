"""Deterministically generate the pre-frozen Phase-10 causal holdout.

Selection uses only official-scene inventory, semantic templates, feasibility,
declared complexity/quota constraints, and the method-independent evaluator.
No method output is read.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import graph_sha256, sha256
from experiments.progprompt_vh.phase9.scripts import generate_long_horizon_extension as p9
from experiments.progprompt_vh.phase10.verification.partial_order_evaluator import (
    evaluate_partial_order_goal,
    phase9_goal_to_partial_order,
)


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase10"
MANIFEST_PATH = ROOT / "PHASE10_FINAL_HOLDOUT_MANIFEST.json"
MANIFEST_SHA_PATH = ROOT / "PHASE10_FINAL_HOLDOUT_MANIFEST.sha256"
FINAL_STATES_PATH = ROOT / "data/holdout_reference_final_states.jsonl"
AUDIT_PATH = ROOT / "HOLDOUT_GENERATION_AUDIT.json"
METHOD_FREEZE = ROOT / "PHASE10_METHOD_FREEZE.json"
SEED = 20260827

CATEGORIES = [
    "container_state_transfer",
    "appliance_lifecycle",
    "causal_multi_object",
    "cross_location_mixed",
]
SLOTS = [(scene, category) for scene in (0, 1, 2) for category in CATEGORIES]
CATEGORY_LABELS = {
    "container_state_transfer": "A_container_intermediate_state_transfer",
    "appliance_lifecycle": "B_appliance_process_downstream_transfer",
    "causal_multi_object": "C_causal_multi_object_shared_state",
    "cross_location_mixed": "D_cross_location_causal",
}


def _candidate_order(scene: int, category: str, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = list(rows)
    random.Random(f"{SEED}:{scene}:{category}").shuffle(ordered)
    return ordered


def _prior_texts() -> Tuple[set[str], List[str]]:
    corpus, sources = p9._leakage_corpus()
    phase9_long = PROJECT_ROOT / "experiments/progprompt_vh/phase9/data/long11_manifest.json"
    payload = json.loads(phase9_long.read_text(encoding="utf-8"))
    corpus.update(item["task_text"].strip().lower() for item in payload["entries"])
    return corpus, [*sources, str(phase9_long.relative_to(PROJECT_ROOT))]


def _terminal_ir(condition: Mapping[str, Any]) -> Dict[str, Any]:
    result = {
        key: value
        for key, value in condition.items()
        if key in {"predicate", "object", "value", "subject", "relation"}
    }
    result["semantic_goal"] = f"Task must end with {condition['condition']}."
    return result


def _gold_atomic_ir(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    category = candidate["category"]
    stages = candidate["causal_stages"]
    terminal_conditions = [
        item
        for item in candidate["causal_goal"]["final_conditions"]
        if item["predicate"] == "STATE"
    ]
    if category == "container_state_transfer":
        source = stages[0]["event"]["first"]
        intermediate = stages[0]["event"]["second"]
        target = stages[4]["event"]["second"]
        atomics = [
            {
                "id": "A1", "type": "TRANSFER", "focal_object": source,
                "source": None, "target": intermediate, "completion_mode": "state",
                "semantic_goal": f"Temporarily store {source} in {intermediate}.", "depends_on": [],
            },
            {
                "id": "A2", "type": "TRANSFER", "focal_object": source,
                "source": intermediate, "target": target, "completion_mode": "state",
                "semantic_goal": f"Transfer {source} from {intermediate} to {target}.", "depends_on": ["A1"],
            },
        ]
    elif category == "appliance_lifecycle":
        source = stages[0]["event"]["first"]
        appliance = stages[0]["event"]["second"]
        destination = stages[-1]["event"]["second"]
        atomics = [
            {
                "id": "A1", "type": "PROCESS", "focal_object": source,
                "source": None, "target": appliance, "completion_mode": "process",
                "semantic_goal": f"Complete the requested {appliance} process for {source}.", "depends_on": [],
            },
            {
                "id": "A2", "type": "TRANSFER", "focal_object": source,
                "source": appliance, "target": destination, "completion_mode": "state",
                "semantic_goal": f"Place processed {source} on {destination}.", "depends_on": ["A1"],
            },
        ]
    elif category == "causal_multi_object":
        first = stages[0]["event"]["first"]
        second = stages[1]["event"]["first"]
        container = stages[0]["event"]["second"]
        destination = stages[-1]["event"]["second"]
        atomics = [
            {
                "id": "A1", "type": "MULTI_OBJECT_COUPLED", "focal_object": first,
                "source": None, "target": container, "completion_mode": "state",
                "semantic_goal": f"Stage {first} and {second} together in {container}.", "depends_on": [],
            },
            {
                "id": "A2", "type": "TRANSFER", "focal_object": second,
                "source": container, "target": destination, "completion_mode": "state",
                "semantic_goal": f"Leave {first} stored and deliver {second} to {destination}.", "depends_on": ["A1"],
            },
        ]
    else:
        source = stages[0]["event"]["first"]
        waypoint = stages[0]["event"]["second"]
        intermediate = stages[1]["event"]["second"]
        destination = stages[-1]["event"]["second"]
        atomics = [
            {
                "id": "A1", "type": "TRANSFER", "focal_object": source,
                "source": None, "target": waypoint, "completion_mode": "state",
                "semantic_goal": f"Stage {source} at {waypoint}.", "depends_on": [],
            },
            {
                "id": "A2", "type": "TRANSFER", "focal_object": source,
                "source": waypoint, "target": intermediate, "completion_mode": "state",
                "semantic_goal": f"Temporarily store {source} in {intermediate}.", "depends_on": ["A1"],
            },
            {
                "id": "A3", "type": "TRANSFER", "focal_object": source,
                "source": intermediate, "target": destination, "completion_mode": "state",
                "semantic_goal": f"Deliver {source} to {destination}.", "depends_on": ["A2"],
            },
        ]
    return {
        "atomic_tasks": atomics,
        "terminal_constraints": [_terminal_ir(item) for item in terminal_conditions],
    }


def _metrics(candidate: Mapping[str, Any], gold_ir: Mapping[str, Any]) -> Dict[str, int]:
    atomics = gold_ir["atomic_tasks"]
    parents = {item["id"]: item["depends_on"] for item in atomics}
    memo: Dict[str, int] = {}

    def depth(node: str) -> int:
        if node not in memo:
            memo[node] = 1 + max((depth(parent) for parent in parents[node]), default=0)
        return memo[node]

    category = candidate["category"]
    return {
        "semantic_atomic_count": len(atomics),
        "dependency_depth": max(depth(item["id"]) for item in atomics),
        "process_atomic_count": sum(item["type"] == "PROCESS" for item in atomics),
        "cross_object_transition_count": 2 if category == "cross_location_mixed" else 1,
        "cross_location_transition_count": max(len(set(candidate["rooms_involved"])) - 1, 0),
    }


def build() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    actions = json.loads(p9.ACTION_PATH.read_text(encoding="utf-8"))
    prior, prior_sources = _prior_texts()
    selected: List[Dict[str, Any]] = []
    final_states: List[Dict[str, Any]] = []
    attempts: Dict[str, int] = {}
    seen: set[str] = set()

    for scene, category in SLOTS:
        graph = p9._load_graph(scene)
        candidates = _candidate_order(scene, category, p9.CANDIDATE_BUILDERS[category](scene, graph))
        accepted = None
        for attempt, candidate in enumerate(candidates, 1):
            key = candidate["instruction"].strip().lower()
            if key in prior or key in seen:
                continue
            feasible, reference = p9._execute_reference(graph, candidate, actions)
            length = len(reference["trace"])
            if not feasible or length < 10:
                continue
            gold_ir = _gold_atomic_ir(candidate)
            metrics = _metrics(candidate, gold_ir)
            if metrics["semantic_atomic_count"] < 2 or metrics["dependency_depth"] < 2:
                continue
            gold = phase9_goal_to_partial_order(candidate["causal_goal"], category)
            score = evaluate_partial_order_goal(
                {"graph_execution_trace": reference["trace"]}, gold, reference["final_state"]
            )
            if not score["final_semantic_SR"] or not gold["required_dependency_edges"]:
                continue
            accepted = {
                **candidate,
                "reference": reference,
                "reference_horizon": length,
                "gold_semantics": gold,
                "gold_atomic_ir": gold_ir,
                **metrics,
            }
            attempts[f"scene{scene}:{category}"] = attempt
            break
        if accepted is None:
            raise RuntimeError(f"No first-valid Phase-10 candidate for scene={scene}/{category}")
        seen.add(accepted["instruction"].strip().lower())
        final_states.append(accepted["reference"]["final_state"])
        selected.append(accepted)

    entries: List[Dict[str, Any]] = []
    category_ordinals = Counter()
    for item, final_graph in zip(selected, final_states):
        category_ordinals[item["category"]] += 1
        short = {
            "container_state_transfer": "container",
            "appliance_lifecycle": "process",
            "causal_multi_object": "coupled",
            "cross_location_mixed": "crossloc",
        }[item["category"]]
        reference = item.pop("reference")
        task_id = f"p10_s{item['scene']}_{short}_{category_ordinals[item['category']]}"
        entries.append(
            {
                "task_id": task_id,
                "task_text": item.pop("instruction"),
                "instruction": None,
                "scene": item["scene"],
                "category": item["category"],
                "category_label": CATEGORY_LABELS[item["category"]],
                "source": "phase10_deterministic_semantic_template_on_official_scene",
                "synthetic": True,
                "official_or_extension": "synthetic_causal_holdout",
                "official_split": "phase10_final_holdout",
                "horizon": "Long",
                "is_long_horizon": True,
                "initial_state_source": p9.SCENES[item["scene"]]["source"],
                "initial_state_index": p9.SCENES[item["scene"]]["index"],
                "initial_state_sha256": graph_sha256(p9._load_graph(item["scene"])),
                "reference_program": item["reference_program"],
                "reference_action_sequence": reference["compiled_actions"],
                "reference_trace": reference["trace"],
                "reference_horizon": item["reference_horizon"],
                "reference_final_state_source": str(FINAL_STATES_PATH.relative_to(PROJECT_ROOT)),
                "reference_final_state_index": len(entries),
                "reference_final_state_sha256": graph_sha256(final_graph),
                "reference_feasibility": {
                    "all_actions_executable": reference["all_actions_executable"],
                    "partial_order_evaluator_success": True,
                },
                "evaluator_type": "semantic_partial_order",
                "gold_semantics": item["gold_semantics"],
                "gold_atomic_ir": item["gold_atomic_ir"],
                "semantic_atomic_count": item["semantic_atomic_count"],
                "dependency_depth": item["dependency_depth"],
                "process_atomic_count": item["process_atomic_count"],
                "cross_object_transition_count": item["cross_object_transition_count"],
                "cross_location_transition_count": item["cross_location_transition_count"],
                "rooms_involved": item["rooms_involved"],
                "method_output_used_for_selection": False,
                "reference_program_role": "feasibility_validation_and_reference_horizon_only",
            }
        )
        entries[-1]["instruction"] = entries[-1]["task_text"]
    audit = {
        "seed": SEED,
        "attempts": attempts,
        "prior_text_sources": prior_sources,
        "exact_overlap_count": 0,
        "method_outputs_read": [],
        "selection_inputs": [
            "official VirtualHome scene inventory",
            "predefined semantic templates",
            "deterministic seeded order",
            "reference replay feasibility",
            "semantic atomic/dependency thresholds",
            "fixed category and scene quotas",
            "partial-order evaluator validity",
        ],
    }
    return entries, final_states, audit


def _write_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def generate() -> Dict[str, Any]:
    if not METHOD_FREEZE.exists():
        raise RuntimeError("Method must be frozen after development before holdout generation")
    targets = [MANIFEST_PATH, MANIFEST_SHA_PATH, FINAL_STATES_PATH, AUDIT_PATH]
    if any(path.exists() for path in targets):
        raise RuntimeError("Refusing to overwrite Phase-10 final holdout artifacts")
    entries, final_states, audit = build()
    categories = Counter(item["category"] for item in entries)
    scenes = Counter(item["scene"] for item in entries)
    if categories != Counter({item: 3 for item in CATEGORIES}) or scenes != Counter({0: 4, 1: 4, 2: 4}):
        raise RuntimeError(f"Holdout quota mismatch: categories={categories}, scenes={scenes}")
    if any(
        item["semantic_atomic_count"] < 2
        or item["dependency_depth"] < 2
        or item["reference_horizon"] < 10
        or not item["gold_semantics"]["required_dependency_edges"]
        for item in entries
    ):
        raise RuntimeError("Holdout complexity threshold failure")
    final_text = "".join(
        json.dumps(graph, ensure_ascii=False, separators=(",", ":")) + "\n"
        for graph in final_states
    )
    _write_exclusive(FINAL_STATES_PATH, final_text)
    manifest = {
        "schema_version": 1,
        "name": "Phase-10 Dependency-Aware Causal Holdout",
        "classification": "SYNTHETIC HOLDOUT ON OFFICIAL VIRTUALHOME SCENES",
        "seed": SEED,
        "task_count": 12,
        "category_allocation": dict(sorted(categories.items())),
        "scene_allocation": {str(key): value for key, value in sorted(scenes.items())},
        "selection_rule": "first reference-valid candidate per predeclared scene/category slot",
        "method_output_used_for_selection": False,
        "reference_program_is_task_semantics": False,
        "reference_feasibility_count": 12,
        "reference_final_states_sha256": sha256(FINAL_STATES_PATH),
        "entries": entries,
    }
    _write_exclusive(MANIFEST_PATH, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    manifest_sha = sha256(MANIFEST_PATH)
    _write_exclusive(MANIFEST_SHA_PATH, manifest_sha + "\n")
    lengths = [item["reference_horizon"] for item in entries]
    audit.update(
        {
            "task_count": 12,
            "category_allocation": dict(sorted(categories.items())),
            "scene_allocation": {str(key): value for key, value in sorted(scenes.items())},
            "reference_executable": 12,
            "evaluator_success": 12,
            "horizon": {
                "min": min(lengths), "mean": mean(lengths),
                "median": median(lengths), "max": max(lengths),
            },
            "manifest_sha256": manifest_sha,
            "reference_final_states_sha256": sha256(FINAL_STATES_PATH),
            "entries": [
                {
                    key: item[key]
                    for key in (
                        "task_id", "task_text", "scene", "category", "reference_horizon",
                        "semantic_atomic_count", "dependency_depth", "process_atomic_count",
                        "cross_object_transition_count", "cross_location_transition_count",
                        "reference_feasibility",
                    )
                }
                for item in entries
            ],
        }
    )
    _write_exclusive(AUDIT_PATH, json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    return {
        "tasks": 12,
        "categories": dict(categories),
        "scenes": dict(scenes),
        "reference_feasible": 12,
        "manifest_sha256": manifest_sha,
    }


if __name__ == "__main__":
    print(json.dumps(generate(), ensure_ascii=False, indent=2))

