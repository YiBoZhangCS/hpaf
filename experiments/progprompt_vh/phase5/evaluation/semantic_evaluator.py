"""Deterministic evaluator for the pre-frozen task-semantic conditions."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


def canonical_condition(condition: Dict[str, Any]) -> Tuple[str, ...]:
    predicate = str(condition.get("predicate", "")).upper()
    if predicate == "STATE":
        return (
            "STATE",
            str(condition.get("object", "")).lower(),
            str(condition.get("value", "")).upper(),
        )
    if predicate == "RELATION":
        return (
            "RELATION",
            str(condition.get("subject", "")).lower(),
            str(condition.get("relation", "")).upper(),
            str(condition.get("object", "")).lower(),
        )
    raise ValueError(f"Unsupported semantic predicate: {predicate}")


def condition_satisfied(
    graph: Dict[str, Any], condition: Dict[str, Any]
) -> Tuple[bool, str]:
    key = canonical_condition(condition)
    if key[0] == "STATE":
        _, object_name, value = key
        evidence = [
            node["id"]
            for node in graph["nodes"]
            if node["class_name"] == object_name and value in node.get("states", [])
        ]
        return bool(evidence), f"matching node ids={evidence}" if evidence else ""

    _, subject, relation, object_name = key
    class_by_id = {node["id"]: node["class_name"] for node in graph["nodes"]}
    matching = []
    for edge in graph["edges"]:
        edge_relation = str(edge["relation_type"]).upper()
        relation_match = (
            "HOLD" in edge_relation if relation in {"HOLD", "HOLDS"} else edge_relation == relation
        )
        if (
            class_by_id.get(edge["from_id"]) == subject
            and relation_match
            and class_by_id.get(edge["to_id"]) == object_name
        ):
            matching.append(
                f'{edge["from_id"]}-{edge["relation_type"]}-{edge["to_id"]}'
            )
    return bool(matching), f"matching edges={matching}" if matching else ""


def evaluate_conditions(
    graph: Dict[str, Any], conditions: Iterable[Dict[str, Any]]
) -> Dict[str, Any]:
    details: List[Dict[str, Any]] = []
    for condition in conditions:
        satisfied, evidence = condition_satisfied(graph, condition)
        details.append(
            {
                "condition": condition,
                "satisfied": satisfied,
                "evidence": evidence,
            }
        )
    if not details:
        raise ValueError("Semantic evaluation requires at least one frozen condition")
    satisfied_count = sum(int(item["satisfied"]) for item in details)
    gcr = satisfied_count / len(details)
    return {
        "Semantic_SR": int(satisfied_count == len(details)),
        "Semantic_GCR": gcr,
        "semantic_goal_condition_count": len(details),
        "semantic_satisfied_condition_count": satisfied_count,
        "semantic_condition_details": details,
        "semantic_missing_conditions": [
            item["condition"] for item in details if not item["satisfied"]
        ],
    }


def verify_primary_goal(
    graph: Dict[str, Any], condition: Dict[str, Any]
) -> Tuple[bool, Dict[str, Any]]:
    satisfied, evidence = condition_satisfied(graph, condition)
    return satisfied, {
        "condition": condition,
        "satisfied": satisfied,
        "evidence": evidence,
    }

