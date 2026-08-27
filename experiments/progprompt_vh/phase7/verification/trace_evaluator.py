"""Frozen method-independent trace predicates for restored official tasks."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple


ACTION_RE = re.compile(
    r"\[([a-z]+)\].*?<([a-z0-9_]+)> \(([0-9]+)\)(?:.*?<([a-z0-9_]+)> \(([0-9]+)\))?",
    re.IGNORECASE,
)


def successful_actions(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions = []
    for item in record.get("graph_execution_trace", []):
        if not item.get("success") or item.get("parsed_action") is None:
            continue
        match = ACTION_RE.search(item.get("source_action", ""))
        if not match:
            continue
        verb, first, first_id, second, second_id = match.groups()
        actions.append(
            {
                "verb": verb.lower(),
                "first": first.lower(),
                "first_id": int(first_id),
                "second": second.lower() if second else None,
                "second_id": int(second_id) if second_id else None,
                "ordinal": len(actions) + 1,
            }
        )
    return actions


def _event_success(actions: List[Dict[str, Any]], goal: Dict[str, Any]) -> Tuple[bool, str]:
    allowed = {str(item).lower() for item in goal["actions"]}
    object_name = str(goal["object"]).lower()
    matches = [
        item for item in actions
        if item["verb"] in allowed and (item["first"] == object_name or item["second"] == object_name)
    ]
    return bool(matches), f"successful event actions={matches}" if matches else ""


def _has_relation(graph: Dict[str, Any], subject: str, obj: str) -> bool:
    classes = {node["id"]: node["class_name"] for node in graph.get("nodes", [])}
    return any(
        classes.get(edge["from_id"]) == subject
        and classes.get(edge["to_id"]) == obj
        and edge["relation_type"] in {"INSIDE", "ON"}
        for edge in graph.get("edges", [])
    )


def _associated_at_on(
    actions: List[Dict[str, Any]], initial_graph: Dict[str, Any], item: str,
    appliance: str, controller: str
) -> bool:
    classes = {node["id"]: node["class_name"] for node in initial_graph.get("nodes", [])}
    appliance_ids = {node_id for node_id, name in classes.items() if name == appliance}
    associated = {
        edge["from_id"] for edge in initial_graph.get("edges", [])
        if classes.get(edge["from_id"]) == item
        and edge["to_id"] in appliance_ids
        and edge["relation_type"] in {"INSIDE", "ON"}
    }
    for action in actions:
        if action["verb"] in {"putin", "putback"} and action["first"] == item:
            if action["second"] == appliance:
                associated.add(action["first_id"])
            else:
                associated.discard(action["first_id"])
        elif action["verb"] == "grab" and action["first"] == item:
            associated.discard(action["first_id"])
        if action["verb"] == "switchon" and action["first"] in {controller, appliance}:
            return bool(associated)
    return False


def _appliance_cycle_success(
    actions: List[Dict[str, Any]], goal: Dict[str, Any], initial_graph: Dict[str, Any]
) -> Tuple[bool, str]:
    item_name = str(goal["item"]).lower() if goal.get("item") else None
    appliance_name = str(goal["appliance"]).lower()
    controller_name = str(goal.get("controller", appliance_name)).lower()
    load_required = bool(goal.get("load_required", True))
    output_name = str(goal["output_object"]).lower() if goal.get("output_object") else None

    load = [
        action for action in actions
        if action["verb"] == "putin"
        and action["second"] == appliance_name
        and (item_name is None or action["first"] == item_name)
    ]
    on = [
        action for action in actions
        if action["verb"] == "switchon"
        and (action["first"] == controller_name or action["first"] == appliance_name)
    ]
    off = [
        action for action in actions
        if action["verb"] == "switchoff"
        and (action["first"] == controller_name or action["first"] == appliance_name)
    ]
    if load_required and not load:
        return False, "required source-to-appliance putin event absent"
    if goal.get("require_initial_association") and (
        item_name is None or not _has_relation(initial_graph, item_name, appliance_name)
    ):
        return False, "required initial source-appliance association absent"
    if not on or not off or min(item["ordinal"] for item in off) <= min(item["ordinal"] for item in on):
        return False, "successful appliance ON->OFF cycle absent"
    if item_name is not None and not _associated_at_on(
        actions, initial_graph, item_name, appliance_name, controller_name
    ):
        return False, "source was not associated with the appliance at ON transition"
    if output_name:
        output = [
            action for action in actions
            if action["verb"] == "grab" and action["first"] == output_name
            and action["ordinal"] > max(item["ordinal"] for item in off)
        ]
        if not output:
            return False, "required post-cycle output interaction absent"
    return True, f"load={load}; on={on}; off={off}; output={output_name or 'none'}"


def evaluate_trace_goal(
    record: Dict[str, Any], trace_goal: Dict[str, Any], initial_graph: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    actions = successful_actions(record)
    kind = str(trace_goal.get("kind", "")).upper()
    if kind == "SUCCESSFUL_EVENT":
        satisfied, evidence = _event_success(actions, trace_goal)
    elif kind == "SUCCESSFUL_APPLIANCE_CYCLE":
        satisfied, evidence = _appliance_cycle_success(actions, trace_goal, initial_graph or {})
    else:
        raise ValueError(f"Unsupported frozen trace predicate: {kind}")
    return {
        "final_semantic_SR": int(satisfied),
        "semantic_GCR": float(satisfied),
        "semantic_goal_condition_count": 1,
        "semantic_satisfied_condition_count": int(satisfied),
        "semantic_condition_details": [{"trace_goal": trace_goal, "satisfied": satisfied, "evidence": evidence}],
        "semantic_missing_conditions": [] if satisfied else [trace_goal],
    }
