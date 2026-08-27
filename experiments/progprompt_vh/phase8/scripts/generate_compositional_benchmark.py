"""Deterministically generate and validate the frozen Phase-8 stress set."""

from __future__ import annotations

import hashlib
import itertools
import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase5.execution import GraphProgramExecutor
from experiments.progprompt_vh.phase6.dataset import (
    graph_sha256,
    ordered_annotation_rows,
    read_jsonl,
    sha256,
)
from experiments.progprompt_vh.phase6.verification.deterministic_evaluator import (
    condition_satisfied,
    evaluate_conditions,
)


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase8"
DATA = ROOT / "data"
MANIFEST_PATH = DATA / "final_compositional_manifest.json"
FINAL_STATES_PATH = DATA / "reference_final_states.jsonl"
PROTOCOL_PATH = ROOT / "FINAL_BENCHMARK_PROTOCOL.md"
LOCK_PATH = DATA / "FINAL_PROTOCOL_LOCK.json"
PROCESS_LOCK = DATA / "PROCESS_PROMPT_LOCK.json"
COMPRESSION_LOCK = DATA / "TOKEN_COMPRESSION_LOCK.json"
ACTION_PATH = (
    PROJECT_ROOT / "experiments/progprompt_vh/phase5/data/graph_supported_actions.json"
)
SEED = 20260826

SCENES = {
    0: {
        "source": "experiments/progprompt_vh/results/environment_initial_state.json",
        "index": None,
    },
    1: {
        "source": "third_party/progprompt-vh/data/final_states/initial_states_env1.json",
        "index": 0,
    },
    2: {
        "source": "third_party/progprompt-vh/data/final_states/initial_states_env2.json",
        "index": 0,
    },
}

# Rows sum to 10 by goal count and to 10 by scene.
ALLOCATION = {
    (0, 2): 4,
    (1, 2): 3,
    (2, 2): 3,
    (0, 3): 3,
    (1, 3): 4,
    (2, 3): 3,
    (0, 4): 3,
    (1, 4): 3,
    (2, 4): 4,
}

METHOD_FILES = [
    ROOT / "compat_client.py",
    ROOT / "execution.py",
    ROOT / "representation.py",
    ROOT / "runner.py",
    ROOT / "methods/common.py",
    ROOT / "methods/hpaf_flat.py",
    ROOT / "methods/hpaf_full.py",
    ROOT / "verification/llm_verifier.py",
    ROOT / "configs/benchmark.yaml",
]
EVALUATOR_FILES = [
    PROJECT_ROOT
    / "experiments/progprompt_vh/phase6/verification/deterministic_evaluator.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase5/execution.py",
    PROJECT_ROOT / "experiments/progprompt_vh/adapters/virtualhome.py",
]


def _load_graph(scene: int) -> Dict[str, Any]:
    spec = SCENES[scene]
    path = PROJECT_ROOT / spec["source"]
    if spec["index"] is None:
        return json.loads(path.read_text(encoding="utf-8"))
    return read_jsonl(path)[int(spec["index"])]


def _condition_text(condition: Dict[str, Any]) -> str:
    if condition["predicate"] == "STATE":
        return f"STATE({condition['object']}, {condition['value']})"
    return (
        f"{condition['relation']}({condition['subject']}, {condition['object']})"
    )


def _state_goal(object_name: str, value: str, action: str) -> Dict[str, Any]:
    verb = {
        "open": "open",
        "close": "close",
        "switchon": "turn on",
        "switchoff": "turn off",
    }[action]
    condition = {
        "condition": f"STATE({object_name}, {value})",
        "predicate": "STATE",
        "object": object_name,
        "value": value,
        "rationale": "Direct persistent state requested by the generated atomic goal.",
    }
    return {
        "template": {
            "open": "OPEN",
            "close": "CLOSE",
            "switchon": "SWITCH_ON",
            "switchoff": "SWITCH_OFF",
        }[action],
        "manipulated_object": object_name,
        "involved_objects": [object_name],
        "instruction_fragment": f"{verb} the {object_name}",
        "goal_predicate": condition,
        "reference_program": f"find('{object_name}')\n{action}('{object_name}')",
    }


