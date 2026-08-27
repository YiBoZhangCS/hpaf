"""Generate the pre-frozen, causal Long-11 extension on official VH scenes."""

from __future__ import annotations

import hashlib
import itertools
import json
import random
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase5.execution import GraphProgramExecutor
from experiments.progprompt_vh.phase6.dataset import (
    graph_sha256,
    ordered_annotation_rows,
    read_jsonl,
    sha256,
)
from experiments.progprompt_vh.phase9.verification.causal_evaluator import (
    evaluate_causal_goal,
)


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase9"
DATA = ROOT / "data"
MANIFEST_PATH = DATA / "long11_manifest.json"
FINAL_STATES_PATH = DATA / "long11_reference_final_states.jsonl"
STRUCTURE_AUDIT_PATH = ROOT / "LONG_TASK_STRUCTURE_AUDIT.md"
REFERENCE_AUDIT_PATH = ROOT / "LONG_REFERENCE_AUDIT.json"
LEAKAGE_AUDIT_PATH = ROOT / "LONG11_LEAKAGE_AUDIT.json"
ACTION_PATH = (
    PROJECT_ROOT / "experiments/progprompt_vh/phase5/data/graph_supported_actions.json"
)
PHASE7_MANIFEST = (
    PROJECT_ROOT / "experiments/progprompt_vh/phase7/data/combined_manifest.json"
)
PHASE8_MANIFEST = (
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/data/final_compositional_manifest.json"
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

# Fixed before candidate execution: 4/4/3 scenes and exact 3/3/3/2 categories.
SLOTS = [
    (0, "container_state_transfer"),
    (0, "appliance_lifecycle"),
    (0, "causal_multi_object"),
    (0, "cross_location_mixed"),
    (1, "container_state_transfer"),
    (1, "appliance_lifecycle"),
    (1, "causal_multi_object"),
    (1, "cross_location_mixed"),
    (2, "container_state_transfer"),
    (2, "appliance_lifecycle"),
    (2, "causal_multi_object"),
]

APPLIANCE_COMPATIBILITY = {
    "microwave": {"EATABLE", "FOODLIKE"},
    "washingmachine": {"CLOTHES", "COVER_OBJECT"},
    "dishwasher": {"RECIPIENT", "CUTLERY"},
}
APPLIANCE_BY_SCENE = {0: "washingmachine", 1: "dishwasher", 2: "microwave"}
STORAGE_CLASSES = {
    "bathroomcabinet", "cabinet", "closet", "fridge", "kitchencabinet", "nightstand",
}
PERSONAL_CLASSES = {
    "barsoap", "toothbrush", "toothpaste", "towel", "slippers",
    "clothesshirt", "clothespants", "hairproduct", "facecream",
}
KITCHENWARE_CLASSES = {
    "dishwashingliquid", "dishbowl", "plate", "mug", "waterglass", "wineglass",
    "coffeepot", "cookingpot", "cutleryfork", "cutleryknife", "fryingpan",
}
DESK_CLASSES = {"book", "paper", "mouse", "keyboard", "remotecontrol", "cellphone"}
FOODLIKE = {
    "salmon", "chicken", "cutlets", "mincedmeat", "breadslice", "poundcake",
    "pie", "cupcake", "creamybuns", "apple", "bananas", "lime", "peach", "plum",
}


def _load_graph(scene: int) -> Dict[str, Any]:
    spec = SCENES[scene]
    path = PROJECT_ROOT / str(spec["source"])
    if spec["index"] is None:
        return json.loads(path.read_text(encoding="utf-8"))
    return read_jsonl(path)[int(spec["index"])]


def _unique_nodes(graph: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    nodes = [
        item for item in graph["nodes"]
        if item["class_name"] != "character" and item.get("category") != "Rooms"
    ]
    counts = Counter(str(item["class_name"]) for item in nodes)
    return {
        str(item["class_name"]): item
        for item in nodes
        if counts[str(item["class_name"])] == 1
    }


def _representative_nodes(graph: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for item in graph["nodes"]:
        if item["class_name"] != "character" and item.get("category") != "Rooms":
            result.setdefault(str(item["class_name"]), item)
    return result


def _props(node: Mapping[str, Any]) -> set[str]:
    return {str(item).upper() for item in node.get("properties", [])}


def _states(node: Mapping[str, Any]) -> set[str]:
    return {str(item).upper() for item in node.get("states", [])}


def _source_pool(nodes: Mapping[str, Mapping[str, Any]]) -> List[str]:
    excluded = {"SURFACES", "CONTAINERS", "SITTABLE", "LIEABLE", "HAS_SWITCH"}
    return sorted(
        name for name, node in nodes.items()
        if "GRABBABLE" in _props(node) and not (_props(node) & excluded)
    )


def _carrier_pool(nodes: Mapping[str, Mapping[str, Any]]) -> List[str]:
    required = {"GRABBABLE", "CONTAINERS", "CAN_OPEN"}
    return sorted(name for name, node in nodes.items() if required <= _props(node))


def _closed_container_pool(nodes: Mapping[str, Mapping[str, Any]]) -> List[str]:
    required = {"CONTAINERS", "CAN_OPEN"}
    return sorted(
        name for name, node in nodes.items()
        if required <= _props(node) and "CLOSED" in _states(node)
    )


def _storage_container_pool(nodes: Mapping[str, Mapping[str, Any]]) -> List[str]:
    return [name for name in _closed_container_pool(nodes) if name in STORAGE_CLASSES]


def _surface_pool(nodes: Mapping[str, Mapping[str, Any]]) -> List[str]:
    forbidden = {"GRABBABLE", "CONTAINERS", "HAS_SWITCH"}
    return sorted(
        name for name, node in nodes.items()
        if "SURFACES" in _props(node) and not (_props(node) & forbidden)
    )


def _semantic_group(nodes: Mapping[str, Mapping[str, Any]], source: str) -> str:
    properties = _props(nodes[source])
    if source in FOODLIKE or "EATABLE" in properties:
        return "food"
    if source in PERSONAL_CLASSES or "CLOTHES" in properties:
        return "personal"
    if source in KITCHENWARE_CLASSES or source.startswith("cutlery"):
        return "kitchenware"
    if source in DESK_CLASSES or "READABLE" in properties:
        return "desk"
    return "misc"


def _storage_for(
    nodes: Mapping[str, Mapping[str, Any]], source: str
) -> List[str]:
    allowed = {
        "food": {"fridge", "kitchencabinet", "cabinet"},
        "kitchenware": {"kitchencabinet", "cabinet"},
        "personal": {"bathroomcabinet", "closet", "nightstand", "cabinet"},
        "desk": {"cabinet", "closet", "nightstand"},
        "misc": {"cabinet", "closet"},
    }[_semantic_group(nodes, source)]
    return [name for name in _storage_container_pool(nodes) if name in allowed]


def _natural_destination_surfaces(
    nodes: Mapping[str, Mapping[str, Any]], rooms: Mapping[str, str], source: str,
    *, appliance: str | None = None,
) -> List[str]:
    surfaces = _surface_pool(nodes)
    if appliance in {"microwave", "dishwasher"}:
        allowed = {"kitchentable", "kitchencounter", "coffeetable"}
    elif source:
        allowed = {
            "food": {"kitchentable", "kitchencounter", "coffeetable"},
            "kitchenware": {"kitchentable", "kitchencounter", "coffeetable"},
            "personal": {"bathroomcounter", "bed"},
            "desk": {"desk", "coffeetable", "kitchentable", "mousemat"},
            "misc": set(surfaces) - {"bed", "sofa"},
        }[_semantic_group(nodes, source)]
    else:
        allowed = set(surfaces)
    return [name for name in surfaces if name in allowed]


def _room_map(graph: Dict[str, Any]) -> Dict[str, str]:
    class_by_id = {int(item["id"]): str(item["class_name"]) for item in graph["nodes"]}
    room_ids = {
        int(item["id"]) for item in graph["nodes"] if item.get("category") == "Rooms"
    }
    parents: Dict[int, List[int]] = {}
    for edge in graph["edges"]:
        if str(edge["relation_type"]).upper() == "INSIDE":
            parents.setdefault(int(edge["from_id"]), []).append(int(edge["to_id"]))

    def room_for(node_id: int) -> str:
        frontier = [node_id]
        seen = set()
        while frontier:
            current = frontier.pop(0)
            if current in room_ids:
                return class_by_id[current]
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(parents.get(current, []))
        return "unknown"

    return {
        str(item["class_name"]): room_for(int(item["id"]))
        for item in graph["nodes"]
        if item["class_name"] != "character"
    }


def _relation(subject: str, relation: str, obj: str) -> Dict[str, Any]:
    return {
        "condition": f"{relation}({subject}, {obj})",
        "predicate": "RELATION",
        "subject": subject,
        "relation": relation,
        "object": obj,
        "rationale": "Frozen final relation required by the deterministic task template.",
    }


def _state(obj: str, value: str) -> Dict[str, Any]:
    return {
        "condition": f"STATE({obj}, {value})",
        "predicate": "STATE",
        "object": obj,
        "value": value,
        "rationale": "Frozen terminal state required by the deterministic task template.",
    }


def _stage(number: int, description: str, verb: str, first: str, second: str | None = None) -> Dict[str, Any]:
    event = {"verb": verb, "first": first}
    if second is not None:
        event["second"] = second
    return {"stage": number, "description": description, "event": event}


def _program(*stages: Sequence[str]) -> str:
    lines: List[str] = []
    for number, actions in enumerate(stages, 1):
        lines.append(f"# causal stage {number}")
        lines.extend(actions)
    return "\n".join(lines)


def _base_candidate(
    *, scene: int, category: str, instruction: str, program: str,
    causal_stages: List[Dict[str, Any]], manipulated: Sequence[str],
    involved: Sequence[str], rooms: Sequence[str], final_conditions: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "scene": scene,
        "category": category,
        "instruction": instruction,
        "reference_program": program,
        "causal_stages": causal_stages,
        "causal_stage_count": len(causal_stages),
        "dependent_stage_count": len(causal_stages) - 1,
        "independent_goal_count": 1,
        "manipulated_objects": list(dict.fromkeys(manipulated)),
        "involved_objects": list(dict.fromkeys(involved)),
        "rooms_involved": sorted(set(rooms) - {"unknown"}),
        "evaluator_type": "generic_causal_trace_state",
        "causal_goal": {
            "kind": "ORDERED_EVENTS_AND_STATE",
            "event_stages": causal_stages,
            "final_conditions": list(final_conditions),
        },
    }


def _container_candidates(scene: int, graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    nodes = _unique_nodes(graph)
    rooms = _room_map(graph)
    candidates = []
    for source in _source_pool(nodes):
        for intermediate, target in itertools.product(_storage_for(nodes, source), repeat=2):
            if len({source, intermediate, target}) != 3:
                continue
            instruction = (
                f"Temporarily store the {source} in the {intermediate}, then transfer the {source} "
                f"to the {target} and leave both containers closed."
            )
            stages = [
            _stage(1, "store source in intermediate container", "putin", source, intermediate),
            _stage(2, "close intermediate container", "close", intermediate),
            _stage(3, "retrieve source from intermediate container", "grab", source),
            _stage(4, "restore intermediate container state", "close", intermediate),
            _stage(5, "store source in final container", "putin", source, target),
            _stage(6, "restore final container state", "close", target),
            ]
            program = _program(
            [f"find('{source}')", f"grab('{source}')", f"find('{intermediate}')", f"open('{intermediate}')", f"putin('{source}','{intermediate}')", f"close('{intermediate}')"],
            [f"open('{intermediate}')", f"find('{source}')", f"grab('{source}')", f"find('{intermediate}')", f"close('{intermediate}')"],
            [f"find('{target}')", f"open('{target}')", f"putin('{source}','{target}')", f"close('{target}')"],
            )
            candidates.append(_base_candidate(
            scene=scene, category="container_state_transfer", instruction=instruction,
            program=program, causal_stages=stages, manipulated=[source],
            involved=[source, intermediate, target],
            rooms=[rooms.get(source, "unknown"), rooms.get(intermediate, "unknown"), rooms.get(target, "unknown")],
            final_conditions=[_relation(source, "INSIDE", target), _state(intermediate, "CLOSED"), _state(target, "CLOSED")],
            ))
    return candidates


def _compatible_appliance_sources(
    nodes: Mapping[str, Mapping[str, Any]], appliance: str
) -> List[str]:
    allowed = APPLIANCE_COMPATIBILITY[appliance]
    result = []
    for source in _source_pool(nodes):
        tags = _props(nodes[source])
        if source in FOODLIKE:
            tags.add("FOODLIKE")
        if source.startswith("cutlery"):
            tags.add("CUTLERY")
        if tags & allowed:
            result.append(source)
    return result


def _process_verb(appliance: str) -> str:
    return {"microwave": "heat", "washingmachine": "wash", "dishwasher": "clean"}[appliance]


def _appliance_candidates(scene: int, graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    nodes = _unique_nodes(graph)
    source_nodes = _representative_nodes(graph)
    rooms = _room_map(graph)
    candidates = []
    appliances = [APPLIANCE_BY_SCENE[scene]] if APPLIANCE_BY_SCENE[scene] in nodes else []
    for appliance in appliances:
        for source, destination in itertools.product(
            _compatible_appliance_sources(source_nodes, appliance),
            _natural_destination_surfaces(nodes, rooms, source="", appliance=appliance)
        ):
            if len({source, appliance, destination}) != 3:
                continue
            verb = _process_verb(appliance)
            instruction = (
                f"{verb.capitalize()} the {source} in the {appliance}, complete the cycle, "
                f"then place the {source} on the {destination}."
            )
            stages = [
                _stage(1, "load source into appliance", "putin", source, appliance),
                _stage(2, "start appliance", "switchon", appliance),
                _stage(3, "complete appliance cycle", "switchoff", appliance),
                _stage(4, "retrieve processed source", "grab", source),
                _stage(5, "place processed source at destination", "putback", source, destination),
            ]
            program = _program(
                [f"find('{source}')", f"grab('{source}')", f"find('{appliance}')", f"open('{appliance}')", f"putin('{source}','{appliance}')", f"close('{appliance}')"],
                [f"switchon('{appliance}')", f"switchoff('{appliance}')"],
                [f"open('{appliance}')", f"find('{source}')", f"grab('{source}')"],
                [f"find('{destination}')", f"putback('{source}','{destination}')"],
            )
            candidates.append(_base_candidate(
                scene=scene, category="appliance_lifecycle", instruction=instruction,
                program=program, causal_stages=stages, manipulated=[source],
                involved=[source, appliance, destination],
                rooms=[rooms.get(source, "unknown"), rooms.get(appliance, "unknown"), rooms.get(destination, "unknown")],
                final_conditions=[_relation(source, "ON", destination), _state(appliance, "OFF")],
            ))
    return candidates


def _multi_object_candidates(scene: int, graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    nodes = _unique_nodes(graph)
    rooms = _room_map(graph)
    candidates = []
    for first, second, container in itertools.product(
        _source_pool(nodes), _source_pool(nodes), _storage_container_pool(nodes)
    ):
        if first >= second or len({first, second, container}) != 3:
            continue
        if _semantic_group(nodes, first) != _semantic_group(nodes, second):
            continue
        if container not in _storage_for(nodes, first):
            continue
        for destination in _natural_destination_surfaces(nodes, rooms, second):
            if destination in {first, second, container}:
                continue
            instruction = (
                f"Stage the {first} and {second} together in the {container}, then leave "
                f"the {first} stored there and deliver the {second} to the {destination}, "
                f"with the {container} closed."
            )
            stages = [
                _stage(1, "stage first source in shared container", "putin", first, container),
                _stage(2, "stage second source in shared container", "putin", second, container),
                _stage(3, "retrieve second source after shared staging", "grab", second),
                _stage(4, "restore shared container state", "close", container),
                _stage(5, "deliver second source to destination", "putback", second, destination),
            ]
            program = _program(
                [f"find('{first}')", f"grab('{first}')", f"find('{container}')", f"open('{container}')", f"putin('{first}','{container}')"],
                [f"find('{second}')", f"grab('{second}')", f"find('{container}')", f"putin('{second}','{container}')", f"close('{container}')"],
                [f"open('{container}')", f"find('{second}')", f"grab('{second}')", f"find('{container}')", f"close('{container}')"],
                [f"find('{destination}')", f"putback('{second}','{destination}')"],
            )
            candidates.append(_base_candidate(
                scene=scene, category="causal_multi_object", instruction=instruction,
                program=program, causal_stages=stages, manipulated=[first, second],
                involved=[first, second, container, destination],
                rooms=[rooms.get(first, "unknown"), rooms.get(second, "unknown"), rooms.get(destination, "unknown")],
                final_conditions=[_relation(first, "INSIDE", container), _relation(second, "ON", destination), _state(container, "CLOSED")],
            ))
    return candidates


def _cross_location_candidates(scene: int, graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    nodes = _unique_nodes(graph)
    rooms = _room_map(graph)
    candidates = []
    for source, waypoint, container in itertools.product(
        _source_pool(nodes), _surface_pool(nodes), _storage_container_pool(nodes)
    ):
        if waypoint not in _natural_destination_surfaces(nodes, rooms, source):
            continue
        if container not in _storage_for(nodes, source):
            continue
        for destination in _natural_destination_surfaces(nodes, rooms, source):
            if len({source, waypoint, container, destination}) != 4:
                continue
            route_rooms = [rooms.get(source, "unknown"), rooms.get(waypoint, "unknown"), rooms.get(container, "unknown"), rooms.get(destination, "unknown")]
            if "unknown" in route_rooms or len(set(route_rooms)) < 2 or rooms.get(waypoint) == rooms.get(destination):
                continue
            instruction = (
                f"Stage the {source} on the {waypoint}, store the {source} temporarily in the "
                f"{container}, then deliver the {source} to the {destination} and leave the {container} closed."
            )
            stages = [
                _stage(1, "stage source at waypoint", "putback", source, waypoint),
                _stage(2, "store source in intermediate container", "putin", source, container),
                _stage(3, "retrieve source from intermediate container", "grab", source),
                _stage(4, "restore intermediate container state", "close", container),
                _stage(5, "deliver source to final destination", "putback", source, destination),
            ]
            program = _program(
                [f"find('{source}')", f"grab('{source}')", f"find('{waypoint}')", f"putback('{source}','{waypoint}')"],
                [f"find('{source}')", f"grab('{source}')", f"find('{container}')", f"open('{container}')", f"putin('{source}','{container}')", f"close('{container}')"],
                [f"open('{container}')", f"find('{source}')", f"grab('{source}')", f"find('{container}')", f"close('{container}')"],
                [f"find('{destination}')", f"putback('{source}','{destination}')"],
            )
            candidates.append(_base_candidate(
                scene=scene, category="cross_location_mixed", instruction=instruction,
                program=program, causal_stages=stages, manipulated=[source],
                involved=[source, waypoint, container, destination], rooms=route_rooms,
                final_conditions=[_relation(source, "ON", destination), _state(container, "CLOSED")],
            ))
    return candidates


CANDIDATE_BUILDERS = {
    "container_state_transfer": _container_candidates,
    "appliance_lifecycle": _appliance_candidates,
    "causal_multi_object": _multi_object_candidates,
    "cross_location_mixed": _cross_location_candidates,
}


def _execute_reference(
    graph: Dict[str, Any], candidate: Dict[str, Any], actions: Dict[str, Any]
) -> Tuple[bool, Dict[str, Any]]:
    executor = GraphProgramExecutor(
        graph, actions_payload=actions, llm_client=None, unity_comm=None, seed=SEED
    )
    executor.execute(candidate["reference_program"])
    artifacts = executor.artifacts()
    score = evaluate_causal_goal(
        {"graph_execution_trace": artifacts["graph_execution_trace"]},
        candidate["causal_goal"], artifacts["final_state"],
    )
    trace = artifacts["graph_execution_trace"]
    all_actions = bool(trace) and all(bool(item["success"]) for item in trace)
    return all_actions and bool(score["final_semantic_SR"]), {
        "final_state": artifacts["final_state"],
        "compiled_actions": artifacts["compiled_virtualhome_actions"],
        "trace": trace,
        "score": score,
        "all_actions_executable": all_actions,
    }


def _leakage_corpus() -> Tuple[set[str], Dict[str, Any]]:
    sources: Dict[str, List[str]] = {
        split: [row[0] for row in ordered_annotation_rows(split)]
        for split in ["train", "test_seen"]
    }
    phase7 = json.loads(PHASE7_MANIFEST.read_text(encoding="utf-8"))
    phase8 = json.loads(PHASE8_MANIFEST.read_text(encoding="utf-8"))
    sources["existing_29"] = [item["task_text"] for item in phase7["entries"]]
    sources["phase8_synthetic_30"] = [item["task_text"] for item in phase8["entries"]]
    corpus = {text.strip().lower() for rows in sources.values() for text in rows}
    detail = {
        name: {
            "count": len(rows),
            "sha256": hashlib.sha256(
                json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        }
        for name, rows in sources.items()
    }
    return corpus, detail


def _candidate_order(scene: int, category: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = sorted(
        candidates,
        key=lambda item: (
            item["instruction"], tuple(item["manipulated_objects"]), tuple(item["involved_objects"])
        ),
    )
    random.Random(f"{SEED}:{scene}:{category}").shuffle(ordered)
    return ordered


def build() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    actions = json.loads(ACTION_PATH.read_text(encoding="utf-8"))
    leakage, leakage_sources = _leakage_corpus()
    selected: List[Dict[str, Any]] = []
    final_states: List[Dict[str, Any]] = []
    attempts: Dict[str, int] = {}
    seen_instructions: set[str] = set()

    for scene, category in SLOTS:
        key = f"scene{scene}:{category}"
        candidates = _candidate_order(
            scene, category, CANDIDATE_BUILDERS[category](scene, _load_graph(scene))
        )
        accepted = None
        for attempt, candidate in enumerate(candidates, 1):
            instruction_key = candidate["instruction"].strip().lower()
            if instruction_key in leakage or instruction_key in seen_instructions:
                continue
            feasible, reference = _execute_reference(_load_graph(scene), candidate, actions)
            length = len(reference["trace"])
            if not feasible or not 11 <= length <= 25:
                continue
            if candidate["causal_stage_count"] < 3:
                continue
            if candidate["dependent_stage_count"] * 2 < candidate["causal_stage_count"]:
                continue
            accepted = dict(candidate)
            accepted["reference"] = reference
            accepted["reference_horizon"] = length
            attempts[key] = attempt
            break
        if accepted is None:
            raise RuntimeError(f"No qualifying first-valid candidate for {key}")
        seen_instructions.add(accepted["instruction"].strip().lower())
        final_states.append(accepted["reference"]["final_state"])
        selected.append(accepted)

    return selected, final_states, {
        "attempts": attempts,
        "leakage_sources": leakage_sources,
        "exact_overlap_count": 0,
    }


def _write_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"Refusing to overwrite frozen artifact: {path}")
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def _structure_markdown(entries: Sequence[Dict[str, Any]]) -> str:
    lines = [
        "# Long Task Structure Audit", "",
        "All tasks were selected before any method execution. Each row has one semantic objective whose later stages depend on successful predecessor state; these are not independent `G1 AND G2 AND G3` compositions.", "",
        "| Task | Scene | Category | Reference actions | Causal stages | Dependent stages | Independent goals | Rooms | Instruction |",
        "|---|---:|---|---:|---:|---:|---:|---|---|",
    ]
    for item in entries:
        lines.append(
            f"| `{item['task_id']}` | {item['scene']} | {item['category']} | "
            f"{item['reference_horizon']} | {item['causal_stage_count']} | "
            f"{item['dependent_stage_count']} | {item['independent_goal_count']} | "
            f"{', '.join(item['rooms_involved']) or 'unknown'} | {item['task_text']} |"
        )
    return "\n".join(lines) + "\n"


def generate() -> Dict[str, Any]:
    targets = [MANIFEST_PATH, FINAL_STATES_PATH, STRUCTURE_AUDIT_PATH, REFERENCE_AUDIT_PATH, LEAKAGE_AUDIT_PATH]
    if any(path.exists() for path in targets):
        raise RuntimeError("Long-11 artifacts already exist; regeneration is forbidden")
    selected, final_states, audit = build()
    counts = Counter(item["category"] for item in selected)
    scenes = Counter(item["scene"] for item in selected)
    if len(selected) != 11 or counts != Counter({
        "container_state_transfer": 3, "appliance_lifecycle": 3,
        "causal_multi_object": 3, "cross_location_mixed": 2,
    }) or scenes != Counter({0: 4, 1: 4, 2: 3}):
        raise RuntimeError(f"Frozen allocation mismatch: categories={counts}, scenes={scenes}")

    final_text = "".join(
        json.dumps(graph, ensure_ascii=False, separators=(",", ":")) + "\n"
        for graph in final_states
    )
    _write_exclusive(FINAL_STATES_PATH, final_text)
    entries = []
    for ordinal, item in enumerate(selected, 1):
        reference = item.pop("reference")
        task_id = f"vh40_long_s{item['scene']}_{ordinal:02d}"
        entries.append({
            "task_id": task_id,
            "task_text": item.pop("instruction"),
            "instruction": item.get("instruction"),
            "source": "phase9_pre_frozen_long_horizon_extension",
            "official_or_extension": "synthetic_long_horizon_extension",
            "official_split": "phase9_long_extension",
            "synthetic": True,
            "horizon": "Long",
            "is_long_horizon": True,
            "task_structure": "causally_dependent_sequential",
            "initial_state_source": SCENES[item["scene"]]["source"],
            "initial_state_index": SCENES[item["scene"]]["index"],
            "initial_state_sha256": graph_sha256(_load_graph(item["scene"])),
            "reference_action_sequence": reference["compiled_actions"],
            "reference_trace": reference["trace"],
            "reference_final_state_source": str(FINAL_STATES_PATH.relative_to(PROJECT_ROOT)),
            "reference_final_state_index": ordinal - 1,
            "reference_final_state_sha256": graph_sha256(reference["final_state"]),
            "reference_feasibility": {
                "all_actions_executable": reference["all_actions_executable"],
                "evaluator_success": bool(reference["score"]["final_semantic_SR"]),
            },
            **item,
        })
        entries[-1]["instruction"] = entries[-1]["task_text"]

    manifest = {
        "schema_version": 1,
        "name": "VH-40 Pre-Frozen Long-Horizon Extension",
        "classification": "SYNTHETIC EXTENSION ON OFFICIAL VIRTUALHOME SCENES",
        "official_progprompt_tasks": False,
        "seed": SEED,
        "selection_rule": "seeded deterministic candidate order; first reference-valid candidate per fixed category/scene slot",
        "scene_allocation": {str(key): value for key, value in sorted(scenes.items())},
        "category_allocation": dict(sorted(counts.items())),
        "exact_text_overlap_count": audit["exact_overlap_count"],
        "reference_feasibility_count": 11,
        "generation_attempts": audit["attempts"],
        "leakage_sources": audit["leakage_sources"],
        "reference_final_states_sha256": sha256(FINAL_STATES_PATH),
        "entries": entries,
    }
    _write_exclusive(MANIFEST_PATH, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    _write_exclusive(STRUCTURE_AUDIT_PATH, _structure_markdown(entries))

    lengths = [item["reference_horizon"] for item in entries]
    reference_audit = {
        "task_count": 11,
        "reference_executable": 11,
        "evaluator_success": 11,
        "horizon": {"min": min(lengths), "mean": mean(lengths), "median": median(lengths), "max": max(lengths)},
        "entries": [{
            "task_id": item["task_id"], "scene": item["scene"],
            "instruction": item["task_text"], "category": item["category"],
            "reference_program": item["reference_program"],
            "reference_length": item["reference_horizon"],
            "causal_stages": item["causal_stages"],
            "manipulated_objects": item["manipulated_objects"],
            "rooms_involved": item["rooms_involved"],
            "final_conditions": item["causal_goal"]["final_conditions"],
            "initial_graph_hash": item["initial_state_sha256"],
            "final_graph_hash": item["reference_final_state_sha256"],
        } for item in entries],
    }
    _write_exclusive(REFERENCE_AUDIT_PATH, json.dumps(reference_audit, ensure_ascii=False, indent=2) + "\n")
    leakage_audit = {
        "exact_instruction_overlap": 0,
        "corpora": audit["leakage_sources"],
        "checked_against": ["train", "test_seen", "existing_29", "phase8_synthetic_30"],
        "reference_or_evaluator_payload_entered_method_prompt": False,
        "pass": True,
    }
    _write_exclusive(LEAKAGE_AUDIT_PATH, json.dumps(leakage_audit, ensure_ascii=False, indent=2) + "\n")
    return {
        "tasks": 11, "reference_feasible": 11, "evaluator_success": 11,
        "scene_allocation": dict(scenes), "category_allocation": dict(counts),
        "manifest_sha256": sha256(MANIFEST_PATH),
    }


if __name__ == "__main__":
    print(json.dumps(generate(), ensure_ascii=False, indent=2))
