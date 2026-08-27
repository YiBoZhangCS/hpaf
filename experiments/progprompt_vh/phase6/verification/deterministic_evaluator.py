"""Method-independent final scorer for the frozen Phase-6 semantic goals."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


def condition_satisfied(graph: Dict[str, Any], condition: Dict[str, Any]) -> Tuple[bool, str]:
    predicate = str(condition.get("predicate", "")).upper()
    if predicate == "STATE":
        object_name = str(condition["object"]).lower()
        value = str(condition["value"]).upper()
        matches = [
            node["id"] for node in graph["nodes"]
            if node["class_name"] == object_name and value in node.get("states", [])
        ]
        return bool(matches), f"matching node ids={matches}" if matches else ""

    class_by_id = {node["id"]: node["class_name"] for node in graph["nodes"]}
    if predicate == "RELATION":
        subject = str(condition["subject"]).lower()
        relation = str(condition["relation"]).upper()
        obj = str(condition["object"]).lower()
        matches = []
        for edge in graph["edges"]:
            edge_relation = str(edge["relation_type"]).upper()
            relation_match = "HOLD" in edge_relation if relation in {"HOLD", "HOLDS"} else edge_relation == relation
            if class_by_id.get(edge["from_id"]) == subject and relation_match and class_by_id.get(edge["to_id"]) == obj:
                matches.append(f'{edge["from_id"]}-{edge["relation_type"]}-{edge["to_id"]}')
        return bool(matches), f"matching edges={matches}" if matches else ""

    if predicate == "COUNT_RELATION":
        subjects = {str(item).lower() for item in condition["subjects"]}
        relation = str(condition["relation"]).upper()
        obj = str(condition["object"]).lower()
        target_ids = {node["id"] for node in graph["nodes"] if node["class_name"] == obj}
        matching_ids = {
            edge["from_id"] for edge in graph["edges"]
            if str(edge["relation_type"]).upper() == relation
            and edge["to_id"] in target_ids
            and class_by_id.get(edge["from_id"]) in subjects
        }
        minimum = int(condition["minimum"])
        return len(matching_ids) >= minimum, f"matching distinct instance ids={sorted(matching_ids)}; minimum={minimum}"

    raise ValueError(f"Unsupported semantic predicate: {predicate}")


def evaluate_conditions(graph: Dict[str, Any], conditions: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    details: List[Dict[str, Any]] = []
    for condition in conditions:
        satisfied, evidence = condition_satisfied(graph, condition)
        details.append({"condition": condition, "satisfied": satisfied, "evidence": evidence})
    if not details:
        raise ValueError("Semantic evaluation requires at least one frozen condition")
    satisfied_count = sum(int(item["satisfied"]) for item in details)
    return {
        "final_semantic_SR": int(satisfied_count == len(details)),
        "semantic_GCR": satisfied_count / len(details),
        "semantic_goal_condition_count": len(details),
        "semantic_satisfied_condition_count": satisfied_count,
        "semantic_condition_details": details,
        "semantic_missing_conditions": [item["condition"] for item in details if not item["satisfied"]],
    }