def _relation_goal(
    source: str,
    target: str,
    relation: str,
    target_open: bool,
) -> Dict[str, Any]:
    if relation == "INSIDE":
        fragment = f"put the {source} in the {target}"
        action = "putin"
        template = "PUT_IN"
    else:
        fragment = f"place the {source} on the {target}"
        action = "putback"
        template = "PUT_ON"
    lines = [f"find('{source}')", f"grab('{source}')", f"find('{target}')"]
    if relation == "INSIDE" and target_open:
        lines.append(f"open('{target}')")
    lines.append(f"{action}('{source}','{target}')")
    condition = {
        "condition": f"{relation}({source}, {target})",
        "predicate": "RELATION",
        "subject": source,
        "relation": relation,
        "object": target,
        "rationale": "Direct persistent relation requested by the generated atomic goal.",
    }
    return {
        "template": template,
        "source_object": source,
        "target_object": target,
        "manipulated_object": source,
        "involved_objects": [source, target],
        "instruction_fragment": fragment,
        "goal_predicate": condition,
        "reference_program": "\n".join(lines),
    }


def _execute_reference(
    graph: Dict[str, Any], goals: Sequence[Dict[str, Any]], actions: Dict[str, Any]
) -> Tuple[bool, Dict[str, Any]]:
    executor = GraphProgramExecutor(
        graph,
        actions_payload=actions,
        llm_client=None,
        unity_comm=None,
        seed=SEED,
    )
    program_parts = []
    for index, goal in enumerate(goals, 1):
        program = f"# reference goal {index}\n{goal['reference_program']}"
        program_parts.append(program)
        executor.execute(program)
    artifacts = executor.artifacts()
    score = evaluate_conditions(
        artifacts["final_state"], [goal["goal_predicate"] for goal in goals]
    )
    all_actions_executable = bool(artifacts["graph_execution_trace"]) and all(
        item["success"] for item in artifacts["graph_execution_trace"]
    )
    return all_actions_executable and bool(score["final_semantic_SR"]), {
        "program": "\n".join(program_parts),
        "compiled_actions": artifacts["compiled_virtualhome_actions"],
        "trace": artifacts["graph_execution_trace"],
        "final_state": artifacts["final_state"],
        "score": score,
        "all_actions_executable": all_actions_executable,
    }


def _enumerate_atomic_goals(
    graph: Dict[str, Any], actions: Dict[str, Any]
) -> List[Dict[str, Any]]:
    nodes = [
        node
        for node in graph["nodes"]
        if node["class_name"] != "character" and node.get("category") != "Rooms"
    ]
    counts = Counter(str(node["class_name"]) for node in nodes)
    unique = {
        str(node["class_name"]): node
        for node in nodes
        if counts[str(node["class_name"])] == 1
    }
    goals: List[Dict[str, Any]] = []
    for name, node in sorted(unique.items()):
        properties = {str(item).upper() for item in node.get("properties", [])}
        states = {str(item).upper() for item in node.get("states", [])}
        if "CAN_OPEN" in properties:
            if "CLOSED" in states:
                goals.append(_state_goal(name, "OPEN", "open"))
            elif "OPEN" in states:
                goals.append(_state_goal(name, "CLOSED", "close"))
        if "HAS_SWITCH" in properties:
            if "OFF" in states:
                goals.append(_state_goal(name, "ON", "switchon"))
            elif "ON" in states:
                goals.append(_state_goal(name, "OFF", "switchoff"))

    sources = sorted(
        name
        for name, node in unique.items()
        if "GRABBABLE" in {str(item).upper() for item in node.get("properties", [])}
    )
    containers = sorted(
        name
        for name, node in unique.items()
        if "CONTAINERS" in {str(item).upper() for item in node.get("properties", [])}
    )
    surfaces = sorted(
        name
        for name, node in unique.items()
        if "SURFACES" in {str(item).upper() for item in node.get("properties", [])}
    )
    for source, target in itertools.product(sources, containers):
        if source == target:
            continue
        target_states = {
            str(item).upper() for item in unique[target].get("states", [])
        }
        candidate = _relation_goal(
            source, target, "INSIDE", target_open="CLOSED" in target_states
        )
        already, _ = condition_satisfied(graph, candidate["goal_predicate"])
        if not already:
            goals.append(candidate)
    for source, target in itertools.product(sources, surfaces):
        if source == target:
            continue
        candidate = _relation_goal(source, target, "ON", target_open=False)
        already, _ = condition_satisfied(graph, candidate["goal_predicate"])
        if not already:
            goals.append(candidate)

    valid = []
    for goal in sorted(
        goals,
        key=lambda item: (
            item["template"],
            item["manipulated_object"],
            item.get("target_object", ""),
        ),
    ):
        feasible, _detail = _execute_reference(graph, [goal], actions)
        if feasible:
            valid.append(goal)
    return valid


