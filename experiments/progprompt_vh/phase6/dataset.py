"""Audited loaders and pre-execution selection policy for Phase 6."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT, PROGPROMPT_ROOT


PHASE6_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROGPROMPT_ROOT / "data"
SCENE0_INITIAL = PROJECT_ROOT / "experiments/progprompt_vh/results/environment_initial_state.json"
ACTION_PATH = PROJECT_ROOT / "experiments/progprompt_vh/phase5/data/graph_supported_actions.json"

DEFAULT_PROMPT_EXAMPLES = {
    "put the wine glass in the kitchen cabinet",
    "throw away the lime",
    "wash mug",
}

# The release stores GT final graphs without task identifiers. These orders are
# therefore protocol data, not incidental filesystem order. test_unseen matches
# ProgPrompt Table II and the already audited Phase-5 mapping.
POSITIONAL_ORDERS: Dict[str, List[str]] = {
    "test_seen": [
        "wash the rug in washing machine",
        "put all the cutlery in the sink",
        "throw away the lime",
        "put the wine glass in the kitchen cabinet",
        "put the candle on the living room shelf",
        "listen to radio",
        "bring pillow to the sofa",
        "open window",
        "cut apple",
        "wash mug",
    ],
    "test_unseen": [
        "watch tv",
        "turn off light",
        "brush teeth",
        "throw away apple",
        "make toast",
        "eat chips on the sofa",
        "put salmon in the fridge",
        "wash the plate",
        "bring coffeepot and cupcake to the coffee table",
        "microwave salmon",
    ],
}


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def graph_sha256(graph: Dict[str, Any]) -> str:
    value = json.dumps(graph, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def flatten_actions(subgoals: Dict[str, List[str]]) -> List[str]:
    return [action for group in subgoals.values() for action in group]


def horizon(length: int) -> str:
    if length <= 5:
        return "Short"
    if length <= 10:
        return "Medium"
    return "Long"


def _annotation_rows(split: str) -> List[Tuple[str, str, Dict[str, List[str]]]]:
    if split in {"env1", "env2"}:
        paths = [DATA_ROOT / "new_env" / f"{split}_annotated.json"]
    else:
        paths = sorted((DATA_ROOT / split).glob("*.json"))
    rows: List[Tuple[str, str, Dict[str, List[str]]]] = []
    for path in paths:
        for row in read_jsonl(path):
            if len(row) != 1:
                raise ValueError(f"Expected one task per line: {path}")
            task, subgoals = next(iter(row.items()))
            rows.append((task, str(path.relative_to(PROJECT_ROOT)), subgoals))
    return rows


def ordered_annotation_rows(split: str) -> List[Tuple[str, str, Dict[str, List[str]]]]:
    rows = _annotation_rows(split)
    if split not in POSITIONAL_ORDERS:
        return rows
    by_task = {task: (task, source, subgoals) for task, source, subgoals in rows}
    order = POSITIONAL_ORDERS[split]
    if set(by_task) != set(order) or len(rows) != len(order):
        raise RuntimeError(f"Audited positional order mismatch for {split}")
    return [by_task[task] for task in order]


def final_state_path(split: str) -> Path:
    name = {
        "test_seen": "final_states_test_seen.json",
        "test_unseen": "final_states_test_unseen.json",
        "test_unseen_ambiguous_goals": "final_states_test_unseen_ambiguous_goals.json",
        "env1": "final_states_env1.json",
        "env2": "final_states_env2.json",
    }[split]
    return DATA_ROOT / "final_states" / name


def initial_state_path(split: str) -> Path:
    if split in {"env1", "env2"}:
        return DATA_ROOT / "final_states" / f"initial_states_{split}.json"
    return SCENE0_INITIAL


def scene_for_split(split: str) -> int:
    return {"test_seen": 0, "test_unseen": 0, "test_unseen_ambiguous_goals": 0,
            "env1": 1, "env2": 2}[split]


def _state(object_name: str, value: str, rationale: str) -> Dict[str, Any]:
    return {
        "condition": f"STATE({object_name}, {value})",
        "predicate": "STATE",
        "object": object_name,
        "value": value,
        "rationale": rationale,
    }


def _relation(subject: str, relation: str, obj: str, rationale: str) -> Dict[str, Any]:
    return {
        "condition": f"{relation}({subject}, {obj})",
        "predicate": "RELATION",
        "subject": subject,
        "relation": relation,
        "object": obj,
        "rationale": rationale,
    }


def _count_fruit_goal() -> Dict[str, Any]:
    return {
        "condition": "COUNT_DISTINCT_INSTANCES(apple|bananas|lime|peach|plum INSIDE dishbowl) >= 4",
        "predicate": "COUNT_RELATION",
        "subjects": ["apple", "bananas", "lime", "peach", "plum"],
        "relation": "INSIDE",
        "object": "dishbowl",
        "minimum": 4,
        "distinct_instances": True,
        "rationale": "The instruction requests any four fruits; counting distinct available fruit instances avoids selecting the annotator's particular four fruits.",
    }


# Semantic goals are fixed from task language and the pinned augmentation
# ontology. They are never sent to TaskAgent, ProgramAgent, or online verifier.
SEMANTIC_GOALS: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("test_unseen", "turn off light"): {
        "conditions": [_state("lightswitch", "OFF", "The instruction explicitly requests the controlled light switch to be off.")],
        "ambiguity": "The scene represents the controlled light through the lightswitch object.",
    },
    ("test_unseen", "throw away apple"): {
        "conditions": [_relation("apple", "INSIDE", "garbagecan", "Disposal is represented by containment in the garbage can.")],
        "ambiguity": "Container closure and character location are procedural endpoints, not goals.",
    },
    ("test_unseen", "put salmon in the fridge"): {
        "conditions": [_relation("salmon", "INSIDE", "fridge", "The requested destination relation is salmon inside the fridge.")],
        "ambiguity": "Fridge-door and character states are excluded.",
    },
    ("test_unseen", "wash the plate"): {
        "conditions": [_state("plate", "WASHED", "The released benchmark augmentation persistently marks an object washed when it is in a sink while a faucet is on.")],
        "ambiguity": "WASHED is a released evaluator augmentation rather than a native graph state.",
    },
    ("test_unseen", "bring coffeepot and cupcake to the coffee table"): {
        "conditions": [
            _relation("coffeepot", "ON", "coffeetable", "The coffeepot must reach the requested table."),
            _relation("cupcake", "ON", "coffeetable", "The cupcake must reach the requested table."),
        ],
        "ambiguity": "Both object destinations are conjunctive.",
    },
    ("test_unseen", "microwave salmon"): {
        "conditions": [_state("salmon", "HEATED", "The released microwave augmentation persistently marks food HEATED.")],
        "ambiguity": "Microwave state, containment, and holding are procedural or endpoint states.",
    },
    ("test_unseen_ambiguous_goals", "collect 4 fruits such as apple, banana, etc in the dishbowl"): {
        "conditions": [_count_fruit_goal()],
        "ambiguity": "Fruit identities are intentionally open; the frozen goal counts any four distinct available fruit instances rather than the annotation's choices.",
    },
    ("env1", "turn off tablelamp"): {
        "conditions": [_state("tablelamp", "OFF", "The instruction explicitly requests the lamp to be off.")],
        "ambiguity": "No final character location is required.",
    },
    ("env1", "put the soap in the bathroomcabinet"): {
        "conditions": [_relation("barsoap", "INSIDE", "bathroomcabinet", "The soap must be contained by the requested cabinet.")],
        "ambiguity": "The annotation grounds 'soap' to the available barsoap class.",
    },
    ("env1", "throw away plum"): {
        "conditions": [_relation("plum", "INSIDE", "garbagecan", "Disposal is represented by containment in the garbage can.")],
        "ambiguity": "Container closure is not part of semantic completion.",
    },
    ("env1", "bring my book to the sofa"): {
        "conditions": [_relation("book", "ON", "sofa", "The book must be placed on the requested sofa.")],
        "ambiguity": "Character proximity is excluded.",
    },
    ("env1", "put chicken in the fridge"): {
        "conditions": [_relation("chicken", "INSIDE", "fridge", "The chicken must be inside the fridge.")],
        "ambiguity": "Fridge-door state is procedural.",
    },
    ("env1", "bring coffeepot and peach to the coffee table"): {
        "conditions": [
            _relation("coffeepot", "ON", "coffeetable", "The coffeepot must reach the coffee table."),
            _relation("peach", "ON", "coffeetable", "The peach must reach the coffee table."),
        ],
        "ambiguity": "Both requested objects are conjunctive.",
    },
    ("env1", "microwave chicken"): {
        "conditions": [_state("chicken", "HEATED", "The released microwave augmentation persistently marks food HEATED.")],
        "ambiguity": "Microwave endpoint state and holding are not required.",
    },
    ("env2", "open the curtains"): {
        "conditions": [_state("curtains", "OPEN", "The instruction explicitly requests open curtains.")],
        "ambiguity": "Character location is excluded.",
    },
    ("env2", "turn on tv"): {
        "conditions": [_state("tv", "ON", "The instruction explicitly requests the television to be on.")],
        "ambiguity": "Unlike 'watch tv', this task has an exact persistent requested state.",
    },
    ("env2", "put the soap in the bathroomcabinet"): {
        "conditions": [_relation("barsoap", "INSIDE", "bathroomcabinet", "The soap must be contained by the requested cabinet.")],
        "ambiguity": "The annotation grounds 'soap' to the available barsoap class.",
    },
    ("env2", "throw away bananas"): {
        "conditions": [_relation("bananas", "INSIDE", "garbagecan", "Disposal is represented by containment in the garbage can.")],
        "ambiguity": "Container closure is procedural.",
    },
    ("env2", "bring my book to the sofa"): {
        "conditions": [_relation("book", "ON", "sofa", "The book must be placed on the requested sofa.")],
        "ambiguity": "Character proximity is excluded.",
    },
    ("env2", "put milk in the fridge"): {
        "conditions": [_relation("milk", "INSIDE", "fridge", "The milk must be inside the fridge.")],
        "ambiguity": "Fridge-door state is procedural.",
    },
}


UNREPRESENTABLE_REASONS: Dict[Tuple[str, str], str] = {
    ("test_unseen", "watch tv"): "WATCH is an event but the graph has no persistent WATCHED state; TV ON does not establish that watching occurred.",
    ("test_unseen", "brush teeth"): "The shared API has no brush/use primitive and the graph has no BRUSHED_TEETH state.",
    ("test_unseen", "make toast"): "The graph has no TOASTED state or elapsed-time transition; toaster placement/power is only an initiation proxy.",
    ("test_unseen", "eat chips on the sofa"): "EAT is outside the released ProgPrompt/shared API and consumption has no persistent state.",
    ("test_unseen_ambiguous_goals", "make dinner"): "Open-ended meal content has no unique method-independent semantic endpoint.",
    ("test_unseen_ambiguous_goals", "make breakfast"): "Open-ended meal content has no unique method-independent semantic endpoint.",
    ("test_unseen_ambiguous_goals", "bring some breakfast to the coffeetable"): "The requested breakfast objects are unspecified and the ontology has no breakfast category predicate.",
    ("test_unseen_ambiguous_goals", "cook lunch"): "Open-ended meal content and cooking completion have no unique persistent endpoint.",
    ("env1", "watch tv"): "WATCH is an event but the graph has no persistent WATCHED state.",
    ("env1", "make toast"): "The graph has no TOASTED state or elapsed-time transition.",
    ("env1", "wash the dishbowl in dishwasher"): "The pinned augmentation has no dishwasher-to-WASHED rule, so washing completion is not representable.",
    ("env2", "make toast"): "The graph has no TOASTED state or elapsed-time transition.",
    ("env2", "wash the cutlery in dishwasher"): "The pinned augmentation has no dishwasher-to-WASHED rule, so washing completion is not representable.",
    ("env2", "make coffee in coffeemaker"): "The graph has no COFFEE_MADE/USED state and the released program leaves only a held coffeepot endpoint.",
    ("env2", "heat salmon on the stove"): "Offline replay of the released GT path does not yield HEATED under the pinned augmentation, so final heat completion is not reliably scoreable.",
}


def build_manifest_entries() -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for split in ["test_seen", "test_unseen", "test_unseen_ambiguous_goals", "env1", "env2"]:
        rows = ordered_annotation_rows(split)
        finals = read_jsonl(final_state_path(split))
        if len(rows) != len(finals):
            raise RuntimeError(f"Final-state count mismatch for {split}: {len(rows)} vs {len(finals)}")
        initials = read_jsonl(initial_state_path(split)) if split in {"env1", "env2"} else None
        if initials is not None and len(initials) != len(rows):
            raise RuntimeError(f"Initial-state count mismatch for {split}")
        for index, (task, source, subgoals) in enumerate(rows):
            actions = flatten_actions(subgoals)
            key = (split, task)
            if split == "test_seen":
                status = "excluded_not_held_out"
                reason = "Task text is present in the official train split; this is the seen-task evaluation slice."
            elif key in UNREPRESENTABLE_REASONS:
                status = "excluded_unrepresentable"
                reason = UNREPRESENTABLE_REASONS[key]
            elif key in SEMANTIC_GOALS:
                status = "included"
                reason = "Valid official held-out task with GT program/final state and a reliable frozen semantic goal under the shared API."
            else:
                raise RuntimeError(f"No pre-execution selection decision for {key}")
            init_index: Optional[int] = index if split in {"env1", "env2"} else None
            initial_graph = initials[index] if initials is not None else json.loads(SCENE0_INITIAL.read_text(encoding="utf-8"))
            entries.append(
                {
                    "task_id": f"{split}::{task.replace(' ', '_')}",
                    "task_text": task,
                    "official_split": split,
                    "scene": scene_for_split(split),
                    "source_annotation": source,
                    "gt_action_length": len(actions),
                    "horizon": horizon(len(actions)),
                    "is_long_horizon": len(actions) >= 11,
                    "gt_actions": actions,
                    "has_gt_program": True,
                    "initial_state_source": str(initial_state_path(split).relative_to(PROJECT_ROOT)),
                    "initial_state_index": init_index,
                    "initial_state_sha256": graph_sha256(initial_graph),
                    "final_state_source": str(final_state_path(split).relative_to(PROJECT_ROOT)),
                    "final_state_index": index,
                    "has_final_state": True,
                    "direct_default_prompt_overlap": task in DEFAULT_PROMPT_EXAMPLES,
                    "semantic_goal": SEMANTIC_GOALS.get(key),
                    "filter_status": status,
                    "filter_reason": reason,
                }
            )
    return entries


def load_initial_graph(entry: Dict[str, Any]) -> Dict[str, Any]:
    path = PROJECT_ROOT / entry["initial_state_source"]
    if entry["initial_state_index"] is None:
        graph = json.loads(path.read_text(encoding="utf-8"))
    else:
        graph = read_jsonl(path)[int(entry["initial_state_index"])]
    if graph_sha256(graph) != entry["initial_state_sha256"]:
        raise RuntimeError(f"Initial graph hash mismatch for {entry['task_id']}")
    return graph


def load_final_graph(entry: Dict[str, Any]) -> Dict[str, Any]:
    path = PROJECT_ROOT / entry["final_state_source"]
    return read_jsonl(path)[int(entry["final_state_index"])]


def taskset_statistics(entries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    selected = [item for item in entries if item["filter_status"] == "included"]
    lengths = [int(item["gt_action_length"]) for item in selected]
    counts = Counter(item["horizon"] for item in selected)
    return {
        "n": len(selected),
        "min": min(lengths),
        "mean": mean(lengths),
        "median": median(lengths),
        "max": max(lengths),
        "horizons": {name: counts[name] for name in ["Short", "Medium", "Long"]},
        "splits": dict(Counter(item["official_split"] for item in selected)),
    }

