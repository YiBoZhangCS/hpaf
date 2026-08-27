"""Deterministic task-relevant symbolic state projection."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, Mapping, Sequence


RELEVANT_PROPERTIES = {
    "CAN_OPEN",
    "CONTAINERS",
    "GRABBABLE",
    "HAS_SWITCH",
    "SITTABLE",
    "SURFACES",
}


def _mentioned_classes(text: str, classes: Iterable[str]) -> set[str]:
    compact_text = re.sub(r"[^a-z0-9]", "", text.lower())
    words = set(re.findall(r"[a-z0-9_]+", text.lower()))
    return {
        name
        for name in classes
        if name.lower() in words
        or re.sub(r"[^a-z0-9]", "", name.lower()) in compact_text
    }


def project_relevant_symbolic_state(
    graph: Dict[str, Any],
    *,
    task: str,
    atomic_task: Mapping[str, Any] | None = None,
    recent_errors: Sequence[Mapping[str, Any]] = (),
) -> str:
    """Project current state without using goals, GT programs, or scores."""

    nodes = {int(node["id"]): node for node in graph.get("nodes", [])}
    classes = sorted({str(node["class_name"]) for node in nodes.values()})
    atomic_text = ""
    explicit = set()
    if atomic_task:
        atomic_text = " ".join(
            str(atomic_task.get(key) or "")
            for key in ["instruction", "manipulated_object", "target_object", "process_intent"]
        )
        explicit.update(
            str(atomic_task[key])
            for key in ["manipulated_object", "target_object"]
            if atomic_task.get(key)
        )
    error_text = " ".join(
        f"{item.get('line', '')} {item.get('message', '')}" for item in recent_errors
    )
    relevant_classes = explicit | _mentioned_classes(
        f"{task} {atomic_text} {error_text}", classes
    )

    character_ids = {
        node_id for node_id, node in nodes.items() if node["class_name"] == "character"
    }
    held_ids = {
        int(edge["to_id"])
        for edge in graph.get("edges", [])
        if int(edge["from_id"]) in character_ids
        and "HOLD" in str(edge["relation_type"]).upper()
    }
    relevant_classes.update(
        str(nodes[node_id]["class_name"]) for node_id in held_ids if node_id in nodes
    )
    seed_ids = {
        node_id
        for node_id, node in nodes.items()
        if str(node["class_name"]) in relevant_classes
    } | character_ids | held_ids

    selected_ids = set(seed_ids)
    for edge in graph.get("edges", []):
        source = int(edge["from_id"])
        target = int(edge["to_id"])
        relation = str(edge["relation_type"]).upper()
        if relation in {"ON", "INSIDE", "CLOSE"} and (
            source in seed_ids or target in seed_ids
        ):
            selected_ids.update([source, target])
    selected_ids.intersection_update(nodes)

    room_names = sorted(
        {
            str(nodes[int(edge["to_id"])]["class_name"])
            for edge in graph.get("edges", [])
            if int(edge["from_id"]) in character_ids
            and str(edge["relation_type"]).upper() == "INSIDE"
            and int(edge["to_id"]) in nodes
            and nodes[int(edge["to_id"])].get("category") == "Rooms"
        }
    )
    character_states = sorted(
        {
            str(state)
            for node_id in character_ids
            for state in nodes[node_id].get("states", [])
        }
    )
    held_classes = sorted(
        str(nodes[node_id]["class_name"]) for node_id in held_ids if node_id in nodes
    )

    by_class: Dict[str, list[Dict[str, Any]]] = defaultdict(list)
    for node_id in sorted(selected_ids):
        node = nodes[node_id]
        if node["class_name"] == "character" or node.get("category") == "Rooms":
            continue
        by_class[str(node["class_name"])].append(node)

    object_parts = []
    for class_name in sorted(by_class):
        candidates = by_class[class_name]
        state_variants = sorted(
            {
                "/".join(sorted(str(state) for state in node.get("states", []))) or "none"
                for node in candidates
            }
        )
        properties = sorted(
            {
                str(prop)
                for node in candidates
                for prop in node.get("properties", [])
                if str(prop) in RELEVANT_PROPERTIES
            }
        )
        object_parts.append(
            f"{class_name}[n={len(candidates)};state={'+'.join(state_variants)};"
            f"props={'+'.join(properties) or 'none'}]"
        )

    relations = sorted(
        {
            f"{nodes[int(edge['from_id'])]['class_name']} "
            f"{str(edge['relation_type']).upper()} "
            f"{nodes[int(edge['to_id'])]['class_name']}"
            for edge in graph.get("edges", [])
            if int(edge["from_id"]) in selected_ids
            and int(edge["to_id"]) in selected_ids
            and str(edge["relation_type"]).upper() in {"ON", "INSIDE", "CLOSE", "HOLDS_LH", "HOLDS_RH"}
            and nodes[int(edge["from_id"])]["class_name"] != nodes[int(edge["to_id"])]["class_name"]
        }
    )
    return (
        f"character(room={','.join(room_names) or 'unknown'};"
        f"state={'+'.join(character_states) or 'none'};"
        f"holds={'+'.join(held_classes) or 'none'}). "
        f"objects: {'; '.join(object_parts) or 'none'}. "
        f"relations: {'; '.join(relations) or 'none'}."
    )