def _compatible(goals: Sequence[Dict[str, Any]]) -> bool:
    involved = [name for goal in goals for name in goal["involved_objects"]]
    if len(involved) != len(set(involved)):
        return False
    templates = {goal["template"] for goal in goals}
    if len(templates) < 2:
        return False
    return bool(templates & {"PUT_IN", "PUT_ON"})


def _instruction(goals: Sequence[Dict[str, Any]]) -> str:
    fragments = [goal["instruction_fragment"] for goal in goals]
    if len(fragments) == 2:
        body = f"{fragments[0]} and {fragments[1]}"
    else:
        body = f"{', '.join(fragments[:-1])}, and {fragments[-1]}"
    return body[0].upper() + body[1:] + "."


def _leakage_corpus() -> Tuple[set[str], Dict[str, Any]]:
    sources: Dict[str, List[str]] = {}
    for split in ["train", "test_seen"]:
        sources[split] = [row[0] for row in ordered_annotation_rows(split)]
    phase7 = json.loads(
        (
            PROJECT_ROOT
            / "experiments/progprompt_vh/phase7/data/combined_manifest.json"
        ).read_text(encoding="utf-8")
    )
    sources["phase7_development"] = [item["task_text"] for item in phase7["entries"]]
    corpus = {text.strip().lower() for rows in sources.values() for text in rows}
    source_hashes = {
        name: hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        for name, rows in sources.items()
    }
    return corpus, {"sizes": {key: len(value) for key, value in sources.items()}, "hashes": source_hashes}


