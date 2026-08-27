#!/usr/bin/env python3
"""Build the pre-execution semantic-goal freeze from task language and ontology.

The mapping below is the result of a task-by-task protocol audit, not model
output.  Running this command is intentionally one-shot: it refuses to replace
an existing freeze.  ``--check`` validates the frozen file without rewriting it.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[4]
PHASE5 = ROOT / "experiments/progprompt_vh/phase5"
TASK_METADATA = ROOT / "experiments/progprompt_vh/results/task_metadata.csv"
INITIAL_GRAPH = ROOT / "experiments/progprompt_vh/results/environment_initial_state.json"
OUTPUT = PHASE5 / "data/semantic_goals_test_unseen.json"


def state(object_name: str, value: str, rationale: str) -> Dict[str, Any]:
    return {
        "condition": f"STATE({object_name}, {value})",
        "predicate": "STATE",
        "object": object_name,
        "value": value,
        "rationale": rationale,
    }


def relation(subject: str, predicate: str, obj: str, rationale: str) -> Dict[str, Any]:
    return {
        "condition": f"{predicate}({subject}, {obj})",
        "predicate": "RELATION",
        "subject": subject,
        "relation": predicate,
        "object": obj,
        "rationale": rationale,
    }


def audited_specs() -> List[Dict[str, Any]]:
    return [
        {
            "task": "watch tv",
            "conditions": [
                state(
                    "tv",
                    "ON",
                    "Watching requires a powered television; ON is the persistent graph effect used by the task annotation.",
                )
            ],
            "ambiguity": "WATCH is an executable event but leaves no persistent WATCHED state. TV ON is a disclosed operational surrogate and does not prove viewing duration.",
        },
        {
            "task": "turn off light",
            "conditions": [
                state(
                    "lightswitch",
                    "OFF",
                    "The instruction explicitly requests the light switch's OFF state.",
                )
            ],
            "ambiguity": "The graph represents the controlled light through the lightswitch object; no character room/location endpoint is required.",
        },
        {
            "task": "brush teeth",
            "conditions": [
                relation(
                    "toothpaste",
                    "INSIDE",
                    "toothbrush",
                    "The released task annotation operationalizes preparing/using the toothbrush by applying toothpaste to the toothbrush; this is its only persistent task-object relation.",
                )
            ],
            "ambiguity": "The ontology has no BRUSHED_TEETH state and no mouth/teeth target. This relation is an annotation-informed operational surrogate, not proof of the real-world brushing event.",
        },
        {
            "task": "throw away apple",
            "conditions": [
                relation(
                    "apple",
                    "INSIDE",
                    "garbagecan",
                    "Throwing the apple away is represented by containment in the garbage can.",
                )
            ],
            "ambiguity": "Garbage-can OPEN/CLOSED and character proximity are prerequisites/endpoints, not requested semantic goals.",
        },
        {
            "task": "make toast",
            "conditions": [
                relation(
                    "breadslice",
                    "INSIDE",
                    "toaster",
                    "A bread slice placed in the toaster is the persistent object relation for initiating toast preparation.",
                ),
                state(
                    "toaster",
                    "ON",
                    "The toaster being ON distinguishes initiated toasting from merely storing bread in it.",
                ),
            ],
            "ambiguity": "The pinned augmentation explicitly leaves toaster/TOASTED as TODO, and time cannot advance automatically. INSIDE+ON is a frozen 'toasting initiated' proxy; it cannot certify finished toast and differs from the demonstration endpoint that switches off/removes the bread.",
        },
        {
            "task": "eat chips on the sofa",
            "conditions": [
                relation(
                    "character",
                    "ON",
                    "sofa",
                    "The task language explicitly requires performing the activity on the sofa; sitting is persistently represented as character ON sofa.",
                )
            ],
            "ambiguity": "Chips lack EATABLE in this scene and consumption has no persistent state. The sofa condition captures only the explicitly stated spatial part; arbitrary final HOLDS is excluded.",
        },
        {
            "task": "put salmon in the fridge",
            "conditions": [
                relation(
                    "salmon",
                    "INSIDE",
                    "fridge",
                    "The requested destination relation is exactly salmon inside the fridge.",
                )
            ],
            "ambiguity": "Fridge door state, character proximity, room, and holding are not required by the instruction.",
        },
        {
            "task": "wash the plate",
            "conditions": [
                state(
                    "plate",
                    "WASHED",
                    "The pinned benchmark augmentation adds WASHED when a plate is in a sink while its faucet is on.",
                )
            ],
            "ambiguity": "WASHED is evaluator augmentation rather than a native Evolving Graph State enum; plate-in-sink and faucet state are causal prerequisites, not additional goals.",
        },
        {
            "task": "bring coffeepot and cupcake to the coffee table",
            "conditions": [
                relation(
                    "coffeepot",
                    "ON",
                    "coffeetable",
                    "The coffeepot's requested destination is the coffee table surface.",
                ),
                relation(
                    "cupcake",
                    "ON",
                    "coffeetable",
                    "The cupcake's requested destination is the coffee table surface.",
                ),
            ],
            "ambiguity": "Both objects are conjunctive goals. Character location and object room containment are excluded demonstration endpoints.",
        },
        {
            "task": "microwave salmon",
            "conditions": [
                state(
                    "salmon",
                    "HEATED",
                    "The pinned benchmark augmentation adds HEATED when food is inside an ON microwave.",
                )
            ],
            "ambiguity": "Microwave door/power and salmon containment/holding are procedural or endpoint states; HEATED is the persistent core effect.",
        },
    ]


def validate(payload: Dict[str, Any]) -> None:
    with TASK_METADATA.open("r", encoding="utf-8", newline="") as handle:
        expected_tasks = [row["task"] for row in csv.DictReader(handle)]
    specs = payload.get("tasks")
    if not isinstance(specs, list) or [item.get("task") for item in specs] != expected_tasks:
        raise ValueError("Semantic-goal task order differs from the audited test_unseen order")
    graph = json.loads(INITIAL_GRAPH.read_text(encoding="utf-8"))
    classes = {node["class_name"] for node in graph["nodes"]}
    for spec in specs:
        conditions = spec.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            raise ValueError(f'{spec.get("task")}: expected at least one condition')
        if not str(spec.get("ambiguity", "")).strip():
            raise ValueError(f'{spec.get("task")}: missing ambiguity disclosure')
        for condition in conditions:
            predicate = condition.get("predicate")
            if predicate == "STATE":
                names = [condition.get("object")]
            elif predicate == "RELATION":
                names = [condition.get("subject"), condition.get("object")]
            else:
                raise ValueError(f"Unsupported semantic predicate: {predicate}")
            if any(name not in classes for name in names):
                raise ValueError(f'{spec.get("task")}: condition references absent class {names}')
            if not str(condition.get("rationale", "")).strip():
                raise ValueError(f'{spec.get("task")}: condition lacks rationale')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        if not OUTPUT.exists():
            raise FileNotFoundError(OUTPUT)
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
        validate(payload)
        print(f"semantic_goal_sha256={hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}")
        return
    if OUTPUT.exists():
        raise FileExistsError(
            f"Refusing to overwrite frozen semantic goals: {OUTPUT}. Use --check."
        )
    payload = {
        "schema_version": 1,
        "test_set": "test_unseen",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "source_policy": [
            "natural-language task description",
            "pinned VirtualHome/Evolving Graph and ProgPrompt augmentation ontology",
            "ground-truth task annotation/action description for semantic interpretation only",
        ],
        "excluded_sources": [
            "all Phase-5 method outputs",
            "method ranking or success/failure",
            "ground-truth final graph supplied to a planner or verifier",
        ],
        "aggregation": "all listed conditions are conjunctive; no method-specific alternatives",
        "tasks": audited_specs(),
    }
    validate(payload)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"semantic_goal_sha256={hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}")
    print(f"wrote={OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