def _bundle_hash(paths: Iterable[Path]) -> str:
    payload = [
        (str(path.relative_to(PROJECT_ROOT)), sha256(path)) for path in paths
    ]
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"Refusing to regenerate frozen benchmark artifact: {path}")
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def generate() -> Dict[str, Any]:
    if not PROCESS_LOCK.exists() or not COMPRESSION_LOCK.exists():
        raise RuntimeError("Method process/compression locks must exist before benchmark generation")
    compression = json.loads(COMPRESSION_LOCK.read_text(encoding="utf-8"))
    if compression.get("adopted_representation") not in {"compressed", "uncompressed"}:
        raise RuntimeError("Compression lock has no valid adopted representation")
    representation = str(compression["adopted_representation"])
    if any(path.exists() for path in [MANIFEST_PATH, FINAL_STATES_PATH, PROTOCOL_PATH, LOCK_PATH]):
        raise RuntimeError("Final benchmark has already been generated/frozen")

    actions = json.loads(ACTION_PATH.read_text(encoding="utf-8"))
    leakage_corpus, leakage_sources = _leakage_corpus()
    rng = random.Random(SEED)
    selected: List[Dict[str, Any]] = []
    final_states: List[Dict[str, Any]] = []
    attempts: Dict[str, int] = {}

    for (scene, goal_count), required in ALLOCATION.items():
        graph = _load_graph(scene)
        pool = _enumerate_atomic_goals(graph, actions)
        accepted_keys = set()
        accepted = 0
        draws = 0
        while accepted < required:
            draws += 1
            if draws > 250000:
                raise RuntimeError(
                    f"Unable to fill deterministic allocation scene={scene} goals={goal_count}"
                )
            goals = rng.sample(pool, goal_count)
            if not _compatible(goals):
                continue
            key = tuple(
                sorted(
                    (
                        goal["template"],
                        goal["manipulated_object"],
                        goal.get("target_object", ""),
                    )
                    for goal in goals
                )
            )
            if key in accepted_keys:
                continue
            accepted_keys.add(key)
            feasible, reference = _execute_reference(graph, goals, actions)
            if not feasible:
                continue
            instruction = _instruction(goals)
            if instruction.strip().lower() in leakage_corpus:
                continue
            accepted += 1
            ordinal = len(selected) + 1
            task_id = f"vhcsb_s{scene}_g{goal_count}_{ordinal:02d}"
            final_state_index = len(final_states)
            final_states.append(reference["final_state"])
            selected.append(
                {
                    "task_id": task_id,
                    "task_text": instruction,
                    "instruction": instruction,
                    "official_split": "synthetic_composition",
                    "scene": scene,
                    "goal_count": goal_count,
                    "atomic_goals": goals,
                    "goal_predicates": [goal["goal_predicate"] for goal in goals],
                    "manipulated_objects": [
                        goal["manipulated_object"] for goal in goals
                    ],
                    "initial_state_source": SCENES[scene]["source"],
                    "initial_state_index": SCENES[scene]["index"],
                    "initial_state_sha256": graph_sha256(graph),
                    "evaluator_type": "persistent_conjunctive_state",
                    "reference_feasibility": {
                        "feasible": True,
                        "all_actions_executable": reference["all_actions_executable"],
                        "all_goal_predicates_satisfied": bool(
                            reference["score"]["final_semantic_SR"]
                        ),
                    },
                    "reference_program": reference["program"],
                    "reference_action_sequence": reference["compiled_actions"],
                    "reference_trace": reference["trace"],
                    "reference_final_state_source": str(
                        FINAL_STATES_PATH.relative_to(PROJECT_ROOT)
                    ),
                    "reference_final_state_index": final_state_index,
                    "reference_final_state_sha256": graph_sha256(
                        reference["final_state"]
                    ),
                    "exact_text_overlap": False,
                    "synthetic": True,
                }
            )
        attempts[f"scene{scene}_goal{goal_count}"] = draws

    if len(selected) != 30:
        raise RuntimeError(f"Expected 30 generated tasks, got {len(selected)}")
    if Counter(item["scene"] for item in selected) != Counter({0: 10, 1: 10, 2: 10}):
        raise RuntimeError("Scene allocation is not exactly 10/10/10")
    if Counter(item["goal_count"] for item in selected) != Counter({2: 10, 3: 10, 4: 10}):
        raise RuntimeError("Goal-count allocation is not exactly 10/10/10")
    if len({item["task_text"].lower() for item in selected}) != 30:
        raise RuntimeError("Generated instructions are not unique")

    final_states_text = "".join(
        json.dumps(graph, ensure_ascii=False, separators=(",", ":")) + "\n"
        for graph in final_states
    )
    _write_exclusive(FINAL_STATES_PATH, final_states_text)
    manifest = {
        "schema_version": 1,
        "name": "VirtualHome Compositional Stress Benchmark",
        "classification": "SYNTHETIC COMPOSITION BASED ON OFFICIAL VIRTUALHOME SCENES",
        "official_progprompt_test_set": False,
        "seed": SEED,
        "generation_algorithm": (
            "Enumerate executable persistent atomics, seeded-sample compatible disjoint "
            "compositions, accept first reference-validated combinations per fixed allocation."
        ),
        "scene_allocation": {"0": 10, "1": 10, "2": 10},
        "goal_count_allocation": {"2": 10, "3": 10, "4": 10},
        "exact_text_overlap_count": 0,
        "leakage_corpus": leakage_sources,
        "reference_feasibility_count": 30,
        "generation_draws": attempts,
        "reference_final_states_sha256": sha256(FINAL_STATES_PATH),
        "entries": selected,
    }
    _write_exclusive(
        MANIFEST_PATH,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )

    protocol = f"""# Final Benchmark Protocol

## Identity

- Name: VirtualHome Compositional Stress Benchmark.
- Classification: synthetic deterministic compositions based on official VirtualHome scene inventories; not an official ProgPrompt test set.
- Seed: `{SEED}`.
- Size: 30 task-scene instances: 10 each with 2, 3, and 4 semantic goals.
- Scene balance: 10 each in official VirtualHome scenes 0, 1, and 2.

## Frozen Generation Rule

The generator enumerates persistent `PUT_IN`, `PUT_ON`, `SWITCH_ON`,
`SWITCH_OFF`, `OPEN`, and `CLOSE` atomics on unique scene instances. It uses a
fixed RNG, rejects conflicting/shared object classes, requires at least one
transfer and two goal-template types, and accepts the first combinations whose
complete deterministic reference programs execute and satisfy every conjunctive
predicate. No LLM output or method result enters generation or selection.

Exact instruction overlap with ProgPrompt train, test_seen, and the 29 Phase-7
development instances is zero. Atomic goals may recur; novel composition is the
intended independent variable.

## Methods And Order

The frozen methods are `ProgPrompt-Compat`, `HPAF-Flat`, and `HPAF-Full`.
Execution order is task-major, then method order as listed. Each of the 90
task-method pairs receives exactly one run. No repeats, resampling, task removal,
prompt change, or evaluator change is allowed after this lock.

Flat and Full share process-aware ProgramAgent rules, alignment/precondition
guidance, and the frozen `{representation}` context representation. The attempted
compression is used only if its bounded development gate passed. Full alone has
TaskAgent decomposition, current-state per-atomic generation, atomic verification,
and one local Retry-1. The online verifier never receives frozen goal predicates.

## Evaluator And Metrics

Final success is method-independent conjunction over the pre-frozen persistent
goal predicates. Goal completion ratio is the fraction satisfied. Primary results
report Task SR by 2/3/4 goals and overall. Macro Exec is primary; micro Exec,
tokens/task, calls/task, role costs, retention, and 2-to-4-goal SR drop are also
reported. Reference programs and final states validate dataset feasibility only
and never enter any method prompt.
"""
    _write_exclusive(PROTOCOL_PATH, protocol)

    lock = {
        "schema_version": 1,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "formal_execution_started": False,
        "manifest_sha256": sha256(MANIFEST_PATH),
        "reference_final_states_sha256": sha256(FINAL_STATES_PATH),
        "protocol_sha256": sha256(PROTOCOL_PATH),
        "process_prompt_lock_sha256": sha256(PROCESS_LOCK),
        "token_compression_lock_sha256": sha256(COMPRESSION_LOCK),
        "method_bundle_sha256": _bundle_hash(METHOD_FILES),
        "evaluator_bundle_sha256": _bundle_hash(EVALUATOR_FILES),
        "action_set_sha256": sha256(ACTION_PATH),
        "seed": SEED,
        "records_required": 90,
    }
    _write_exclusive(
        LOCK_PATH,
        json.dumps(lock, ensure_ascii=False, indent=2) + "\n",
    )
    return {
        "manifest_sha256": lock["manifest_sha256"],
        "protocol_sha256": lock["protocol_sha256"],
        "tasks": len(selected),
        "reference_feasible": sum(
            int(item["reference_feasibility"]["feasible"]) for item in selected
        ),
        "exact_text_overlap": sum(int(item["exact_text_overlap"]) for item in selected),
    }


if __name__ == "__main__":
    print(json.dumps(generate(), ensure_ascii=False, indent=2))
